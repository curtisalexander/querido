"""Workflow file discovery and parsing.

Workflows live in three tiers, searched in order:

1. ``./.qdo/workflows/<name>.yaml`` — project-scoped (checked into git).
2. ``<user-config>/qdo/workflows/<name>.yaml`` — user-scoped.
3. Bundled examples in :mod:`querido.core.workflow.examples`.

The first match wins, so a project workflow can override a bundled one
with the same name.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkflowEntry:
    """A discovered workflow — its name, source tier, and origin path."""

    name: str
    source: str  # "project" | "user" | "bundled"
    path: Path
    description: str


def project_workflows_dir(cwd: Path | None = None) -> Path:
    """Return the project-scoped workflows dir (``./.qdo/workflows``)."""
    return (cwd or Path.cwd()) / ".qdo" / "workflows"


def user_workflows_dir() -> Path:
    """Return the user-scoped workflows dir under the qdo config directory."""
    from querido.config import get_config_dir

    return get_config_dir() / "workflows"


def _bundled_entries() -> list[tuple[str, Path]]:
    pkg = resources.files("querido.core.workflow").joinpath("examples")
    return [
        (entry.name.removesuffix(".yaml"), Path(str(entry)))
        for entry in sorted(pkg.iterdir(), key=lambda p: p.name)
        if entry.name.endswith(".yaml") and entry.is_file()
    ]


def _dir_entries(dir_: Path) -> list[tuple[str, Path]]:
    if not dir_.is_dir():
        return []
    return [
        (p.stem, p)
        for p in sorted(dir_.iterdir(), key=lambda p: p.name)
        if p.suffix == ".yaml" and p.is_file()
    ]


def list_available_workflows(cwd: Path | None = None) -> list[WorkflowEntry]:
    """Return every discoverable workflow across the three tiers.

    Tier precedence is respected — when the same name appears in multiple
    tiers, only the highest-precedence one is returned.
    """
    seen: set[str] = set()
    out: list[WorkflowEntry] = []
    tiers = (
        ("project", _dir_entries(project_workflows_dir(cwd))),
        ("user", _dir_entries(user_workflows_dir())),
        ("bundled", _bundled_entries()),
    )
    for source, entries in tiers:
        for name, path in entries:
            if name in seen:
                continue
            seen.add(name)
            description = _peek_description(path)
            out.append(WorkflowEntry(name=name, source=source, path=path, description=description))
    out.sort(key=lambda e: e.name)
    return out


def resolve_workflow(name_or_path: str, cwd: Path | None = None) -> WorkflowEntry:
    """Return the workflow matching *name_or_path*.

    A value that looks like a file path (contains a separator or ``.yaml``
    suffix) is resolved directly; otherwise it's looked up by name across
    the three tiers.
    """
    candidate = Path(name_or_path)
    if candidate.suffix == ".yaml" or "/" in name_or_path or candidate.is_file():
        if not candidate.is_file():
            raise FileNotFoundError(f"Workflow file not found: {name_or_path}")
        return WorkflowEntry(
            name=candidate.stem,
            source="file",
            path=candidate,
            description=_peek_description(candidate),
        )

    for entry in list_available_workflows(cwd):
        if entry.name == name_or_path:
            return entry
    raise FileNotFoundError(
        f"Workflow not found: {name_or_path!r}. "
        "Run 'qdo workflow list' to see available workflows."
    )


def load_workflow_doc(path: Path) -> dict[str, Any]:
    """Read and YAML-parse a workflow file. Returns the raw dict."""
    import yaml

    text = path.read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict):
        raise ValueError(f"Workflow at {path} must be a YAML mapping at the top level.")
    return doc


def _peek_description(path: Path) -> str:
    """Best-effort description extraction without fully parsing."""
    try:
        import yaml

        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if isinstance(doc, dict):
        desc = doc.get("description")
        if isinstance(desc, str):
            return desc
    return ""


__all__ = [
    "WorkflowEntry",
    "list_available_workflows",
    "load_workflow_doc",
    "project_workflows_dir",
    "resolve_workflow",
    "user_workflows_dir",
]
