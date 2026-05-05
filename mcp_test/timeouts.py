from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


READ_METHODS = {
    "ping",
    "tools/list",
    "resources/list",
    "resources/read",
    "resources/templates/list",
    "prompts/list",
    "prompts/get",
    "completion/complete",
    "logging/setLevel",
}

SAMPLING_METHODS = {
    "sampling/createMessage",
    "elicitation/create",
    "roots/list",
}

# Built-in defaults by operation family. These power smart_timeout_for_method
# AND are exposed via SMART_TIMEOUT_DEFAULTS so docs / pyproject examples don't
# need to hardcode the same numbers in two places.
SMART_TIMEOUT_DEFAULTS: dict[str, float] = {
    "tools/call": 30.0,
    "tasks/*": 30.0,
    "sampling/createMessage": 60.0,
    "elicitation/create": 60.0,
    "roots/list": 60.0,
    "*/list": 5.0,
    "*/read": 5.0,
    "default": 10.0,
}


@dataclass(frozen=True)
class TimeoutConfig:
    """Per-method timeout policy for MCP JSON-RPC operations."""

    default: float = 10.0
    methods: Mapping[str, float] = field(default_factory=dict)
    use_smart_defaults: bool = False

    def resolve(self, method: str, explicit: float | None = None) -> float:
        if explicit is not None:
            return float(explicit)
        if method in self.methods:
            return float(self.methods[method])
        if self.use_smart_defaults:
            return smart_timeout_for_method(method)
        return float(self.default)

    @classmethod
    def from_values(
        cls,
        default: float = 10.0,
        methods: Mapping[str, float] | None = None,
        *,
        use_smart_defaults: bool = False,
    ) -> "TimeoutConfig":
        return cls(
            default=float(default),
            methods={str(k): float(v) for k, v in (methods or {}).items()},
            use_smart_defaults=use_smart_defaults,
        )


def smart_timeout_for_method(method: str) -> float:
    """Return conservative built-in defaults by operation family.

    Sourced from SMART_TIMEOUT_DEFAULTS so callers/docs can introspect the
    same map.
    """

    if method == "tools/call":
        return SMART_TIMEOUT_DEFAULTS["tools/call"]
    if method.startswith("tasks/"):
        return SMART_TIMEOUT_DEFAULTS["tasks/*"]
    if method in SAMPLING_METHODS:
        return SMART_TIMEOUT_DEFAULTS.get(method, SMART_TIMEOUT_DEFAULTS["sampling/createMessage"])
    if method in READ_METHODS or method.endswith("/list"):
        return SMART_TIMEOUT_DEFAULTS["*/list"]
    if method.endswith("/read"):
        return SMART_TIMEOUT_DEFAULTS["*/read"]
    return SMART_TIMEOUT_DEFAULTS["default"]


def parse_timeout_overrides(values: list[str] | tuple[str, ...] | None) -> dict[str, float]:
    """Parse CLI values shaped as METHOD=SECONDS."""

    parsed: dict[str, float] = {}
    for raw in values or ():
        if "=" not in raw:
            raise ValueError(
                f"Invalid timeout override {raw!r}; expected METHOD=SECONDS"
            )
        method, _, value = raw.partition("=")
        method = method.strip()
        if not method:
            raise ValueError(
                f"Invalid timeout override {raw!r}; method name is empty"
            )
        try:
            timeout = float(value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid timeout override {raw!r}; seconds must be numeric"
            ) from exc
        if timeout <= 0:
            raise ValueError(
                f"Invalid timeout override {raw!r}; seconds must be positive"
            )
        parsed[method] = timeout
    return parsed
