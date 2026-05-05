
from __future__ import annotations

import random
import string
from typing import Any

from .types import ToolList, ToolSchema


class SchemaValidationError:
    """A single schema validation issue."""

    def __init__(self, tool_name: str, message: str, severity: str = "error"):
        self.tool_name = tool_name
        self.message = message
        self.severity = severity  # "error" | "warning"

    def __repr__(self) -> str:
        return f"SchemaValidationError({self.tool_name!r}, {self.message!r})"


def validate_tool_schema(tool: ToolSchema) -> list[SchemaValidationError]:
    errors: list[SchemaValidationError] = []
    schema = tool.input_schema

    if not schema:
        errors.append(SchemaValidationError(tool.name, "Missing inputSchema"))
        return errors

    if "type" not in schema:
        errors.append(SchemaValidationError(tool.name, "inputSchema missing 'type' field"))

    if schema.get("type") != "object":
        errors.append(SchemaValidationError(
            tool.name,
            f"inputSchema type should be 'object', got '{schema.get('type')}'",
        ))

    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for req in required:
        if req not in properties:
            errors.append(SchemaValidationError(
                tool.name,
                f"Required field '{req}' not found in properties",
            ))

    for prop_name, prop_schema in properties.items():
        if "type" not in prop_schema:
            errors.append(SchemaValidationError(
                tool.name,
                f"Property '{prop_name}' missing 'type' field",
                severity="warning",
            ))

    if not properties and not required:
        errors.append(SchemaValidationError(
            tool.name,
            "inputSchema has no properties and no required fields",
            severity="warning",
        ))

    return errors


def validate_schemas(tools: ToolList) -> list[SchemaValidationError]:
    errors: list[SchemaValidationError] = []
    for tool in tools:
        errors.extend(validate_tool_schema(tool))
    return errors


def _generate_value_for_type(type_str: str, prop_schema: dict | None = None) -> Any:
    if type_str == "string":
        enum = (prop_schema or {}).get("enum")
        if enum:
            return enum[0]
        return "test_" + "".join(random.choices(string.ascii_lowercase, k=5))
    elif type_str == "integer":
        minimum = (prop_schema or {}).get("minimum", 0)
        maximum = (prop_schema or {}).get("maximum", 100)
        return random.randint(int(minimum), int(maximum))
    elif type_str == "number":
        return round(random.uniform(0, 100), 2)
    elif type_str == "boolean":
        return True
    elif type_str == "array":
        items = (prop_schema or {}).get("items", {})
        item_type = items.get("type", "string")
        return [_generate_value_for_type(item_type)]
    elif type_str == "object":
        return {}
    elif type_str == "null":
        return None
    else:
        return "test_value"


def _generate_invalid_value_for_type(type_str: str) -> Any:
    if type_str == "string":
        return 12345
    elif type_str in ("integer", "number"):
        return "not_a_number"
    elif type_str == "boolean":
        return "not_a_bool"
    elif type_str == "array":
        return "not_an_array"
    elif type_str == "object":
        return "not_an_object"
    else:
        return None


def generate_valid_inputs(tool: ToolSchema) -> dict[str, Any]:
    properties = tool.properties
    required = tool.required
    args: dict[str, Any] = {}

    for prop_name in required:
        prop_schema = properties.get(prop_name, {})
        prop_type = prop_schema.get("type", "string")
        args[prop_name] = _generate_value_for_type(prop_type, prop_schema)

    return args


def generate_invalid_inputs_missing_required(tool: ToolSchema) -> list[dict[str, Any]]:
    invalid_cases: list[dict[str, Any]] = []
    valid = generate_valid_inputs(tool)

    for req_field in tool.required:
        case = {k: v for k, v in valid.items() if k != req_field}
        invalid_cases.append(case)

    return invalid_cases


def generate_invalid_inputs_wrong_types(tool: ToolSchema) -> list[dict[str, Any]]:
    invalid_cases: list[dict[str, Any]] = []
    valid = generate_valid_inputs(tool)

    for req_field in tool.required:
        prop_schema = tool.properties.get(req_field, {})
        prop_type = prop_schema.get("type", "string")
        case = valid.copy()
        case[req_field] = _generate_invalid_value_for_type(prop_type)
        invalid_cases.append(case)

    return invalid_cases


def hypothesis_strategy_for_tool(tool: ToolSchema):
    """Return a Hypothesis strategy for valid inputs when Hypothesis is installed."""

    try:
        from hypothesis import strategies as st
    except ImportError as exc:
        raise RuntimeError(
            "hypothesis is required for property-based contract tests"
        ) from exc

    fields: dict[str, Any] = {}
    for name, prop_schema in tool.properties.items():
        if name in tool.required:
            fields[name] = _hypothesis_strategy_for_schema(prop_schema, st)
    return st.fixed_dictionaries(fields)


def _hypothesis_strategy_for_schema(prop_schema: dict, st):
    prop_type = prop_schema.get("type", "string")
    enum = prop_schema.get("enum")
    if enum:
        return st.sampled_from(enum)
    if prop_type == "string":
        return st.text(min_size=1, max_size=128)
    if prop_type == "integer":
        minimum = int(prop_schema.get("minimum", -1000))
        maximum = int(prop_schema.get("maximum", 1000))
        return st.integers(min_value=minimum, max_value=maximum)
    if prop_type == "number":
        minimum = float(prop_schema.get("minimum", -1000))
        maximum = float(prop_schema.get("maximum", 1000))
        return st.floats(min_value=minimum, max_value=maximum, allow_nan=False, allow_infinity=False)
    if prop_type == "boolean":
        return st.booleans()
    if prop_type == "array":
        item_schema = prop_schema.get("items", {"type": "string"})
        return st.lists(_hypothesis_strategy_for_schema(item_schema, st), max_size=10)
    if prop_type == "object":
        return st.dictionaries(st.text(min_size=1, max_size=32), st.text(max_size=128), max_size=10)
    if prop_type == "null":
        return st.none()
    return st.text(min_size=1, max_size=128)


class ContractTestResult:
    """Result of contract testing a tool."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        self.valid_input_passed: bool = False
        self.invalid_input_results: list[tuple[str, bool, str]] = []
        self.errors: list[str] = []

    @property
    def passed(self) -> bool:
        if not self.valid_input_passed:
            return False
        return all(passed for _, passed, _ in self.invalid_input_results)

    @property
    def total_checks(self) -> int:
        return 1 + len(self.invalid_input_results)

    @property
    def passed_checks(self) -> int:
        count = 1 if self.valid_input_passed else 0
        count += sum(1 for _, passed, _ in self.invalid_input_results if passed)
        return count
