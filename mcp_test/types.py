
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re


class JSONRPCErrors:
    """Standard JSON-RPC 2.0 error codes + MCP application range."""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    MCP_APP_ERROR_MIN = -32099
    MCP_APP_ERROR_MAX = -32000


SPEC_VERSIONS = {
    "2024-11-05": 1,
    "2025-03-26": 2,
    "2025-06-18": 3,
    "2025-11-25": 4,
}

TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


class MCPClientError(Exception):
    """Base exception for all mcp-test client errors."""


class MCPServerCrash(MCPClientError):
    """Raised when the MCP server process exits unexpectedly."""

    def __init__(self, returncode: int, stderr: str = ""):
        self.returncode = returncode
        self.stderr = stderr
        msg = f"MCP server exited with code {returncode}"
        if stderr:
            msg += f"\nServer stderr:\n{stderr}"
        super().__init__(msg)


class MCPTimeoutError(MCPClientError):
    """Raised when a request to the MCP server times out."""


class MCPCancelledError(MCPClientError):
    """Raised when a request is cancelled via notifications/cancelled."""


class MCPAuthRequired(MCPClientError):
    """Raised when an HTTP MCP server returns 401 Unauthorized."""

    def __init__(self, status_code: int = 401, www_authenticate: str = "", message: str = ""):
        self.status_code = status_code
        self.www_authenticate = www_authenticate
        msg = message or f"MCP server returned {status_code}"
        if www_authenticate:
            msg += f"\nWWW-Authenticate: {www_authenticate}"
        super().__init__(msg)


class MCPForbiddenError(MCPClientError):
    """Raised when an HTTP MCP server returns 403 Forbidden."""

    def __init__(self, scopes_required: list[str] | None = None, message: str = ""):
        self.scopes_required = scopes_required or []
        msg = message or "MCP server returned 403 Forbidden"
        if self.scopes_required:
            msg += f" (required scopes: {', '.join(self.scopes_required)})"
        super().__init__(msg)


@dataclass
class Icon:
    """MCP icon metadata (spec 2025-11-25)."""
    type: str
    data: str
    width: int | None = None
    height: int | None = None

    def is_valid(self) -> bool:
        return self.type in ("svg", "png") and len(self.data) > 0

    @classmethod
    def from_dict(cls, d: dict) -> Icon:
        return cls(
            type=d.get("type", ""),
            data=d.get("data", ""),
            width=d.get("width"),
            height=d.get("height"),
        )


@dataclass
class Content:
    """A single content block returned by a tool."""

    type: str
    text: str = ""
    data: str = ""
    mime_type: str = ""
    uri: str = ""
    resource: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> Content:
        resource = d.get("resource", {})
        return cls(
            type=d.get("type", "text"),
            text=d.get("text", resource.get("text", "")),
            data=d.get("data", ""),
            mime_type=d.get("mimeType", d.get("mime_type", "")),
            uri=d.get("uri", resource.get("uri", "")),
            resource=resource,
        )


@dataclass
class MCPError:
    """An error returned by the MCP server."""

    code: int
    message: str
    data: Any = None

    @classmethod
    def from_dict(cls, d: dict) -> MCPError:
        return cls(code=d.get("code", 0), message=d.get("message", ""), data=d.get("data"))


@dataclass
class ToolResult:
    """The result of calling an MCP tool."""

    content: list[Content]
    is_error_result: bool
    raw: dict
    _error: MCPError | None = field(default=None, repr=False)

    def is_ok(self) -> bool:
        return not self.is_error_result and self._error is None

    def is_error(self) -> bool:
        return self.is_error_result or self._error is not None

    @property
    def error(self) -> MCPError | None:
        return self._error

    def text(self) -> str:
        return "\n".join(c.text for c in self.content if c.type == "text")

    @classmethod
    def from_response(cls, response: dict) -> ToolResult:
        if "error" in response:
            err = MCPError.from_dict(response["error"])
            return cls(content=[], is_error_result=True, raw=response, _error=err)
        result = response.get("result", {})
        content_list = [Content.from_dict(c) for c in result.get("content", [])]
        is_err = result.get("isError", False)
        return cls(content=content_list, is_error_result=is_err, raw=response)


