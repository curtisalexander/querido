"""Argv preprocessing so `-f/--format` can appear anywhere in a qdo invocation.

Click binds options to whichever command they follow in argv. `-f/--format` is
defined on the root `qdo` group, so `qdo inspect -c mydb -f json` hands `-f` to
`inspect`'s parser, which fails with `No such option: -f`. Agents produce both
orderings roughly equally; rather than train every model to place flags
correctly, we hoist `-f/--format` to position 1 before Click sees argv.

The workflow runner uses the same trick (see
``core/workflow/runner.py::_hoist_format_flag``), which also layers in a
capture-default injection. This module is the shared, pure hoist.
"""

from __future__ import annotations


def split_format_flag(tokens: list[str]) -> tuple[list[str], str | None]:
    """Walk *tokens* once, removing any ``-f``/``--format``/``--format=X``
    occurrence. Return ``(cleaned, value)`` where *value* is the last format
    value seen (or ``None`` if the flag never appeared).

    Multiple ``-f`` occurrences: last wins. This matches Click's own behavior
    when options are repeated.

    Edge cases:
    - ``-f`` as the final token with no value following: treated as absent.
    - ``--format=`` with an empty value: the empty string is returned as the
      value (Click will then reject it downstream, preserving the original
      error surface).
    """
    fmt_value: str | None = None
    cleaned: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-f", "--format"):
            if i + 1 < len(tokens):
                fmt_value = tokens[i + 1]
                i += 2
                continue
            i += 1
            continue
        if tok.startswith("--format="):
            fmt_value = tok.split("=", 1)[1]
            i += 1
            continue
        cleaned.append(tok)
        i += 1
    return cleaned, fmt_value


def hoist_format_flag(argv_after_prog: list[str]) -> list[str]:
    """Return *argv_after_prog* with any ``-f``/``--format`` moved to the
    front so Click's root group parses it.

    Input is argv *without* the program name (``sys.argv[1:]``). Output has
    the same shape — the hoist just reorders.

    No-op cases (returns input unchanged):
    - no ``-f``/``--format`` present
    - ``--help`` or ``--version`` present (don't rewrite help/version argv)
    """
    if not argv_after_prog:
        return argv_after_prog
    if "--help" in argv_after_prog or "--version" in argv_after_prog:
        return argv_after_prog
    cleaned, fmt_value = split_format_flag(argv_after_prog)
    if fmt_value is None:
        return argv_after_prog
    return ["-f", fmt_value, *cleaned]
