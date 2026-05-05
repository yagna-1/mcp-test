
from __future__ import annotations

import os
import sys


from mcp_test import make_client, validate_schemas, validate_tool_schema
from mcp_test.schema_validator import (
    generate_valid_inputs,
    generate_invalid_inputs_missing_required,
    generate_invalid_inputs_wrong_types,
    ContractTestResult,
)
from mcp_test.types import ToolSchema

ECHO_SERVER = os.path.join(os.path.dirname(__file__), "fixtures", "echo_server.py")
SERVER_CMD = f"{sys.executable} {ECHO_SERVER}"


def test_validate_valid_schema():
    tool = ToolSchema(
        name="search",
        description="Search",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    errors = validate_tool_schema(tool)
    assert len([e for e in errors if e.severity == "error"]) == 0


def test_validate_missing_type():
    tool = ToolSchema(name="bad", description="Bad", input_schema={"properties": {}})
    errors = validate_tool_schema(tool)
    assert any("missing 'type'" in e.message for e in errors)


def test_validate_wrong_type():
    tool = ToolSchema(name="bad", description="Bad", input_schema={"type": "array"})
    errors = validate_tool_schema(tool)
    assert any("should be 'object'" in e.message for e in errors)


def test_validate_required_not_in_properties():
    tool = ToolSchema(
        name="bad",
        description="Bad",
        input_schema={
            "type": "object",
            "properties": {},
            "required": ["ghost_field"],
        },
    )
    errors = validate_tool_schema(tool)
    assert any("ghost_field" in e.message for e in errors)


def test_validate_missing_input_schema():
    tool = ToolSchema(name="empty", description="Empty", input_schema={})
    errors = validate_tool_schema(tool)
    assert len(errors) > 0


def test_validate_all_schemas_on_echo_server():
    with make_client(SERVER_CMD, timeout=5.0) as client:
        tools = client.list_tools()
        errors = validate_schemas(tools)
        # echo server schemas are well-formed, only warnings expected
        hard_errors = [e for e in errors if e.severity == "error"]
        assert len(hard_errors) == 0, f"Unexpected errors: {hard_errors}"


def test_generate_valid_inputs():
    tool = ToolSchema(
        name="search",
        description="Search",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query", "limit"],
        },
    )
    inputs = generate_valid_inputs(tool)
    assert "query" in inputs
    assert "limit" in inputs
    assert isinstance(inputs["query"], str)
    assert isinstance(inputs["limit"], int)


def test_generate_invalid_inputs_missing_required():
    tool = ToolSchema(
        name="search",
        description="Search",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query", "limit"],
        },
    )
    cases = generate_invalid_inputs_missing_required(tool)
    assert len(cases) == 2
    assert any("query" not in c for c in cases)
    assert any("limit" not in c for c in cases)


def test_generate_invalid_inputs_wrong_types():
    tool = ToolSchema(
        name="search",
        description="Search",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["query", "count"],
        },
    )
    cases = generate_invalid_inputs_wrong_types(tool)
    assert len(cases) == 2


def test_contract_test_result():
    r = ContractTestResult("test_tool")
    r.valid_input_passed = True
    r.invalid_input_results = [("missing query", True, "ok"), ("wrong type", False, "fail")]
    assert r.total_checks == 3
    assert r.passed_checks == 2
    assert not r.passed
