import pytest
from mcp_test.types import SPEC_VERSIONS


def test_spec_versions_contains_known_versions():
    assert "2024-11-05" in SPEC_VERSIONS
    assert "2025-03-26" in SPEC_VERSIONS
    assert "2025-06-18" in SPEC_VERSIONS
    assert "2025-11-25" in SPEC_VERSIONS


def test_spec_versions_ordering():
    assert SPEC_VERSIONS["2024-11-05"] < SPEC_VERSIONS["2025-03-26"]
    assert SPEC_VERSIONS["2025-03-26"] < SPEC_VERSIONS["2025-06-18"]
    assert SPEC_VERSIONS["2025-06-18"] < SPEC_VERSIONS["2025-11-25"]


def test_server_version_num(mcp_client):
    assert mcp_client.server_version_num >= 1


def test_server_capabilities_available(mcp_client):
    caps = mcp_client.server_capabilities
    assert isinstance(caps, dict)
    assert "tools" in caps or len(caps) > 0


def test_server_instructions_field(mcp_client):
    instructions = mcp_client.server_instructions
    assert isinstance(instructions, str)


@pytest.mark.mcp_v3
def test_v3_feature_audio_content(mcp_client):
    result = mcp_client.call_tool("audio_tool")
    assert result.is_ok()
    assert result.content[0].type == "audio"


@pytest.mark.mcp_v4
def test_v4_feature_task_input_required(mcp_client):
    result = mcp_client.call_tool("input_required_job")
    raw = result.raw.get("result", {})
    assert raw.get("task", {}).get("status") == "input_required"
