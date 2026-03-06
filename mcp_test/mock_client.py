
import warnings
from typing import Any


class MockSampler:
    """Mocks the sampling/createMessage client capability."""

    def __init__(self, response_text: str):
        self.response_text = response_text
        self.requests: list[dict] = []

    def handle(self, params: dict) -> dict:
        self.requests.append(params)

        if "includeContext" in params:
            warnings.warn(
                f"Server sent deprecated 'includeContext' field with value "
                f"'{params['includeContext']}'. This field is deprecated since spec 2025-06-18.",
                DeprecationWarning,
                stacklevel=2,
            )

        return {
            "model": "mock-llm",
            "role": "assistant",
            "content": {
                "type": "text",
                "text": self.response_text
            },
            "stopReason": "endTurn"
        }

    def called_once(self) -> bool:
        return len(self.requests) == 1

    def last_request(self) -> dict:
        return self.requests[-1] if self.requests else {}

    def last_system_prompt(self) -> str:
        return self.last_request().get("systemPrompt", "")

    def last_temperature(self) -> float | None:
        return self.last_request().get("temperature")

    def last_max_tokens(self) -> int:
        return self.last_request().get("maxTokens", 0)

    def last_stop_sequences(self) -> list[str]:
        return self.last_request().get("stopSequences", [])

    def last_model_preferences(self) -> dict:
        return self.last_request().get("modelPreferences", {})

    def last_include_context(self) -> str | None:
        return self.last_request().get("includeContext")


class MockElicitor:
    """Mocks the elicitation/create client capability."""

    def __init__(self, response_data: dict[str, Any]):
        self.response_data = response_data
        self.requests: list[dict] = []

    def handle(self, params: dict) -> dict:
        self.requests.append(params)
        return {"data": self.response_data}

    def called_once(self) -> bool:
        return len(self.requests) == 1

    def last_schema(self) -> dict:
        return self.requests[-1].get("requestedSchema", {}) if self.requests else {}

