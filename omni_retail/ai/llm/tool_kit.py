"""Generic tool-registry infrastructure shared by every LLM tool set in
this codebase.

Extracted from `ai/llm/tools.py` (the admin registry) so a second,
independently-scoped registry -- `ai/llm/storefront_tools.py` -- can
reuse the exact same schema validation, JSON-safety, and dispatch
mechanics without duplicating them. Nothing here knows about "admin"
or "storefront"; each caller supplies its own `dict[str, ToolSpec]`
and gets back its own `get_schemas()`/`dispatch()` pair bound to that
registry, so two registries can never accidentally see each other's
tools.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session


class ToolError(Exception):
    """Base class for a malformed/unknown tool call -- recoverable:
    the orchestrator feeds the message back to the model as a tool
    error result rather than aborting the run."""


class UnknownToolError(ToolError):
    pass


class ToolArgumentError(ToolError):
    pass


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]
    read_only: bool = True


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {k: to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    return value


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any], tool_name: str) -> None:
    if not isinstance(arguments, dict):
        raise ToolArgumentError(f"{tool_name}: arguments must be a JSON object, got {type(arguments).__name__}.")

    for field_name in schema.get("required", []):
        if field_name not in arguments:
            raise ToolArgumentError(f"{tool_name}: missing required argument {field_name!r}.")

    properties = schema.get("properties", {})
    _type_map = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict, "array": list}
    for field_name, value in arguments.items():
        prop_schema = properties.get(field_name)
        if prop_schema is None:
            raise ToolArgumentError(f"{tool_name}: unexpected argument {field_name!r}.")
        expected_type = _type_map.get(prop_schema.get("type"))
        # bool is a subclass of int in Python -- exclude it from the "integer"/"number" check
        # so a stray `true` isn't silently accepted as a quantity.
        if expected_type is not None and (
            not isinstance(value, expected_type) or (expected_type in (int, (int, float)) and isinstance(value, bool))
        ):
            raise ToolArgumentError(
                f"{tool_name}: argument {field_name!r} must be of type {prop_schema.get('type')}, got {type(value).__name__}."
            )
        enum_values = prop_schema.get("enum")
        if enum_values is not None and value not in enum_values:
            raise ToolArgumentError(f"{tool_name}: argument {field_name!r} must be one of {enum_values}, got {value!r}.")

        minimum = prop_schema.get("minimum")
        if minimum is not None and isinstance(value, (int, float)) and not isinstance(value, bool) and value < minimum:
            raise ToolArgumentError(f"{tool_name}: argument {field_name!r} must be >= {minimum}, got {value!r}.")
        maximum = prop_schema.get("maximum")
        if maximum is not None and isinstance(value, (int, float)) and not isinstance(value, bool) and value > maximum:
            raise ToolArgumentError(f"{tool_name}: argument {field_name!r} must be <= {maximum}, got {value!r}.")


def build_schemas(registry: dict[str, ToolSpec]) -> list[dict[str, Any]]:
    return [{"name": spec.name, "description": spec.description, "input_schema": spec.input_schema} for spec in registry.values()]


def dispatch(registry: dict[str, ToolSpec], session: Session, name: str, arguments: dict[str, Any], **context: Any) -> str:
    """Runs one tool call against `registry` and returns its
    JSON-serialized result.

    Raises `UnknownToolError`/`ToolArgumentError` for a bad request
    from the model -- the orchestrator catches exactly these two and
    feeds them back as a tool error result. Any other exception (a
    genuine bug in a handler or the underlying service) is left to
    propagate, on purpose: it must not be mistaken for "the model
    asked for something invalid."

    `**context` is passed straight through to the handler as keyword
    arguments -- the admin registry's handlers expect `question`/
    `today`; the storefront registry's don't need either, so it just
    passes nothing extra.
    """
    spec = registry.get(name)
    if spec is None:
        raise UnknownToolError(f"No such tool {name!r}. Available tools: {', '.join(sorted(registry))}.")

    validate_arguments(spec.input_schema, arguments, name)
    result = spec.handler(session, arguments, **context)
    return json.dumps(result, default=str)


_EMPTY_SCHEMA = {"type": "object", "properties": {}, "required": []}
