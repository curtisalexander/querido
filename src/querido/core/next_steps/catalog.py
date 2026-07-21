"""``next_steps`` rules for the catalog command family."""

from __future__ import annotations

from querido.core.next_steps._helpers import _pick_largest_table, _step


def for_catalog(
    result: dict,
    *,
    connection: str,
    enriched: bool,
) -> list[dict]:
    """Rules for ``qdo catalog``.

    Catalog lists all tables. Natural next moves:
    - drill into a specific table via ``context`` / ``inspect``
    - discover joins across the catalog
    - enrich with stored metadata if not already
    - if empty, pivot the user to check their connection
    """
    steps: list[dict] = []
    tables = result.get("tables") or []

    if not tables:
        steps.append(
            _step(
                ["qdo", "config", "test", connection],
                "No tables visible — verify the connection works.",
            )
        )
        return steps

    largest = _pick_largest_table(tables)
    if largest:
        steps.append(
            _step(
                ["qdo", "context", "-c", connection, "-t", largest],
                f"Deep-dive on '{largest}' (largest table by row count).",
            )
        )

    join_source = largest or next((t.get("name") for t in tables if t.get("name")), None)
    if len(tables) >= 2 and join_source:
        steps.append(
            _step(
                ["qdo", "joins", "-c", connection, "-t", join_source],
                "Discover likely join keys from a representative table.",
            )
        )

    if not enriched:
        steps.append(
            _step(
                ["qdo", "catalog", "-c", connection, "--enrich"],
                "Merge stored metadata (descriptions, owners) into the catalog.",
            )
        )

    return steps


def for_catalog_functions(
    result: dict,
    *,
    connection: str,
    pattern: str | None,
) -> list[dict]:
    """Rules for ``qdo catalog functions``."""
    if not result.get("supported", True):
        return [
            _step(
                ["qdo", "catalog", "-c", connection],
                "SQLite catalogs tables and views, but not backend SQL functions.",
            )
        ]

    if not result.get("functions") and pattern:
        return [
            _step(
                ["qdo", "catalog", "functions", "-c", connection],
                "No functions matched that filter; rerun without --pattern to browse everything.",
            ),
            _step(
                ["qdo", "catalog", "-c", connection],
                "Step back to tables/views if you meant data objects rather than SQL functions.",
            ),
        ]

    return [
        _step(
            ["qdo", "catalog", "-c", connection],
            "Step back to tables/views if you meant data objects rather than SQL functions.",
        )
    ]
