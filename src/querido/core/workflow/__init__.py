"""Workflow spec, loader, runner, and lint.

Phase 4.1 shipped the spec + bundled examples; Phase 4.2 added the
runner, lint, list, and show.  See sibling modules for implementation:

- :mod:`~querido.core.workflow.spec` — authoritative JSON Schema
- :mod:`~querido.core.workflow.loader` — file discovery and parsing
- :mod:`~querido.core.workflow.lint` — structural + semantic checks
- :mod:`~querido.core.workflow.runner` — end-to-end execution
- :mod:`~querido.core.workflow.expr` — tiny expression evaluator
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
