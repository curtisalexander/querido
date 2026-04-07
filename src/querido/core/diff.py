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
    left_by_name = {c.get("name", "").lower(): c for c in left_columns}
    right_by_name = {c.get("name", "").lower(): c for c in right_columns}

    left_names = set(left_by_name.keys())
    right_names = set(right_by_name.keys())

    added = [_col_summary(right_by_name[n]) for n in sorted(right_names - left_names)]
    removed = [_col_summary(left_by_name[n]) for n in sorted(left_names - right_names)]

    changed = []
    unchanged_count = 0
    for n in sorted(left_names & right_names):
        lc = left_by_name[n]
        rc = right_by_name[n]
        if _columns_differ(lc, rc):
            changed.append(
                {
                    "name": lc.get("name", ""),
                    "left_type": lc.get("type", ""),
                    "right_type": rc.get("type", ""),
                    "left_nullable": lc.get("nullable", False),
                    "right_nullable": rc.get("nullable", False),
                }
            )
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
        "name": col.get("name", ""),
        "type": col.get("type", ""),
        "nullable": col.get("nullable", False),
    }


def _columns_differ(left: dict, right: dict) -> bool:
    return left.get("type", "").lower() != right.get("type", "").lower() or left.get(
        "nullable", False
    ) != right.get("nullable", False)
