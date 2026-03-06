
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .types import ToolResult, ToolList


console = Console()


def print_tool_result(result: ToolResult, tool_name: str = "") -> None:
    if result.is_ok():
        title = f"✅ {tool_name}" if tool_name else "✅ Tool Result"
        style = "green"
    else:
        title = f"❌ {tool_name}" if tool_name else "❌ Tool Error"
        style = "red"

    lines: list[str] = []

    if result.error:
        lines.append(f"Error code: {result.error.code}")
        lines.append(f"Error message: {result.error.message}")
    else:
        for i, content in enumerate(result.content):
            if content.type == "text":
                lines.append(content.text)
            elif content.type == "image":
                lines.append(f"[image: {content.mime_type}, {len(content.data)} bytes]")
            elif content.type == "resource":
                lines.append(f"[resource: {content.uri}]")

    body = "\n".join(lines) if lines else "(empty)"
    console.print(Panel(body, title=title, border_style=style))


def print_tool_list(tools: ToolList) -> None:
    table = Table(title="MCP Tools", show_lines=True)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")
    table.add_column("Required Params", style="yellow")

    for tool in tools:
        required = ", ".join(tool.required) if tool.required else "—"
        table.add_row(tool.name, tool.description, required)

    console.print(table)


def print_success(message: str) -> None:
    console.print(Text(f"✅ {message}", style="bold green"))


def print_error(message: str) -> None:
    console.print(Text(f"❌ {message}", style="bold red"))


def print_warning(message: str) -> None:
    console.print(Text(f"⚠️  {message}", style="bold yellow"))
