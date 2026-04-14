"""Authoritative JSON Schema for qdo workflow YAML files.

The schema is intentionally strict: ``additionalProperties: false`` on every
object so agents authoring workflows get a clear error when they invent a
field, rather than the field being silently ignored.

Only declarative constructs are permitted.  ``run`` must begin with ``qdo``
— no shell escape, no embedded Python.  Runtime/lint-time checks (unknown
captures, unresolved references, unsafe commands) belong in Phase 4.2; this
file covers structural validation only.
"""

from __future__ import annotations

from typing import Any

WORKFLOW_SPEC_VERSION = 1

_IDENTIFIER = r"^[a-z][a-z0-9_]*$"
_SLUG = r"^[a-z][a-z0-9-]*$"
_SEMVER = r"^\d+\.\d+(\.\d+)?$"
_QDO_INVOCATION = r"^qdo\s+\S+"

WORKFLOW_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://querido.dev/schemas/workflow/v1.json",
    "title": "qdo workflow",
    "description": (
        "Declarative YAML describing a parameterized sequence of qdo commands. "
        "Workflows are files, not code: only qdo invocations, typed inputs, "
        "captured step outputs, and simple conditionals are permitted."
    ),
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "description", "version", "steps"],
    "properties": {
        "name": {
            "type": "string",
            "pattern": _SLUG,
            "description": "Slug used to invoke the workflow (lowercase, hyphens).",
        },
        "description": {
            "type": "string",
            "minLength": 1,
            "description": "One-line human-readable description.",
        },
        "version": {
            "type": "integer",
            "minimum": 1,
            "description": "Workflow version (author-controlled; bump on breaking changes).",
        },
        "qdo_min_version": {
            "type": "string",
            "pattern": _SEMVER,
            "description": "Minimum qdo version required to run this workflow.",
        },
        "inputs": {
            "type": "object",
            "description": "Typed inputs bound into step ${...} expressions.",
            "additionalProperties": {"$ref": "#/$defs/input"},
        },
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/step"},
            "description": "Ordered list of qdo invocations.",
        },
        "outputs": {
            "type": "object",
            "description": (
                "Named values exposed to callers. Each value is an expression "
                "referencing inputs or captured step outputs (e.g. "
                "``${schema.row_count}``)."
            ),
            "additionalProperties": {"type": "string", "minLength": 1},
        },
    },
    "$defs": {
        "input": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type"],
            "properties": {
                "type": {
                    "type": "string",
                    "enum": [
                        "string",
                        "integer",
                        "number",
                        "boolean",
                        "table",
                        "connection",
                    ],
                    "description": (
                        "Value type. ``table``/``connection`` are validated "
                        "against the target config at run time."
                    ),
                },
                "required": {"type": "boolean", "default": False},
                "default": {
                    "description": (
                        "Default value used when the caller omits this input. "
                        "Must match the declared type."
                    ),
                },
                "description": {"type": "string"},
            },
        },
        "step": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "run"],
            "properties": {
                "id": {
                    "type": "string",
                    "pattern": _IDENTIFIER,
                    "description": (
                        "Unique step identifier (used as capture name if no capture given)."
                    ),
                },
                "run": {
                    "type": "string",
                    "pattern": _QDO_INVOCATION,
                    "description": (
                        "qdo invocation. Must begin with ``qdo``; arguments may "
                        "use ``${input}`` and ``${step.field}`` interpolations."
                    ),
                },
                "capture": {
                    "type": "string",
                    "pattern": _IDENTIFIER,
                    "description": "Variable name to bind the step's JSON output to.",
                },
                "when": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Expression deciding whether to run this step "
                        "(e.g. ``${schema.row_count} > 0``)."
                    ),
                },
                "allow_write": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Must be true for any step that can mutate the target "
                        "(matches the query-command ``--allow-write`` guardrail)."
                    ),
                },
            },
        },
    },
}


__all__ = ["WORKFLOW_SCHEMA", "WORKFLOW_SPEC_VERSION"]
