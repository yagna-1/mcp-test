
def test_pagination_helpers(mcp_client):
    c = mcp_client
    
    tools = c.list_tools()
    paginated_tools = list(c.list_tools_paginated())
    assert len(tools) == len(paginated_tools)
    assert tools.names() == [t.name for t in paginated_tools]
    
    resources = c.list_resources()
    paginated_resources = list(c.list_resources_paginated())
    assert len(resources) == len(paginated_resources)
    assert [r.name for r in resources] == [r.name for r in paginated_resources]
    
    prompts = c.list_prompts()
    paginated_prompts = list(c.list_prompts_paginated())
    assert len(prompts) == len(paginated_prompts)
    assert [p.name for p in prompts] == [p.name for p in paginated_prompts]

def test_subscriptions_and_logging(mcp_client):
    c = mcp_client
    
    res = c.subscribe_resource("file:///test")
    assert isinstance(res, dict)
    
    res = c.unsubscribe_resource("file:///test")
    assert isinstance(res, dict)
    
    res = c.set_logging_level("debug")
    assert isinstance(res, dict)

def test_capture_notifications(mcp_client):
    c = mcp_client
    
    with c.capture_notifications("notifications/progress") as capture:
        c.call_tool("slow_echo", _meta={"progressToken": "123"}, message="hello", delay=0.2)
        
    assert len(capture.collected) > 0
    assert "progress" in capture.collected[0]

def test_cancel_after(mcp_client):
    c = mcp_client
    
    with c.cancel_after(0.1):
        result = c.call_tool("slow_echo", message="hello", delay=2.0)
        
    assert result.is_error()
    assert result.error is not None
    assert result.error.code == -32800

def test_assert_schema_compliant(mcp_client):
    c = mcp_client
    
    c.assert_schema_compliant("echo")

