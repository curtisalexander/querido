"""``qdo workflow`` — declarative workflows (Phase 4.1: spec only).

Only ``qdo workflow spec`` is implemented in Phase 4.1.  The runner, lint,
list, show, and ``from-session`` subcommands land in Phase 4.2+.  Shipping
the schema first lets agent-authoring docs (Phase 4.5) reference a stable
contract while the runner is still being built.
"""

from __future__ import annotations

import json
import sys

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Declarative workflows (spec only; runner in Phase 4.2).")


@app.command()
@friendly_errors
def spec(
    examples: bool = typer.Option(
        False,
        "--examples",
        help="Emit bundled example workflow YAML files instead of the JSON Schema.",
    ),
) -> None:
    """Print the workflow JSON Schema (default) or bundled examples."""
    from querido.core.workflow import WORKFLOW_SCHEMA, load_examples

    if examples:
        docs = load_examples()
        # Concatenate examples with YAML document separators so the output
        # parses as a multi-doc YAML stream. Each block is prefixed with a
        # comment pointing at its filename so agents can split them back out.
        parts: list[str] = []
        for filename, text in docs.items():
            parts.append(f"# file: {filename}\n{text.rstrip()}\n")
        sys.stdout.write("---\n".join(parts))
        return

    json.dump(WORKFLOW_SCHEMA, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")