@dataclass
class ToolAnnotations:
    """Annotations providing hints about a tool's behavior."""

    title: str = ""
    read_only_hint: bool = False
    destructive_hint: bool = False
    idempotent_hint: bool = False
    open_world_hint: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> ToolAnnotations:
        return cls(
            title=d.get("title", ""),
            read_only_hint=d.get("readOnlyHint", False),
            destructive_hint=d.get("destructiveHint", False),
            idempotent_hint=d.get("idempotentHint", False),
            open_world_hint=d.get("openWorldHint", False),
        )


@dataclass
class ToolSchema:
    """Schema information for an MCP tool."""

    name: str
    title: str = ""
    description: str = ""
    input_schema: dict = field(default_factory=dict)
    output_schema: dict | None = None
    annotations: ToolAnnotations = field(default_factory=ToolAnnotations)
    icons: list[Icon] = field(default_factory=list)

    @property
    def required(self) -> list[str]:
        return self.input_schema.get("required", [])

    @property
    def properties(self) -> dict:
        return self.input_schema.get("properties", {})

    def has_valid_name(self) -> bool:
        return bool(TOOL_NAME_PATTERN.match(self.name))

    @classmethod
    def from_dict(cls, d: dict) -> ToolSchema:
        icons = [Icon.from_dict(i) for i in d.get("icons", [])]
        return cls(
            name=d.get("name", ""),
            title=d.get("title", ""),
            description=d.get("description", ""),
            input_schema=d.get("inputSchema", {}),
            output_schema=d.get("outputSchema"),
            annotations=ToolAnnotations.from_dict(d.get("annotations", {})),
            icons=icons,
        )


class ToolList:
    """A list of MCP tool schemas with lookup helpers."""

    def __init__(self, tools: list[ToolSchema]):
        self._tools = tools
        self._by_name = {t.name: t for t in tools}

    def find(self, name: str) -> ToolSchema | None:
        return self._by_name.get(name)

    def names(self) -> list[str]:
        return [t.name for t in self._tools]

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self):
        return iter(self._tools)

    @classmethod
    def from_response(cls, response: dict) -> ToolList:
        result = response.get("result", {})
        tools = [ToolSchema.from_dict(t) for t in result.get("tools", [])]
        return cls(tools)


@dataclass
class Resource:
    """An MCP resource."""

    uri: str
    name: str
    title: str = ""
    description: str = ""
    mime_type: str = ""
    size: int | None = None
    icons: list[Icon] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> Resource:
        icons = [Icon.from_dict(i) for i in d.get("icons", [])]
        return cls(
            uri=d.get("uri", ""),
            name=d.get("name", ""),
            title=d.get("title", ""),
            description=d.get("description", ""),
            mime_type=d.get("mimeType", ""),
            size=d.get("size"),
            icons=icons,
        )


@dataclass
class ResourceContent:
    """Content returned when reading a resource."""

    uri: str
    text: str = ""
    blob: str = ""
    mime_type: str = ""
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_response(cls, response: dict) -> ResourceContent:
        result = response.get("result", {})
        contents = result.get("contents", [])
        if contents:
            c = contents[0]
            return cls(
                uri=c.get("uri", ""),
                text=c.get("text", ""),
                blob=c.get("blob", ""),
                mime_type=c.get("mimeType", ""),
                raw=response,
            )
        return cls(uri="", raw=response)


@dataclass
class Prompt:
    """An MCP prompt template."""

    name: str
    title: str = ""
    description: str = ""
    arguments: list[dict] = field(default_factory=list)
    icons: list[Icon] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> Prompt:
        icons = [Icon.from_dict(i) for i in d.get("icons", [])]
        return cls(
            name=d.get("name", ""),
            title=d.get("title", ""),
            description=d.get("description", ""),
            arguments=d.get("arguments", []),
            icons=icons,
        )


@dataclass
class Task:
    """An experimental MCP task handle with full state machine."""

    id: str
    status: str
    output: dict | None = None
    error: dict | None = None
    elicitation_request: dict | None = None
    meta: dict = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")

    @property
    def needs_input(self) -> bool:
        return self.status == "input_required"

    @classmethod
    def from_response(cls, response: dict) -> Task | None:
        result = response.get("result", {})
        task = result.get("task")
        if task and isinstance(task, dict):
            return cls(
                id=task.get("id", ""),
                status=task.get("status", ""),
                output=task.get("output"),
                error=task.get("error"),
                elicitation_request=task.get("elicitationRequest"),
                meta=task.get("_meta", {}),
            )
        return None
