from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .base import InboundResponse

MOCK_DIR = Path.home() / ".the-show" / "urgent-mock"
SENDS_LOG = MOCK_DIR / "sends.log"
RESPONSES_FILE = MOCK_DIR / "responses.json"


class MockChannel:
    """Console + file-drop mock channel. Supports all three auth methods."""

    channel_type = "mock"
    supported_auth_methods = ["channel-native", "reply-token", "signed-link"]

    def send(self, handle: str, message: str, auth_method: str, auth_token: str | None) -> None:
        import urgent_contact.channels.mock as _m
        _m.MOCK_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[MOCK CHANNEL: mock] >>> To {handle}")
        for line in message.splitlines():
            print(f"  {line}")
        entry = {
            "to": handle,
            "message": message,
            "auth_method": auth_method,
            "auth_token": auth_token,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        with _m.SENDS_LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def poll_responses(self, handle: str) -> List[InboundResponse]:
        """Return all responses in the file addressed to handle."""
        import urgent_contact.channels.mock as _m
        if not _m.RESPONSES_FILE.exists():
            return []
        results: List[InboundResponse] = []
        try:
            text = _m.RESPONSES_FILE.read_text(encoding="utf-8")
        except OSError:
            return []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("handle") != handle:
                continue
            ts_str = entry.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)
            extra = {k: v for k, v in entry.items()
                     if k not in ("handle", "text", "timestamp")}
            results.append(InboundResponse(
                channel_type="mock",
                channel_handle=handle,
                raw_text=entry.get("text", ""),
                channel_verified_identity=True,  # mock always verifies identity
                received_at=ts,
                extra=extra,
            ))
        return results

    def cancel_pending(self, handle: str) -> None:
        pass  # mock has no outbound queue to cancel

    def supports_cancellation(self) -> bool:
        return False
