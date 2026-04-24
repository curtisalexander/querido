"""qdo agent — show or install coding-agent integration docs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Show or install coding-agent integration docs.")


@dataclass(frozen=True)
class AgentFile:
    source: str
    destination: str


@dataclass(frozen=True)
class AgentTarget:
    description: str
    default_path: Path | None
    files: tuple[AgentFile, ...]


_TARGETS: dict[str, AgentTarget] = {
    "skill": AgentTarget(
        description="Claude Code skill files.",
        default_path=Path("skills/querido"),
        files=(
            AgentFile("skills/SKILL.md", "SKILL.md"),
            AgentFile("skills/WORKFLOW_AUTHORING.md", "WORKFLOW_AUTHORING.md"),
            AgentFile("skills/WORKFLOW_EXAMPLES.md", "WORKFLOW_EXAMPLES.md"),
        ),
    ),
    "continue": AgentTarget(
        description="Continue.dev rule file.",
        default_path=Path(".continue/rules"),
        files=(AgentFile("continue/qdo.md", "qdo.md"),),
    ),
    "workflow-authoring": AgentTarget(
        description="Workflow authoring reference for agents.",
        default_path=None,
        files=(AgentFile("skills/WORKFLOW_AUTHORING.md", "WORKFLOW_AUTHORING.md"),),
    ),
    "workflow-examples": AgentTarget(
        description="Worked workflow examples for agents.",
        default_path=None,
        files=(AgentFile("skills/WORKFLOW_EXAMPLES.md", "WORKFLOW_EXAMPLES.md"),),
    ),
}

_INSTALL_PATH_OPTION = typer.Option(
    None,
    "--path",
    "-p",
    help="Destination directory. Defaults to the target's conventional project path.",
)


def _target_names() -> str:
    return ", ".join(sorted(_TARGETS))


def _repo_integration_path(relative: str) -> Path:
    return Path(__file__).resolve().parents[3] / "integrations" / relative


def _read_agent_file(relative: str) -> str:
    repo_path = _repo_integration_path(relative)
    if repo_path.exists():
        return repo_path.read_text()

    from importlib.resources import files

    resource = files("querido.agent_docs")
    for part in relative.split("/"):
        resource = resource.joinpath(part)
    return resource.read_text()


def _get_target(name: str) -> AgentTarget:
    key = name.lower()
    if key not in _TARGETS:
        raise typer.BadParameter(f"Unknown target: {name!r}. Must be one of: {_target_names()}")
    return _TARGETS[key]


@app.command("list")
@friendly_errors
def list_targets() -> None:
    """List installable agent integration targets."""
    from querido.output.envelope import emit_envelope, is_structured_format

    rows: list[dict[str, object]] = [
        {
            "name": name,
            "kind": "installable" if target.default_path else "reference",
            "installable": target.default_path is not None,
            "description": target.description,
            "default_path": str(target.default_path) if target.default_path else None,
            "files": [file.destination for file in target.files],
        }
        for name, target in sorted(_TARGETS.items())
    ]

    if is_structured_format():
        emit_envelope(command="agent list", data={"targets": rows})
        return

    from rich.console import Console
    from rich.table import Table

    table = Table(title="Agent Integration Docs")
    table.add_column("Target", style="cyan bold")
    table.add_column("Kind", style="magenta")
    table.add_column("Description")
    table.add_column("Default install path", style="dim")
    table.add_column("Files", style="green")
    for name, target in sorted(_TARGETS.items()):
        table.add_row(
            name,
            "installable" if target.default_path else "reference",
            target.description,
            str(target.default_path) if target.default_path else "-",
            ", ".join(file.destination for file in target.files),
        )
    Console().print(table)


@app.command()
@friendly_errors
def show(
    target: str = typer.Argument(..., help=f"Target to show: {_target_names()}."),
) -> None:
    """Print an agent integration document to stdout."""
    agent_target = _get_target(target)
    for index, file in enumerate(agent_target.files):
        if index:
            print(f"\n<!-- {file.destination} -->\n")
        print(_read_agent_file(file.source), end="")


@app.command()
@friendly_errors
def install(
    target: str = typer.Argument(..., help="Target to install: skill or continue."),
    path: Path | None = _INSTALL_PATH_OPTION,
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing files."),
) -> None:
    """Install agent integration docs into the current project."""
    agent_target = _get_target(target)
    if agent_target.default_path is None:
        raise typer.BadParameter(
            f"{target!r} is a reference document, not an installable target. "
            "Use 'skill' or 'continue'."
        )

    destination_dir = path or agent_target.default_path
    destination_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for file in agent_target.files:
        destination = destination_dir / file.destination
        if destination.exists() and not force:
            raise typer.BadParameter(
                f"{destination} already exists. Pass --force to overwrite it."
            )
        destination.write_text(_read_agent_file(file.source))
        written.append(destination)

    from rich.console import Console

    console = Console(stderr=True)
    for destination in written:
        console.print(f"[green]Wrote[/green] {destination}")
