"""Workflow spec and (future) runner.

Phase 4.1 ships only the spec and bundled examples; runner/lint land in
later phases.  See :mod:`querido.core.workflow.spec` for the authoritative
JSON Schema and :func:`load_examples` for the bundled example YAML files.
"""

from __future__ import annotations

from importlib import resources

from .spec import WORKFLOW_SCHEMA, WORKFLOW_SPEC_VERSION


def load_examples() -> dict[str, str]:
    """Return bundled example workflows as ``{filename: yaml_text}``.

    Examples are ordered by filename so callers get stable output.
    """
    pkg = resources.files(__package__).joinpath("examples")
    out: dict[str, str] = {}
    for entry in sorted(pkg.iterdir(), key=lambda p: p.name):
        if entry.name.endswith(".yaml") and entry.is_file():
            out[entry.name] = entry.read_text(encoding="utf-8")
    return out


__all__ = ["WORKFLOW_SCHEMA", "WORKFLOW_SPEC_VERSION", "load_examples"]
