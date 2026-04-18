from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from urgent_contact.channels.base import InboundResponse
from urgent_contact import link_queue


class WhatsAppChannel:
    """WhatsApp Business Cloud API adapter — SKELETON for Session 4.

    This adapter is structurally complete but send() raises NotImplementedError
    until Mark completes Meta Business API onboarding (can take 1-7 days).

    SETUP CHECKLIST for Mark:
    1. Go to https://developers.facebook.com → My Apps → Create App → Business
    2. Add the "WhatsApp" product; under "Getting Started" note the test phone number ID
    3. Generate a system user access token (permanent; not the temp test token)
       Settings → Business Settings → System Users → Add → Generate Token
    4. Set env vars:
         URGENT_WHATSAPP_PHONE_NUMBER_ID  = phone number ID from the dashboard
         URGENT_WHATSAPP_ACCESS_TOKEN     = system user token
         URGENT_WHATSAPP_VERIFY_TOKEN     = any random string you choose
    5. In Meta App Dashboard → WhatsApp → Configuration → Webhook:
         Callback URL: https://<public-domain>/whatsapp-webhook
         Verify Token: same as URGENT_WHATSAPP_VERIFY_TOKEN
         Subscribe to: "messages" field
    6. For localhost testing: expose the link server via ngrok or Cloudflare Tunnel
         ngrok http 5099
       then use the ngrok HTTPS URL as the callback URL above.

    Once credentials are in place, replace the NotImplementedError body in send()
    with the commented-out requests.post block below.

    Authentication: reply-token (user must reply with "APPROVE 123456" style).
    handle = recipient WhatsApp phone number in E.164 format without leading '+' (e.g. "61412345678").
    """

    channel_type = "whatsapp"
    supported_auth_methods = ["reply-token"]

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        verify_token: str,
    ) -> None:
        self._phone_number_id = phone_number_id
        self._access_token = access_token
        self._verify_token = verify_token
        self._api = f"https://graph.facebook.com/v17.0/{phone_number_id}"

    def send(
        self, handle: str, message: str, auth_method: str, auth_token: Optional[str]
    ) -> None:
        """Send a WhatsApp message.

        Once Meta credentials are configured, replace this body with:

            import requests
            resp = requests.post(
                f"{self._api}/messages",
                headers={"Authorization": f"Bearer {self._access_token}"},
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": handle,
                    "type": "text",
                    "text": {"body": message},
                },
                timeout=10,
            )
            resp.raise_for_status()
        """
        raise NotImplementedError(
            "WhatsApp adapter requires Meta Business API credentials. "
            "See WhatsAppChannel class docstring for the setup checklist."
        )

    def poll_responses(self, handle: str) -> List[InboundResponse]:
        """Return WhatsApp replies written by the /whatsapp-webhook endpoint."""
        results: List[InboundResponse] = []
        for row in link_queue.read_whatsapp_responses(handle):
            try:
                ts = datetime.fromisoformat(row["received_at"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)
            results.append(InboundResponse(
                channel_type="whatsapp",
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
