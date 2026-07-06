"""Single import point for typer's bundled click.

typer 0.26+ vendors a slimmed click fork at ``typer._click`` and no longer
depends on the standalone ``click`` package. qdo reads the live context
stack (``--format`` / ``--show-sql`` / session argv) and click-level types,
and those must come from the *same* click typer runs the app on — importing
the standalone package would read an empty context stack, silently degrading
``-f json`` to rich output. Everything click-shaped in qdo imports from this
module so a future vendoring move is a one-line fix here.
"""

from __future__ import annotations

from typer._click import Command, Context, HelpFormatter, Parameter
from typer._click.globals import get_current_context

__all__ = [
    "Command",
    "Context",
    "HelpFormatter",
    "Parameter",
    "get_current_context",
]
