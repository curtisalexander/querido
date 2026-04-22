"""Generate a draft workflow YAML from a session's step log.

Reads ``.qdo/sessions/<name>/steps.jsonl``, keeps only successful steps
that invoked a data command (skipping meta-commands like ``session``,
``config``, ``workflow``), and synthesizes a declarative workflow that
replays the investigation with the connection and table parameterized as
``${connection}`` / ``${table}``.

The output is a *draft* — it lints clean on happy paths but the author
is expected to tune captures, outputs, and ``when:`` conditions before
shipping.  ``from-session`` is the bootstrap, not the final artifact.
"""

from __future__ import annotations

import re
import shlex
from collections import defaultdict
from pathlib import Path
from typing import Any

from querido.core.session import iter_steps

# Subcommands that make no sense as workflow steps — they manage local qdo
# state, print reference material, or launch interactive UIs.
_META_SUBCOMMANDS = frozenset(
    {
        "session",
        "config",
        "workflow",
        "overview",
        "completion",
        "tutorial",
        "explore",
        "cache",
    }
)

_IDENTIFIER_SAFE = re.compile(r"[^a-z0-9_]")
_SLUG_SAFE = re.compile(r"[^a-z0-9-]")


def from_session(
    session: str,
    *,
    last: int | None = None,
    name: str | None = None,
    description: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Return a workflow dict derived from *session*.

    Raises ``FileNotFoundError`` if the session has no recorded steps.
    """
    records = [r for r in iter_steps(session, cwd=cwd) if r.get("exit_code") == 0]
    if not records:
        raise FileNotFoundError(
            f"Session {session!r} has no successful steps to convert. "
            "Run 'qdo session show' to inspect."
        )

    steps_in: list[list[str]] = []
    for rec in records:
        argv = rec.get("args") or []
        if not isinstance(argv, list):
            continue
        if not argv:
            continue
        if argv[0] in _META_SUBCOMMANDS:
            continue
        steps_in.append([str(a) for a in argv])

    if last is not None and last > 0:
        steps_in = steps_in[-last:]

    if not steps_in:
        raise FileNotFoundError(
            f"Session {session!r} has no data-command steps to convert "
            "(all recorded steps were meta-commands)."
        )

    used_ids: dict[str, int] = defaultdict(int)
    uses_connection = False
    uses_table = False
    steps_out: list[dict[str, Any]] = []

    for argv in steps_in:
        parameterized, conn_seen, table_seen = _parameterize(argv)
        uses_connection = uses_connection or conn_seen
        uses_table = uses_table or table_seen

        base_id = _step_id_from_argv(argv)
        used_ids[base_id] += 1
        step_id = base_id if used_ids[base_id] == 1 else f"{base_id}_{used_ids[base_id]}"

        run_line = "qdo " + _join_tokens(parameterized)
        steps_out.append({"id": step_id, "run": run_line, "capture": step_id})

    inputs: dict[str, Any] = {}
    if uses_connection:
        inputs["connection"] = {"type": "connection", "required": True}
    if uses_table:
        inputs["table"] = {"type": "table", "required": True}

    wf_name = _slugify(name or f"from-{session}")
    wf_description = description or (
        f"Draft workflow generated from session {session!r}. "
        "Review captures, outputs, and `when:` conditions before using."
    )

    doc: dict[str, Any] = {
        "name": wf_name,
        "description": wf_description,
        "version": 1,
    }
    if inputs:
        doc["inputs"] = inputs
    doc["steps"] = steps_out
    return doc


def _parameterize(argv: list[str]) -> tuple[list[str], bool, bool]:
    """Replace ``-c VALUE`` / ``-t VALUE`` and long forms with ``${connection}`` / ``${table}``.

    Returns ``(rewritten_argv, used_connection, used_table)``.
    """
    out: list[str] = []
    used_conn = False
    used_table = False
    i = 0
    while i < len(argv):
        tok = argv[i]
        # Long forms with =value
        if tok.startswith("--connection="):
            out.extend(["--connection", "${connection}"])
            used_conn = True
            i += 1
            continue
        if tok.startswith("--table="):
            out.extend(["--table", "${table}"])
            used_table = True
            i += 1
            continue
        # -c / --connection (with value as the next token)
        if tok in ("-c", "--connection") and i + 1 < len(argv):
            out.extend([tok, "${connection}"])
            used_conn = True
            i += 2
            continue
        if tok in ("-t", "--table") and i + 1 < len(argv):
            out.extend([tok, "${table}"])
            used_table = True
            i += 2
            continue
        # Drop global format flags — the runner re-injects ``-f json`` for
        # captured steps, and including the original flag twice would fight
        # with that injection.
        if tok in ("-f", "--format") and i + 1 < len(argv):
            i += 2
            continue
        if tok.startswith("--format="):
            i += 1
            continue
        out.append(tok)
        i += 1
    return out, used_conn, used_table


def _step_id_from_argv(argv: list[str]) -> str:
    """Derive an identifier-safe step id from the subcommand tokens."""
    if not argv:
        return "step"
    base = argv[0]
    # Two-token subcommands like ``config add``, ``snowflake semantic``,
    # ``metadata init`` — keep both tokens, joined with an underscore.
    if len(argv) >= 2 and not argv[1].startswith("-"):
        base = f"{argv[0]}_{argv[1]}"
    base = base.lower().replace("-", "_")
    base = _IDENTIFIER_SAFE.sub("_", base)
    if not base or not base[0].isalpha():
        base = f"step_{base}".rstrip("_") or "step"
    return base


def _slugify(s: str) -> str:
    s = s.lower().replace("_", "-")
    s = _SLUG_SAFE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s or not s[0].isalpha():
        s = f"wf-{s}".rstrip("-") or "wf"
    return s


def _join_tokens(tokens: list[str]) -> str:
    """Join argv into a shell-safe string, preserving ``${refs}`` unquoted."""
    parts: list[str] = []
    for tok in tokens:
        if tok.startswith("${") and tok.endswith("}") and _is_simple_ref(tok):
            parts.append(tok)
        elif _needs_quoting(tok):
            parts.append(shlex.quote(tok))
        else:
            parts.append(tok)
    return " ".join(parts)


def _is_simple_ref(tok: str) -> bool:
    inner = tok[2:-1]
    return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_.]*$", inner))


def _needs_quoting(tok: str) -> bool:
    return bool(tok) and any(c.isspace() or c in "\"'\\$&|;()<>*?[]{}" for c in tok)


__all__ = ["from_session"]
