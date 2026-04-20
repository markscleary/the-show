from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Set

import requests

from urgent_contact.channels.base import InboundResponse
from urgent_contact.channels.adapter_base import AbstractChannelAdapter


class TelegramChannel(AbstractChannelAdapter):
    """Polling-based Telegram adapter using the Bot API.

    handle = Telegram chat_id (== numeric user_id for DMs).
    Authentication: channel-native — trusts only messages from allowed_user_ids.
    """

    channel_type = "telegram"
    supported_auth_methods = ["channel-native"]
    timeout_seconds = 30
    retry_policy = {"max_attempts": 3, "backoff": "exponential"}

    def __init__(self, bot_token: str, allowed_user_ids: List[str]) -> None:
        self._token = bot_token
        self._allowed_ids: Set[str] = {str(uid) for uid in allowed_user_ids}
        self._offset: int = 0
        self._api = f"https://api.telegram.org/bot{bot_token}"

    def send(
        self, handle: str, message: str, auth_method: str, auth_token: Optional[str]
    ) -> None:
        resp = requests.post(
            f"{self._api}/sendMessage",
            json={"chat_id": handle, "text": message},
            timeout=10,
        )
        resp.raise_for_status()

    def poll_responses(self, handle: str) -> List[InboundResponse]:
        try:
            resp = requests.get(
                f"{self._api}/getUpdates",
                params={"offset": self._offset, "timeout": 0},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException:
            return []

        results: List[InboundResponse] = []
        for update in resp.json().get("result", []):
            self._offset = max(self._offset, update["update_id"] + 1)
            msg = update.get("message")
            if not msg:
                continue
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if chat_id != str(handle):
                continue
            from_id = str(msg.get("from", {}).get("id", ""))
            verified = from_id in self._allowed_ids
            text = msg.get("text", "")
            ts = datetime.fromtimestamp(msg.get("date", 0), tz=timezone.utc)
            results.append(InboundResponse(
                channel_type="telegram",
                channel_handle=handle,
                raw_text=text,
                channel_verified_identity=verified,
                received_at=ts,
                extra={"from_user_id": from_id},
            ))
        return results

    def cancel_pending(self, handle: str) -> None:
        pass  # no outbound queue to cancel

    def supports_cancellation(self) -> bool:
        return False
