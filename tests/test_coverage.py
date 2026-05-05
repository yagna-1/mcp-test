
from __future__ import annotations

import os
import sys


from mcp_test import make_client
from mcp_test.coverage import CoverageTracker, CoverageReport, PrimitiveCoverage, print_coverage_report
from mcp_test.types import ToolSchema

ECHO_SERVER = os.path.join(os.path.dirname(__file__), "fixtures", "echo_server.py")
SERVER_CMD = f"{sys.executable} {ECHO_SERVER}"

def mock_tool(name: str) -> ToolSchema:
    return ToolSchema(name=name, description="", input_schema={}, output_schema={})

class MockToolList(list):
    pass


def test_tracker_register_tools():
    tracker = CoverageTracker()
    tools = MockToolList([mock_tool("echo"), mock_tool("search"), mock_tool("delete")])
    tracker.register_schemas(tools, [], [])
    report = tracker.report()
    assert report.total_tools == 3
    assert report.covered_tools == 0
    assert report.overall_percentage == 0.0


def test_tracker_record_calls():
    tracker = CoverageTracker()
    tools = MockToolList([mock_tool("echo"), mock_tool("search")])
    tracker.register_schemas(tools, [], [])
    tracker.record_call("tools", "echo", "test_echo")
    tracker.record_call("tools", "echo", "test_echo_2")

    report = tracker.report()
    assert report.total_tools == 2
    assert report.covered_tools == 1
    assert report.overall_percentage == 20.0


def test_tracker_full_coverage():
    tracker = CoverageTracker()
    tools = MockToolList([mock_tool("a"), mock_tool("b"), mock_tool("c")])
    tracker.register_schemas(tools, [], [])
    tracker.record_call("tools", "a")
    tracker.record_call("tools", "b")
    tracker.record_call("tools", "c")

    report = tracker.report()
    assert report.covered_tools == 3
    assert report.overall_percentage == 50.0
    assert report.uncovered_tools == []


def test_tracker_uncovered_tools():
    tracker = CoverageTracker()
    tools = MockToolList([mock_tool("a"), mock_tool("b"), mock_tool("c")])
    tracker.register_schemas(tools, [], [])
    tracker.record_call("tools", "a")

    report = tracker.report()
    assert set(report.uncovered_tools) == {"b", "c"}


def test_tool_coverage_dataclass():
    tc = PrimitiveCoverage(name="echo", call_count=3, test_names=["t1", "t2"])
    assert tc.is_covered
    assert tc.percentage == 100.0

    tc_zero = PrimitiveCoverage(name="unused")
    assert not tc_zero.is_covered
    assert tc_zero.percentage == 0.0


def test_coverage_report_empty():
    report = CoverageReport(tools=[], prompts=[], resources=[], client_features=[])
    assert report.total_tools == 0
    assert report.overall_percentage == 100.0


def test_print_coverage_report(capsys):
    tracker = CoverageTracker()
    tools = MockToolList([mock_tool("echo"), mock_tool("search")])
    tracker.register_schemas(tools, [], [])
    tracker.record_call("tools", "echo")
    report = tracker.report()
    print_coverage_report(report)


def test_coverage_with_real_server():
    with make_client(SERVER_CMD, timeout=5.0) as client:
        tools = client.list_tools()
        prompts = client.list_prompts()
        resources = client.list_resources()

        tracker = CoverageTracker()
        tracker.register_schemas(tools, prompts, resources)

        client.call_tool("echo", message="hi")
        client.call_tool("multi_content", count=2)

        for name in client.called_tools:
            tracker.record_call("tools", name)

        report = tracker.report()
        assert report.covered_tools >= 2
        assert "echo" not in report.uncovered_tools
        assert "multi_content" not in report.uncovered_tools
