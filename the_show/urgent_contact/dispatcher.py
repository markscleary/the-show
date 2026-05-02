from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from the_show.models import ShowSettings
from the_show.state import (
    cancel_pending_sends,
    create_urgent_matter,
    create_urgent_send,
    get_sends_for_matter,
    log_urgent_response,
    mark_send_sent,
    update_urgent_matter,
)
from the_show.urgent_contact.auth import (
    generate_reply_token,
    generate_signed_token,
    token_in_text,
    verify_signed_token,
)
from the_show.urgent_contact.channels.base import ChannelAdapter, InboundResponse
from the_show.urgent_contact.parser import INVALID_FORMAT_REPLY, parse_keyword
from the_show.urgent_contact.throttle import UrgentThrottle

Resolution = str  # APPROVE | REJECT | STOP | CONTINUE | exhausted | throttled


def load_adapters(rehearsal: bool = False) -> dict[str, "ChannelAdapter"]:
    """Build adapter dict from env vars. mock is always available.

    If SHOW_TEST_MODE=1 or rehearsal=True, returns only MockChannel.
    """
    import logging
    import os
    from the_show.urgent_contact.channels.mock import MockChannel
    from the_show.urgent_contact.channels import config as cfg

    if os.environ.get("SHOW_TEST_MODE") == "1" or rehearsal:
        if rehearsal:
            logging.info("[adapters] rehearsal=True — forcing MockChannel for all channels")
        else:
            logging.warning("[adapters] SHOW_TEST_MODE=1 — forcing MockChannel for all channels")
        return {"mock": MockChannel()}

    adapters: dict[str, ChannelAdapter] = {"mock": MockChannel()}

    token = cfg.telegram_bot_token()
    if token:
        from the_show.urgent_contact.channels.telegram import TelegramChannel
        adapters["telegram"] = TelegramChannel(
            bot_token=token,
            allowed_user_ids=cfg.telegram_allowed_user_ids(),
        )
    else:
        logging.warning("[adapters] URGENT_TELEGRAM_BOT_TOKEN not set — telegram not loaded")

    smtp = cfg.smtp_config()
    if smtp and smtp.get("signing_secret"):
        from the_show.urgent_contact.channels.email import EmailChannel
        adapters["email"] = EmailChannel(
            smtp_host=str(smtp["smtp_host"]),
            smtp_port=int(smtp["smtp_port"]),  # type: ignore[arg-type]
            username=str(smtp["username"]),
            password=str(smtp["password"]),
            from_addr=str(smtp["from_addr"]),
            signing_secret=str(smtp["signing_secret"]),
            link_base_url=cfg.link_base_url(),
        )
    elif not smtp:
        logging.warning("[adapters] URGENT_SMTP_HOST not set — email not loaded")
    else:
        logging.warning("[adapters] URGENT_EMAIL_SIGNING_SECRET not set — email not loaded")

    wa = cfg.whatsapp_config()
    if wa:
        from the_show.urgent_contact.channels.whatsapp import WhatsAppChannel
        adapters["whatsapp"] = WhatsAppChannel(**wa)
    else:
        logging.warning("[adapters] URGENT_WHATSAPP_ACCESS_TOKEN not set — whatsapp not loaded")

    twilio = cfg.twilio_config()
    if twilio:
        try:
            from the_show.urgent_contact.channels.sms import SMSChannel
            adapters["sms"] = SMSChannel(**twilio)
        except ImportError:
            logging.warning("[adapters] twilio not installed — sms not loaded")
    else:
        logging.warning("[adapters] URGENT_TWILIO_ACCOUNT_SID not set — sms not loaded")

    return adapters


def _default_timeout() -> int:
    """Read timeout at call time so tests can monkeypatch the env var."""
    return int(os.environ.get("THE_SHOW_URGENT_TIMEOUT", "300"))


def _default_poll_interval() -> float:
    """Read poll interval at call time so tests can monkeypatch the env var."""
    return float(os.environ.get("THE_SHOW_POLL_INTERVAL", "5"))


def _default_max_wait() -> Optional[float]:
    """Read max wait from env at call time. None means use deadline only."""
    val = os.environ.get("THE_SHOW_MAX_WAIT")
    return float(val) if val else None


