"""Schema diff — compare column metadata between two tables."""

from __future__ import annotations


def schema_diff(
    left_table: str,
    left_columns: list[dict],
    right_table: str,
    right_columns: list[dict],
) -> dict:
    """Compare column metadata between two tables.

    Returns::

        {
            "left": str,
            "right": str,
            "added": [{"name", "type", "nullable"}, ...],
            "removed": [{"name", "type", "nullable"}, ...],
            "changed": [{"name", "left_type", "right_type",
                         "left_nullable", "right_nullable"}, ...],
            "unchanged_count": int,
        }

    *added* = columns in right but not left.
    *removed* = columns in left but not right.
    *changed* = same column name, different type or nullable.
    """
    left_by_name = {c["name"].lower(): c for c in left_columns}
    right_by_name = {c["name"].lower(): c for c in right_columns}

    left_names = set(left_by_name.keys())
    right_names = set(right_by_name.keys())

    added = [
        _col_summary(right_by_name[n])
        for n in sorted(right_names - left_names)
    ]
    removed = [
        _col_summary(left_by_name[n])
        for n in sorted(left_names - right_names)
    ]

    changed = []
    unchanged_count = 0
    for n in sorted(left_names & right_names):
        lc = left_by_name[n]
        rc = right_by_name[n]
        if _columns_differ(lc, rc):
            changed.append({
                "name": lc["name"],
                "left_type": lc["type"],
                "right_type": rc["type"],
                "left_nullable": lc["nullable"],
                "right_nullable": rc["nullable"],
            })
        else:
            unchanged_count += 1

    return {
        "left": left_table,
        "right": right_table,
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged_count": unchanged_count,
    }


def _col_summary(col: dict) -> dict:
    return {
        "name": col["name"],
        "type": col["type"],
        "nullable": col["nullable"],
    }


def _columns_differ(left: dict, right: dict) -> bool:
    return (
        left["type"].lower() != right["type"].lower()
        or left["nullable"] != right["nullable"]
    )
