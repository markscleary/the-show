from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from the_show.urgent_contact.channels.base import InboundResponse
from the_show.urgent_contact import link_queue

try:
    from twilio.rest import Client as TwilioClient
    _TWILIO_AVAILABLE = True
except ImportError:
    TwilioClient = None  # type: ignore[assignment,misc]
    _TWILIO_AVAILABLE = False


class SMSChannel:
    """Twilio SMS adapter with reply-token authentication.

    handle = recipient phone number in E.164 format (e.g. "+61412345678").
    Inbound replies arrive via the /twilio-webhook endpoint in link_server.py.
    Configure your Twilio number's "A MESSAGE COMES IN" webhook to POST to:
        http://<host>:<port>/twilio-webhook
    For localhost testing: expose via ngrok ("ngrok http 5099") and use the HTTPS URL.

    Twilio trial accounts can only send to verified phone numbers.
    Upgrade to a paid account to send to any number.
    """

    channel_type = "sms"
    supported_auth_methods = ["reply-token"]

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number

    def send(
        self, handle: str, message: str, auth_method: str, auth_token: Optional[str]
    ) -> None:
        if not _TWILIO_AVAILABLE:
            raise ImportError("twilio package is required for SMSChannel. Run: pip install twilio")
        client = TwilioClient(self._account_sid, self._auth_token)
        client.messages.create(to=handle, from_=self._from_number, body=message)

    def poll_responses(self, handle: str) -> List[InboundResponse]:
        """Return SMS replies received via the /twilio-webhook endpoint."""
        results: List[InboundResponse] = []
        for row in link_queue.read_sms_responses(handle):
            try:
                ts = datetime.fromisoformat(row["received_at"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)
            results.append(InboundResponse(
                channel_type="sms",
                channel_handle=handle,
                raw_text=row["body"],
                channel_verified_identity=False,
                received_at=ts,
            ))
        return results

    def cancel_pending(self, handle: str) -> None:
        pass

    def supports_cancellation(self) -> bool:
        return False