class UrgentContactDispatcher:
    def __init__(
        self,
        db_path: str,
        show: ShowSettings,
        adapters: List[ChannelAdapter],
        poll_interval_seconds: Optional[float] = None,
        max_wait_seconds: Optional[float] = None,
    ) -> None:
        self.db_path = str(db_path)
        self.show = show
        self.adapters: Dict[str, ChannelAdapter] = {a.channel_type: a for a in adapters}
        # None means "read from env at call time" (lets tests override via monkeypatch)
        self._poll_interval_override = poll_interval_seconds
        self._max_wait_override = max_wait_seconds

        config = show.urgent_contact or {}
        self.mode: str = config.get("mode", "sequential")
        self.contacts: List[Dict[str, Any]] = config.get("contacts", [])
        self.send_interval_seconds: float = float(config.get("send-interval-seconds", 30))
        self.throttle = UrgentThrottle(
            db_path=self.db_path,
            show_id=show.id,
            max_per_show=int(config.get("max-per-show", 3)),
        )

    @property
    def poll_interval_seconds(self) -> float:
        if self._poll_interval_override is not None:
            return self._poll_interval_override
        return _default_poll_interval()

    @property
    def max_wait_seconds(self) -> Optional[float]:
        if self._max_wait_override is not None:
            return self._max_wait_override
        return _default_max_wait()

    def raise_urgent_matter(
        self,
        trigger_type: str,
        severity: str,
        prompt: str,
        deadline: Optional[str],
        scene_id: Optional[str] = None,
        channels: Optional[List[str]] = None,
        to: Optional[List[str]] = None,
    ) -> Resolution:
        if not self.throttle.is_allowed(severity, trigger_type):
            print(
                f"[URGENT] Throttled — show '{self.show.id}' has reached its urgent matter limit. "
                f"Scene '{scene_id}' will not receive human approval."
            )
            return "throttled"

        if not self.contacts:
            print(f"[URGENT] No contacts configured for show '{self.show.id}' — exhausted immediately.")
            return "exhausted"

        # Per-scene filter: select only contacts matching channels and/or to.
        # When both are None (the v1.1.0 default), every contact receives the matter.
        selected_contacts = [
            c for c in self.contacts
            if (channels is None or c.get("channel") in channels)
            and (to is None or c.get("handle") in to)
        ]
        if not selected_contacts:
            print(
                f"[URGENT] No contact matches channels={channels} to={to} "
                f"for scene '{scene_id}' — exhausted immediately."
            )
            return "exhausted"

        # Compute deadline (read timeout at call time for test-env-var compatibility)
        if deadline is not None:
            try:
                deadline_dt = datetime.fromisoformat(deadline)
                if deadline_dt.tzinfo is None:
                    deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                deadline_dt = datetime.now(timezone.utc) + timedelta(seconds=_default_timeout())
        else:
            deadline_dt = datetime.now(timezone.utc) + timedelta(seconds=_default_timeout())

        # Apply max_wait cap unconditionally — caps both explicit and default deadlines.
        # This allows THE_SHOW_MAX_WAIT to shorten long YAML timeout-seconds in test environments
        # without changing the YAML. In production, THE_SHOW_MAX_WAIT is unset and has no effect.
        max_wait = self.max_wait_seconds
        if max_wait is not None:
            capped = datetime.now(timezone.utc) + timedelta(seconds=max_wait)
            if capped < deadline_dt:
                deadline_dt = capped

        # Create matter record
        matter_id = create_urgent_matter(
            db_path=self.db_path,
            show_id=self.show.id,
            scene_id=scene_id,
            trigger_type=trigger_type,
            severity=severity,
            prompt=prompt,
            deadline=deadline_dt.isoformat(),
        )

        print(
            f"\n[URGENT] Matter #{matter_id} raised — {severity.upper()}"
            f"\n  Scene: {scene_id}"
            f"\n  Prompt: {prompt}"
            f"\n  Deadline: {deadline_dt.isoformat()}"
            f"\n  Contacts: {len(selected_contacts)} of {len(self.contacts)}"
            f"\n  Mode: {self.mode}"
        )

        # Create send records for selected contacts (queued)
        send_ids: List[int] = []
        for contact in selected_contacts:
            token = self._make_token(contact, matter_id)
            send_id = create_urgent_send(
                db_path=self.db_path,
                matter_id=matter_id,
                channel_type=contact.get("channel", "mock"),
                channel_handle=contact["handle"],
                contact_role=contact.get("role", "operator"),
                auth_method=contact.get("auth", "channel-native"),
                auth_token=token,
            )
            send_ids.append(send_id)

        # Determine firing strategy
        parallel = severity == "critical" or self.mode in ("parallel",)

        if parallel:
            self._fire_sends(matter_id, send_ids, prompt)
        else:
            # Sequential: fire first send immediately
            self._fire_send(matter_id, send_ids[0], prompt)

        # Track which sends have been fired
        fired_set: set[int] = set([send_ids[0]] if not parallel else send_ids)
        next_send_index = 1 if not parallel else len(send_ids)
        last_fire_time = datetime.now(timezone.utc)

        # Seen-response deduplication: set of (handle, raw_text, received_at_iso)
        seen_keys: set[str] = set()

        # Polling loop
        while True:
            now = datetime.now(timezone.utc)

            if now >= deadline_dt:
                print(f"[URGENT] Matter #{matter_id} deadline reached — exhausted.")
                update_urgent_matter(self.db_path, matter_id, status="exhausted")
                # Cancel only queued sends (sent ones have already been dispatched)
                cancel_pending_sends(self.db_path, matter_id, include_sent=False)
                return "exhausted"

            # Sequential: fire next contact if interval elapsed
            if (
                not parallel
                and next_send_index < len(send_ids)
                and (now - last_fire_time).total_seconds() >= self.send_interval_seconds
            ):
                self._fire_send(matter_id, send_ids[next_send_index], prompt)
                fired_set.add(send_ids[next_send_index])
                next_send_index += 1
                last_fire_time = now

            # Poll all fired sends for responses
            sends = get_sends_for_matter(self.db_path, matter_id)
            for send in sends:
                if send["id"] not in fired_set:
                    continue
                if send["status"] not in ("sent",):
                    continue

                adapter = self.adapters.get(send["channel_type"])
                if adapter is None:
                    continue

                for resp in adapter.poll_responses(send["channel_handle"]):
                    key = f"{resp.channel_handle}:{resp.raw_text}:{resp.received_at.isoformat()}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    resolution = self._process_response(
                        matter_id=matter_id,
                        send=send,
                        resp=resp,
                    )
                    if resolution is not None:
                        # Cancel all remaining queued and sent sends
                        cancel_pending_sends(self.db_path, matter_id, include_sent=True)
                        update_urgent_matter(
                            self.db_path,
                            matter_id,
                            status="resolved",
                            resolution=resolution,
                            resolved_by_channel=send["channel_type"],
                            resolved_by_contact=send["contact_role"],
                        )
                        print(
                            f"[URGENT] Matter #{matter_id} resolved: {resolution} "
                            f"(by {send['contact_role']} via {send['channel_type']})"
                        )
                        return resolution

            time.sleep(self.poll_interval_seconds)

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _make_token(self, contact: Dict[str, Any], matter_id: int) -> Optional[str]:
        auth = contact.get("auth", "channel-native")
        if auth == "reply-token":
            return generate_reply_token()
        if auth == "signed-link":
            nonce = uuid.uuid4().hex[:8]
            return generate_signed_token(self.show.id, matter_id, nonce)
        return None  # channel-native needs no token

    def _build_message(self, contact: Dict[str, Any], prompt: str, auth_token: Optional[str]) -> str:
        auth = contact.get("auth", "channel-native")
        lines = [
            f"[The Show — URGENT APPROVAL REQUIRED]",
            f"",
            f"{prompt}",
            f"",
            f"Reply with: APPROVE, REJECT, CONTINUE, or STOP",
        ]
        if auth == "reply-token" and auth_token:
            lines.append(f"Include your token: {auth_token}")
            lines.append(f"Example: APPROVE {auth_token}")
        elif auth == "signed-link" and auth_token:
            lines.append(f"Or click to approve: the-show://respond/{auth_token}")
            lines.append(f"(Or reply: APPROVE {auth_token})")
        return "\n".join(lines)

    def _fire_send(self, matter_id: int, send_id: int, prompt: str) -> None:
        sends = get_sends_for_matter(self.db_path, matter_id)
        send = next((s for s in sends if s["id"] == send_id), None)
        if send is None or send["status"] != "queued":
            return
        adapter = self.adapters.get(send["channel_type"])
        if adapter is None:
            print(f"[URGENT] No adapter for channel '{send['channel_type']}' — skipping send #{send_id}")
            return
        contact_cfg = next(
            (c for c in self.contacts if c["handle"] == send["channel_handle"]), {}
        )
        message = self._build_message(contact_cfg, prompt, send["auth_token"])
        adapter.send(send["channel_handle"], message, send["auth_method"], send["auth_token"])
        mark_send_sent(self.db_path, send_id)

    def _fire_sends(self, matter_id: int, send_ids: List[int], prompt: str) -> None:
        for send_id in send_ids:
            self._fire_send(matter_id, send_id, prompt)

    def _authenticate(self, resp: InboundResponse, send: Dict[str, Any]) -> bool:
        auth_method = send.get("auth_method", "channel-native")
        if auth_method == "channel-native":
            return resp.channel_verified_identity
        if auth_method == "reply-token":
            token = send.get("auth_token")
            if not token:
                return False
            return token_in_text(token, resp.raw_text)
        if auth_method == "signed-link":
            token = send.get("auth_token")
            if not token:
                return False
            # Accept if the exact token appears in the text (covers both click-link and manual reply)
            if not token_in_text(token, resp.raw_text):
                return False
            return verify_signed_token(token, self.show.id)
        return False

    def _process_response(
        self,
        matter_id: int,
        send: Dict[str, Any],
        resp: InboundResponse,
    ) -> Optional[str]:
        """Authenticate and parse one response. Returns keyword or None."""
        authenticated = self._authenticate(resp, send)

        if not authenticated:
            log_urgent_response(
                db_path=self.db_path,
                matter_id=matter_id,
                send_id=send["id"],
                raw_response=resp.raw_text,
                authenticated=False,
                valid_format=False,
                parsed_action=None,
            )
            return None  # silently drop unauthenticated

        action = parse_keyword(resp.raw_text)
        valid = action is not None

        log_urgent_response(
            db_path=self.db_path,
            matter_id=matter_id,
            send_id=send["id"],
            raw_response=resp.raw_text,
            authenticated=True,
            valid_format=valid,
            parsed_action=action,
        )

        if not valid:
            # Send one "invalid format" reply
            adapter = self.adapters.get(send["channel_type"])
            if adapter is not None:
                try:
                    adapter.send(
                        send["channel_handle"],
                        INVALID_FORMAT_REPLY,
                        "channel-native",
                        None,
                    )
                except Exception:
                    pass
            return None

        return action
