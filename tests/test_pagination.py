from mcp_test import MCPTestClient
from mcp_test.pagination import list_tools_paginated, list_resources_paginated, list_prompts_paginated

def test_pagination(mcp_client: MCPTestClient):
    tools = list(list_tools_paginated(mcp_client))
    assert len(tools) > 0
    assert any(t.name == "echo" for t in tools)
    
    resources = list(list_resources_paginated(mcp_client))
    assert len(resources) >= 1
    
    prompts = list(list_prompts_paginated(mcp_client))
    assert len(prompts) >= 1
