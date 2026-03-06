
import os
import sys

import pytest
from mcp_test import make_client, assert_tool_ok, assert_tool_error, assert_tool_text_contains

SERVER = os.path.join(os.path.dirname(__file__), "server.py")
CMD = f"{sys.executable} {SERVER}"


@pytest.fixture(scope="module")
def client():
    with make_client(CMD, timeout=5.0) as c:
        yield c


def test_list_tools(client):
    tools = client.list_tools()
    assert "get_weather" in tools.names()
    assert "get_forecast" in tools.names()


def test_get_weather_valid_city(client):
    result = client.call_tool("get_weather", city="London")
    assert_tool_ok(result)
    assert_tool_text_contains(result, "London")
    assert_tool_text_contains(result, "°C")


def test_get_weather_unknown_city(client):
    result = client.call_tool("get_weather", city="Atlantis")
    assert_tool_error(result)
    assert_tool_text_contains(result, "City not found")


def test_get_forecast(client):
    result = client.call_tool("get_forecast", city="Tokyo", days=3)
    assert_tool_ok(result)
    assert_tool_text_contains(result, "Tokyo")
    assert_tool_text_contains(result, "Day 1")
    assert_tool_text_contains(result, "Day 3")


def test_forecast_invalid_days(client):
    result = client.call_tool("get_forecast", city="London", days=10)
    assert_tool_error(result)


def test_weather_schema(client):
    tools = client.list_tools()
    weather = tools.find("get_weather")
    assert weather is not None
    assert weather.required == ["city"]
    assert weather.properties["city"]["type"] == "string"
