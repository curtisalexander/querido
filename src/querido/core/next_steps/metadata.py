"""``next_steps`` rules for metadata and doc-authoring commands."""

from __future__ import annotations

from querido.core.next_steps._helpers import (
    _maybe_suggest_metadata,
    _preview_column_sql,
    _step,
)


def for_view_def(
    result: dict,
    *,
    connection: str,
    view: str,
) -> list[dict]:
    """Rules for ``qdo view-def``.

    After reading a view's SQL, the next moves are to see its shape
    (``inspect``), sample rows (``preview``), or profile its output.
    """
    steps: list[dict] = []
    if not result.get("definition"):
        return steps

    steps.append(
        _step(
            ["qdo", "inspect", "-c", connection, "-t", view],
            f"See '{view}' column types and nullability.",
        )
    )
    steps.append(
        _step(
            ["qdo", "preview", "-c", connection, "-t", view],
            f"Peek at rows produced by '{view}'.",
        )
    )
    return steps


def for_metadata_show(
    result: dict,
    *,
    connection: str,
    table: str,
) -> list[dict]:
    """Rules for ``qdo metadata show``.

    A shown metadata doc points the reader at the two natural follow-ups:
    edit the YAML (fill in human fields or correct auto-written ones), and
    refresh auto-written stats from a new scan.
    """
    steps: list[dict] = [
        _step(
            ["qdo", "metadata", "edit", "-c", connection, "-t", table],
            "Open the YAML in $EDITOR to fill in descriptions or correct stored fields.",
        ),
        _step(
            ["qdo", "metadata", "refresh", "-c", connection, "-t", table],
            "Re-run the profile scan and update auto-written stats.",
        ),
    ]

    # If any human-authored placeholders remain, nudge at them.
    placeholder = "<description>"
    has_placeholder = False
    if result.get("table_description") == placeholder:
        has_placeholder = True
    for col in result.get("columns") or []:
        if col.get("description") == placeholder:
            has_placeholder = True
            break
    if has_placeholder:
        steps.append(
            _step(
                ["qdo", "metadata", "suggest", "-c", connection, "-t", table],
                "Some placeholder fields remain — suggest deterministic auto-fill.",
            )
        )

    return steps


def for_metadata_search(
    result: dict,
    *,
    connection: str,
) -> list[dict]:
    """Rules for ``qdo metadata search``."""
    if not result.get("metadata_file_count"):
        return [
            _step(
                ["qdo", "metadata", "list", "-c", connection],
                "Check whether this connection has any stored metadata files yet.",
            ),
            _step(
                ["qdo", "catalog", "-c", connection],
                "Browse live tables, then scaffold metadata for the ones you care about.",
            ),
        ]

    matches = result.get("results") or []
    if not matches:
        return [
            _step(
                ["qdo", "metadata", "list", "-c", connection],
                "Browse the stored metadata corpus to refine the next search.",
            ),
            _step(
                ["qdo", "catalog", "-c", connection, "--enrich"],
                "Compare live schema names with the stored descriptions and owners.",
            ),
        ]

    top = matches[0]
    table = str(top.get("table") or "")
    column = top.get("column")
    if not table:
        return []

    steps = [
        _step(
            ["qdo", "metadata", "show", "-c", connection, "-t", table],
            f"Open the stored metadata for '{table}'.",
        ),
        _step(
            ["qdo", "context", "-c", connection, "-t", table],
            f"Pull live stats and sample values for '{table}'.",
        ),
    ]
    if isinstance(column, str) and column:
        steps.append(
            _step(
                [
                    "qdo",
                    "query",
                    "-c",
                    connection,
                    "--sql",
                    _preview_column_sql(table, column),
                ],
                f"Inspect recent non-null values from '{table}.{column}'.",
            )
        )
    return steps


def for_template(
    result: dict,
    *,
    connection: str,
    table: str,
) -> list[dict]:
    """Rules for ``qdo template``.

    Template is the doc-authoring entrypoint. The natural compounding move
    is to scaffold / enrich stored metadata from the same scan output.
    """
    steps: list[dict] = []
    table_comment = result.get("table_comment") or ""
    columns = result.get("columns") or []

    if not table_comment:
        steps.append(
            _step(
                ["qdo", "metadata", "init", "-c", connection, "-t", table],
                "No table description — scaffold a metadata YAML to edit.",
            )
        )

    if columns:
        steps.append(
            _step(
                ["qdo", "profile", "-c", connection, "-t", table, "--write-metadata"],
                "Capture deterministic profile inferences into the metadata YAML.",
            )
        )

    pointer = _maybe_suggest_metadata(connection, table)
    if pointer:
        steps.append(pointer)

    return steps
