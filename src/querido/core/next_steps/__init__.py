"""Deterministic ``next_steps`` rules.

Each rule inspects the shape of a command's output (row counts, null rates,
distinct counts, metadata presence, etc.) and returns a list of suggested
follow-up ``qdo`` invocations as ``{"cmd": str, "why": str}`` dicts.

Rules must be deterministic — no LLM calls, no network, no randomness.
They exist to turn every command into a node in a traversable graph for
agents. Human users also see them via the ``-f rich`` path (eventually).

Each ``cmd`` string is a shell-ready ``qdo ...`` invocation so agents can
re-exec it directly. Use :func:`querido._shell.cmd` to build
them — it handles quoting for identifiers with special characters.

The rules live in command-family submodules (``scan``, ``catalog``, ``query``,
``metadata``, ``errors``); this package re-exports every ``for_*`` so callers
keep using ``from querido.core.next_steps import for_<cmd>`` unchanged.
"""

from __future__ import annotations

from querido.core.next_steps.catalog import for_catalog, for_catalog_functions
from querido.core.next_steps.errors import for_error, for_workflow_step_failed
from querido.core.next_steps.metadata import (
    for_metadata_search,
    for_metadata_show,
    for_template,
    for_view_def,
)
from querido.core.next_steps.query import for_assert, for_diff, for_explain, for_query
from querido.core.next_steps.scan import (
    for_context,
    for_dist,
    for_freshness,
    for_inspect,
    for_joins,
    for_pivot,
    for_preview,
    for_profile,
    for_quality,
    for_values,
)

__all__ = [
    "for_assert",
    "for_catalog",
    "for_catalog_functions",
    "for_context",
    "for_diff",
    "for_dist",
    "for_error",
    "for_explain",
    "for_freshness",
    "for_inspect",
    "for_joins",
    "for_metadata_search",
    "for_metadata_show",
    "for_pivot",
    "for_preview",
    "for_profile",
    "for_quality",
    "for_query",
    "for_template",
    "for_values",
    "for_view_def",
    "for_workflow_step_failed",
]
