from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Protocol, runtime_checkable


@dataclass
class InboundResponse:
    channel_type: str
    channel_handle: str
    raw_text: str
    channel_verified_identity: bool = True
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    extra: dict = field(default_factory=dict)


@runtime_checkable
class ChannelAdapter(Protocol):
    channel_type: str
    supported_auth_methods: List[str]

    def send(self, handle: str, message: str, auth_method: str, auth_token: str | None) -> None:
        ...

    def poll_responses(self, handle: str) -> List[InboundResponse]:
        """Return all responses addressed to handle. Caller deduplicates."""
        ...

    def cancel_pending(self, handle: str) -> None:
        ...

    def supports_cancellation(self) -> bool:
        ...
