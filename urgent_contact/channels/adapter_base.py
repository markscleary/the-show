from abc import ABC, abstractmethod
from typing import Any, Dict, List
from urgent_contact.channels.base import InboundResponse

class AbstractChannelAdapter(ABC):
    channel_type: str
    supported_auth_methods: List[str]
    timeout_seconds: int = 30
    retry_policy: Dict[str, Any] = {"max_attempts": 3, "backoff": "exponential"}

    @abstractmethod
    def send(self, handle: str, message: str, auth_method: str, auth_token: str | None) -> None: ...

    @abstractmethod
    def poll_responses(self, handle: str) -> List[InboundResponse]: ...

    @abstractmethod
    def cancel_pending(self, handle: str) -> None: ...

    @abstractmethod
    def supports_cancellation(self) -> bool: ...

    def error_surface(self) -> List[str]:
        return ["timeout", "connection-error", "rate-limit"]


class AbstractSubAgentAdapter(ABC):
    agent_type: str
    model: str
    timeout_seconds: int = 120
    retry_policy: Dict[str, Any] = {"max_attempts": 3, "backoff": "exponential"}

    @abstractmethod
    def call(self, prompt: str, max_tokens: int = 2000) -> Dict[str, Any]: ...

    def error_surface(self) -> List[str]:
        return ["timeout", "connection-error", "rate-limit", "unsupported"]
