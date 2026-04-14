"""Workflow linting — structural + semantic checks.

The JSON Schema covers structural validation (field names, types, patterns).
This module layers semantic checks on top: duplicate step ids, unresolved
``${refs}``, use-before-define, destructive ``qdo query`` without
``allow_write: true``, etc.

Every issue is returned as a ``LintIssue`` with ``code``, ``message``,
``fix`` (a hint) and an optional ``path`` pointer into the document, so
agents can act on structured failures.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import asdict, dataclass, field
from typing import Any

from querido.core.workflow.expr import REF_RE

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_SLUG = re.compile(r"^[a-z][a-z0-9-]*$")
_SEMVER = re.compile(r"^\d+\.\d+(\.\d+)?$")
_QDO_INVOCATION = re.compile(r"^qdo\s+\S+")

# Matches SQL statements that mutate state. Used by the allow_write lint.
_DESTRUCTIVE_SQL = re.compile(
    r"\b(insert|update|delete|drop|create|alter|truncate|merge|replace|grant|revoke)\b",
    re.IGNORECASE,
)

_VALID_INPUT_TYPES = {"string", "integer", "number", "boolean", "table", "connection"}


@dataclass
class LintIssue:
    """One lint failure. ``path`` is a JSON-Pointer-ish slash path."""

    code: str
    message: str
    fix: str = ""
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v != ""}


@dataclass
class LintResult:
    issues: list[LintIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def add(self, code: str, message: str, fix: str = "", path: str = "") -> None:
        self.issues.append(LintIssue(code=code, message=message, fix=fix, path=path))


def lint(doc: Any) -> LintResult:
    """Return a ``LintResult`` with every structural and semantic issue."""
    result = LintResult()
    if not isinstance(doc, dict):
        result.add(
            "NOT_A_MAPPING",
            "workflow root must be a YAML mapping",
            fix="wrap the document in top-level keys (name, description, version, steps)",
        )
        return result

    _check_top_level(doc, result)
    _check_inputs(doc, result)
    steps = doc.get("steps")
    if isinstance(steps, list):
        _check_steps(steps, doc, result)
    _check_outputs(doc, steps if isinstance(steps, list) else [], result)
    return result


def _check_top_level(doc: dict[str, Any], result: LintResult) -> None:
    for required in ("name", "description", "version", "steps"):
        if required not in doc:
            result.add(
                "MISSING_FIELD",
                f"missing required field: {required!r}",
                fix=f"add a top-level {required!r} entry",
                path=f"/{required}",
            )

    name = doc.get("name")
    if isinstance(name, str) and not _SLUG.match(name):
        result.add(
            "INVALID_NAME",
            f"name {name!r} must be a lowercase-hyphen slug",
            fix="use only lowercase letters, digits, and hyphens (start with a letter)",
            path="/name",
        )

    description = doc.get("description")
    if "description" in doc and (not isinstance(description, str) or not description.strip()):
        result.add(
            "INVALID_DESCRIPTION",
            "description must be a non-empty string",
            fix="write a one-line human-readable description",
            path="/description",
        )

    version = doc.get("version")
    if "version" in doc and (not isinstance(version, int) or version < 1):
        result.add(
            "INVALID_VERSION",
            "version must be a positive integer",
            fix="use an integer >= 1 (bump on breaking changes)",
            path="/version",
        )

    qmin = doc.get("qdo_min_version")
    if qmin is not None and (not isinstance(qmin, str) or not _SEMVER.match(qmin)):
        result.add(
            "INVALID_QDO_MIN_VERSION",
            "qdo_min_version must look like ``X.Y`` or ``X.Y.Z``",
            fix="use a semver string, e.g. '0.1.0'",
            path="/qdo_min_version",
        )

    for unknown in set(doc) - {
        "name",
        "description",
        "version",
        "qdo_min_version",
        "inputs",
        "steps",
        "outputs",
    }:
        result.add(
            "UNKNOWN_FIELD",
            f"unknown top-level field: {unknown!r}",
            fix="remove the field (workflow schema forbids extras)",
            path=f"/{unknown}",
        )


def _check_inputs(doc: dict[str, Any], result: LintResult) -> None:
    inputs = doc.get("inputs")
    if inputs is None:
        return
    if not isinstance(inputs, dict):
        result.add(
            "INVALID_INPUTS",
            "inputs must be a mapping of name -> input spec",
            path="/inputs",
        )
        return
    for name, spec in inputs.items():
        base = f"/inputs/{name}"
        if not isinstance(name, str) or not _IDENTIFIER.match(name):
            result.add(
                "INVALID_INPUT_NAME",
                f"input name {name!r} must match [a-z][a-z0-9_]*",
                path=base,
            )
            continue
        if not isinstance(spec, dict):
            result.add(
                "INVALID_INPUT",
                f"input {name!r} must be a mapping",
                path=base,
            )
            continue
        type_ = spec.get("type")
        if type_ not in _VALID_INPUT_TYPES:
            result.add(
                "INVALID_INPUT_TYPE",
                f"input {name!r} has invalid type {type_!r}",
                fix=f"use one of: {', '.join(sorted(_VALID_INPUT_TYPES))}",
                path=f"{base}/type",
            )
        for unknown in set(spec) - {"type", "required", "default", "description"}:
            result.add(
                "UNKNOWN_INPUT_FIELD",
                f"input {name!r} has unknown field {unknown!r}",
                path=f"{base}/{unknown}",
            )


def _check_steps(steps: list[Any], doc: dict[str, Any], result: LintResult) -> None:
    if not steps:
        result.add("EMPTY_STEPS", "steps must have at least one entry", path="/steps")
        return

    input_names = set(doc.get("inputs") or {})
    defined: set[str] = set(input_names)
    seen_ids: set[str] = set()

    for i, step in enumerate(steps):
        base = f"/steps/{i}"
        if not isinstance(step, dict):
            result.add("INVALID_STEP", "step must be a mapping", path=base)
            continue

        for unknown in set(step) - {"id", "run", "capture", "when", "allow_write"}:
            result.add(
                "UNKNOWN_STEP_FIELD",
                f"step has unknown field {unknown!r}",
                path=f"{base}/{unknown}",
            )

        step_id = step.get("id")
        if not isinstance(step_id, str) or not _IDENTIFIER.match(step_id):
            result.add(
                "INVALID_STEP_ID",
                f"step id {step_id!r} must match [a-z][a-z0-9_]*",
                path=f"{base}/id",
            )
            step_id = None
        elif step_id in seen_ids:
            result.add(
                "DUPLICATE_STEP_ID",
                f"duplicate step id {step_id!r}",
                fix="give each step a unique id",
                path=f"{base}/id",
            )
        else:
            seen_ids.add(step_id)

        run = step.get("run")
        if not isinstance(run, str) or not _QDO_INVOCATION.match(run):
            result.add(
                "INVALID_RUN",
                "step.run must be a string beginning with 'qdo '",
                fix="rewrite as 'qdo <subcommand> ...' — no shell escape, no embedded python",
                path=f"{base}/run",
            )
            run = ""

        capture = step.get("capture")
        if capture is not None:
            if not isinstance(capture, str) or not _IDENTIFIER.match(capture):
                result.add(
                    "INVALID_CAPTURE",
                    f"capture name {capture!r} must match [a-z][a-z0-9_]*",
                    path=f"{base}/capture",
                )
                capture = None
            elif capture in defined:
                result.add(
                    "CAPTURE_SHADOWS",
                    f"capture {capture!r} shadows an earlier input or capture",
                    fix="choose a unique capture name",
                    path=f"{base}/capture",
                )

        # ${ref} checks on run/when
        for field_name in ("run", "when"):
            value = step.get(field_name)
            if isinstance(value, str):
                for ref in _iter_refs(value):
                    root = ref.split(".")[0]
                    if root not in defined:
                        result.add(
                            "UNRESOLVED_REFERENCE",
                            f"reference ${{{ref}}} is not defined at this point",
                            fix="declare it as an input or capture it in an earlier step",
                            path=f"{base}/{field_name}",
                        )

        # allow_write check: if the run line invokes ``qdo query`` with a
        # destructive SQL pattern, require allow_write=true.
        if isinstance(run, str) and _is_write_query(run) and not step.get("allow_write", False):
            result.add(
                "WRITE_WITHOUT_ALLOW",
                "step runs a destructive SQL but allow_write is false",
                fix="set 'allow_write: true' on this step (and confirm the intent)",
                path=f"{base}/allow_write",
            )

        # Record what's available to subsequent steps.
        if step_id:
            defined.add(step_id)
        if capture:
            defined.add(capture)


def _check_outputs(doc: dict[str, Any], steps: list[Any], result: LintResult) -> None:
    outputs = doc.get("outputs")
    if outputs is None:
        return
    if not isinstance(outputs, dict):
        result.add("INVALID_OUTPUTS", "outputs must be a mapping", path="/outputs")
        return

    defined: set[str] = set(doc.get("inputs") or {})
    for step in steps:
        if isinstance(step, dict):
            sid = step.get("id")
            if isinstance(sid, str):
                defined.add(sid)
            cap = step.get("capture")
            if isinstance(cap, str):
                defined.add(cap)

    for key, expr in outputs.items():
        base = f"/outputs/{key}"
        if not isinstance(key, str) or not _IDENTIFIER.match(key):
            result.add("INVALID_OUTPUT_NAME", f"output name {key!r} is invalid", path=base)
            continue
        if not isinstance(expr, str) or not expr.strip():
            result.add("INVALID_OUTPUT", f"output {key!r} must be a non-empty string", path=base)
            continue
        for ref in _iter_refs(expr):
            root = ref.split(".")[0]
            if root not in defined:
                result.add(
                    "UNRESOLVED_REFERENCE",
                    f"output {key!r} references ${{{ref}}} which is not defined",
                    fix="reference an input or a step id/capture",
                    path=base,
                )


def _iter_refs(s: str) -> list[str]:
    return [m.group(1) for m in REF_RE.finditer(s)]


def _is_write_query(run: str) -> bool:
    """Return True if the ``run`` line invokes ``qdo query`` with destructive SQL."""
    try:
        tokens = shlex.split(run)
    except ValueError:
        return False
    if len(tokens) < 2 or tokens[0] != "qdo" or tokens[1] != "query":
        return False
    return bool(_DESTRUCTIVE_SQL.search(run))


__all__ = ["LintIssue", "LintResult", "lint"]
