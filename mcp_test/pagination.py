
from typing import Iterator

from .client import MCPTestClient
from .types import ToolSchema, Resource, Prompt


def list_tools_paginated(client: MCPTestClient) -> Iterator[ToolSchema]:
    cursor = None
    while True:
        params = {}
        if cursor:
            params["cursor"] = cursor
        response = client._request("tools/list", params)
        result = response.get("result", {})
        
        for t in result.get("tools", []):
            yield ToolSchema.from_dict(t)
            
        cursor = result.get("nextCursor")
        if not cursor:
            break


def list_resources_paginated(client: MCPTestClient) -> Iterator[Resource]:
    cursor = None
    while True:
        params = {}
        if cursor:
            params["cursor"] = cursor
        response = client._request("resources/list", params)
        result = response.get("result", {})
        
        for r in result.get("resources", []):
            yield Resource.from_dict(r)
            
        cursor = result.get("nextCursor")
        if not cursor:
            break


def list_prompts_paginated(client: MCPTestClient) -> Iterator[Prompt]:
    cursor = None
    while True:
        params = {}
        if cursor:
            params["cursor"] = cursor
        response = client._request("prompts/list", params)
        result = response.get("result", {})
        
        for p in result.get("prompts", []):
            yield Prompt.from_dict(p)
            
        cursor = result.get("nextCursor")
        if not cursor:
            break
