"""qdo completion — generate shell completion scripts."""

from __future__ import annotations

import typer

app = typer.Typer(help="Generate shell completion scripts.")

_SHELLS = ("bash", "zsh", "fish", "powershell")

_INSTALL_HINTS: dict[str, str] = {
    "bash": '# Add to ~/.bashrc:\neval "$(qdo completion show bash)"',
    "zsh": '# Add to ~/.zshrc:\neval "$(qdo completion show zsh)"',
    "fish": (
        "# Save to fish completions:\n"
        "qdo completion show fish > ~/.config/fish/completions/qdo.fish"
    ),
    "powershell": (
        "# Add to $PROFILE:\nqdo completion show powershell | Out-String | Invoke-Expression"
    ),
}


@app.command()
def show(
    shell: str = typer.Argument(
        ..., help=f"Shell to generate completions for: {', '.join(_SHELLS)}."
    ),
    hint: bool = typer.Option(
        False, "--hint", help="Show install instructions instead of the script."
    ),
) -> None:
    """Print a shell completion script to stdout.

    \b
    Examples:
        qdo completion show bash
        qdo completion show fish --hint
    """
    shell_lower = shell.lower()
    if shell_lower not in _SHELLS:
        raise typer.BadParameter(f"Unknown shell: {shell!r}. Must be one of: {', '.join(_SHELLS)}")

    if hint:
        print(_INSTALL_HINTS[shell_lower])
        return

    from typer._completion_shared import get_completion_script

    script = get_completion_script(
        prog_name="qdo", complete_var="_QDO_COMPLETE", shell=shell_lower
    )
    print(script)
