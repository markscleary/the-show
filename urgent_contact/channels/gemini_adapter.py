from __future__ import annotations
from typing import Any, Dict
from urgent_contact.channels.adapter_base import AbstractSubAgentAdapter

class GeminiSubAgentAdapter(AbstractSubAgentAdapter):
    agent_type = "gemini"
    model = "gemini-flash"
    timeout_seconds = 120
    retry_policy = {"max_attempts": 3, "backoff": "exponential"}

    def call(self, prompt: str, max_tokens: int = 2000) -> Dict[str, Any]:
        from adapters import call_sub_agent
        return call_sub_agent(model=self.model, prompt=prompt, max_tokens=max_tokens)

    def error_surface(self):
        return ["timeout", "connection-error", "rate-limit", "unsupported"]
