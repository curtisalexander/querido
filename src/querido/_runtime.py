"""Runtime invocation state shared across layers.

The active ``--format`` value lives on the root Click context. Both the CLI
layer and :mod:`querido.output.envelope` need to read it, so the lookup lives
here at the package root — ``output`` must not depend on ``cli``.
"""

from __future__ import annotations


def _get_root_obj() -> dict:
    """Walk up the Click context chain and return the root context's obj dict."""
    import click

    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return {}

    root = ctx
    while root.parent is not None:
        root = root.parent

    return root.obj or {}


def get_output_format() -> str:
    """Return the --format value from the root CLI context, defaulting to 'rich'."""
    return _get_root_obj().get("format", "rich")
