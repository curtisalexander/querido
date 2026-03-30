"""Backward-compatible re-exports from split modules.

This module re-exports all public names so that existing imports like
``from querido.cli._util import friendly_errors`` continue to work.
New code should import from the specific modules directly:

- ``querido.cli._context`` — output format, SQL display, HTML emission
- ``querido.cli._validation`` — table/column existence checks
- ``querido.cli._errors`` — error handling, friendly_errors decorator
- ``querido.cli._pipeline`` — table_command, dispatch_output
"""

# Context helpers
from querido.cli._context import emit_html, get_output_format, maybe_show_sql, print_sql

# Error handling
from querido.cli._errors import friendly_errors, set_last_sql

# Validation helpers
from querido.cli._validation import (
    _format_not_found,
    _fuzzy_suggestions,
    check_table_exists,
    resolve_column,
)

__all__ = [
    "_format_not_found",
    "_fuzzy_suggestions",
    "check_table_exists",
    "emit_html",
    "friendly_errors",
    "get_output_format",
    "maybe_show_sql",
    "print_sql",
    "resolve_column",
    "set_last_sql",
]
