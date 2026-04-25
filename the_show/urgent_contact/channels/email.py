from __future__ import annotations

import base64
import hashlib
import hmac
import smtplib
import time
import urllib.parse
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from the_show.urgent_contact.channels.base import InboundResponse
from the_show.urgent_contact.channels.adapter_base import AbstractChannelAdapter
from the_show.urgent_contact import link_queue

_ACTIONS = ["APPROVE", "REJECT", "STOP", "CONTINUE"]


class EmailChannel(AbstractChannelAdapter):
    """SMTP email adapter with signed-link authentication.

    Authentication is handled internally: the link server verifies the HMAC token
    and writes to link_queue; poll_responses reads from there and returns
    channel_verified_identity=True responses.

    handle = recipient email address.
    """

    channel_type = "email"
    supported_auth_methods = ["channel-native"]
    timeout_seconds = 30
    retry_policy = {"max_attempts": 3, "backoff": "exponential"}

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_addr: str,
        signing_secret: str,
        link_base_url: str,
        link_expiry_seconds: int = 86400,
    ) -> None:
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._username = username
        self._password = password
        self._from_addr = from_addr
        self._signing_secret = signing_secret
        self._link_base = link_base_url.rstrip("/")
        self._link_expiry_seconds = link_expiry_seconds

    # ──────────────────────────────────────────────────────────────────────────

    def _make_link_token(self, matter_id: int, action: str, expiry_ts: int) -> str:
        msg = f"{matter_id}:{action}:{expiry_ts}"
        sig = hmac.new(
            self._signing_secret.encode(), msg.encode(), hashlib.sha256
        ).hexdigest()[:32]
        payload = f"{msg}:{sig}"
        return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")

    def _extract_matter_id(self, auth_token: Optional[str]) -> int:
        """Parse matter_id from dispatcher's signed token '{matter_id}-{nonce}-{sig}'."""
        if not auth_token:
            return 0
        try:
            return int(auth_token.split("-")[0])
        except (ValueError, IndexError):
            return 0

    # ──────────────────────────────────────────────────────────────────────────

    def send(
        self, handle: str, message: str, auth_method: str, auth_token: Optional[str]
    ) -> None:
        matter_id = self._extract_matter_id(auth_token)
        expiry_ts = int(time.time()) + self._link_expiry_seconds
        links = {}
        for action in _ACTIONS:
            token = self._make_link_token(matter_id, action, expiry_ts)
            encoded_handle = urllib.parse.quote(handle, safe="")
            links[action] = (
                f"{self._link_base}/respond?token={token}&handle={encoded_handle}"
            )
        self._send_email(
            handle,
            "[The Show] Urgent: Action Required",
            self._html_body(message, links),
            self._text_body(message, links),
        )

    def poll_responses(self, handle: str) -> List[InboundResponse]:
        results: List[InboundResponse] = []
        for row in link_queue.read_link_responses(handle):
            try:
                ts = datetime.fromisoformat(row["received_at"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)
            results.append(InboundResponse(
                channel_type="email",
                channel_handle=handle,
                raw_text=row["action"],
                channel_verified_identity=True,
                received_at=ts,
                extra={"matter_id": row.get("matter_id")},
            ))
        return results

    def cancel_pending(self, handle: str) -> None:
        pass  # email sent; cannot be recalled

    def supports_cancellation(self) -> bool:
        return False

    def error_surface(self):
        return ["timeout", "smtp-error", "rate-limit"]

    # ──────────────────────────────────────────────────────────────────────────

    def _send_email(
        self, to_addr: str, subject: str, html_body: str, text_body: str
    ) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._from_addr
        msg["To"] = to_addr
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP(self._smtp_host, self._smtp_port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(self._username, self._password)
            smtp.send_message(msg)

    def _html_body(self, message: str, links: dict) -> str:
        escaped = (
            message.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        buttons = "".join(
            f'<a href="{url}" style="display:inline-block;margin:8px 4px;padding:12px 24px;'
            f'background:#222;color:#fff;text-decoration:none;border-radius:4px;font-weight:bold">'
            f"{action}</a>"
            for action, url in links.items()
        )
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'></head>"
            "<body style='font-family:sans-serif;max-width:600px;margin:2em auto'>"
            "<h2 style='color:#c00'>[The Show] Urgent Action Required</h2>"
            f"<p>{escaped}</p>"
            f"<div style='margin:2em 0'>{buttons}</div>"
            "<hr><p style='font-size:12px;color:#666'>Sent by The Show automated runtime.</p>"
            "</body></html>"
        )

    def _text_body(self, message: str, links: dict) -> str:
        lines = [message, "", "Click a link below to respond:"]
        for action, url in links.items():
            lines.append(f"  {action}: {url}")
        return "\n".join(lines)
