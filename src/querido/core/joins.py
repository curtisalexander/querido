"""Join key discovery — recommend join columns between tables."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector

# Type families for compatibility checks
_NUMERIC = {
    "integer",
    "int",
    "bigint",
    "smallint",
    "tinyint",
    "real",
    "float",
    "double",
    "numeric",
    "decimal",
    "number",
}
_TEXT = {"text", "varchar", "char", "string", "nvarchar", "nchar"}


def discover_joins(
    connector: Connector,
    table: str,
    *,
    target: str | None = None,
) -> dict:
    """Discover likely join keys between *table* and other tables.

    Returns::

        {
            "source": str,
            "candidates": [
                {
                    "target_table": str,
                    "join_keys": [
                        {
                            "source_col": str,
                            "target_col": str,
                            "match_type": "exact_name" | "convention",
                            "confidence": float,  # 0.0 - 1.0
                        }
                    ],
                }
            ],
        }
    """
    from querido.connectors.base import validate_table_name

    validate_table_name(table)

    source_cols = connector.get_columns(table)
    all_tables = connector.get_tables()

    # Determine target tables
    if target:
        validate_table_name(target)
        target_names = [target]
    else:
        target_names = [
            t.get("name", "") for t in all_tables if t.get("name", "").lower() != table.lower()
        ]

    candidates = []
    for tgt in target_names:
        tgt_cols = connector.get_columns(tgt)
        keys = _find_join_keys(table, source_cols, tgt, tgt_cols)
        if keys:
            # Sort by confidence descending
            keys.sort(key=lambda k: -k.get("confidence", 0.0))
            candidates.append(
                {
                    "target_table": tgt,
                    "join_keys": keys,
                }
            )

    # Sort candidates by best key confidence
    candidates.sort(key=lambda c: -max(k.get("confidence", 0.0) for k in c.get("join_keys", [])))

    return {"source": table, "candidates": candidates}


def _find_join_keys(
    src_table: str,
    src_cols: list[dict],
    tgt_table: str,
    tgt_cols: list[dict],
) -> list[dict]:
    """Find matching columns between source and target."""
    keys: list[dict] = []
    seen: set[tuple[str, str]] = set()

    tgt_by_name = {c.get("name", "").lower(): c for c in tgt_cols}

    for sc in src_cols:
        sc_name = sc.get("name", "").lower()
        sc_type = _type_family(sc.get("type", ""))

        # 1. Exact name match
        if sc_name in tgt_by_name:
            tc = tgt_by_name[sc_name]
            tc_type = _type_family(tc.get("type", ""))
            pair = (sc.get("name", ""), tc.get("name", ""))
            if pair not in seen:
                seen.add(pair)
                type_match = sc_type == tc_type
                confidence = 0.9 if type_match else 0.5
                keys.append(
                    {
                        "source_col": sc.get("name", ""),
                        "target_col": tc.get("name", ""),
                        "match_type": "exact_name",
                        "confidence": confidence,
                    }
                )

        # 2. Convention: source.{target_table}_id ↔ target.id
        tgt_lower = tgt_table.lower().rstrip("s")  # naive singular
        convention_name = f"{tgt_lower}_id"
        if sc_name == convention_name and "id" in tgt_by_name:
            tc = tgt_by_name.get("id", {})
            tc_type = _type_family(tc.get("type", ""))
            pair = (sc.get("name", ""), tc.get("name", ""))
            if pair not in seen:
                seen.add(pair)
                type_match = sc_type == tc_type
                confidence = 0.8 if type_match else 0.4
                keys.append(
                    {
                        "source_col": sc.get("name", ""),
                        "target_col": tc.get("name", ""),
                        "match_type": "convention",
                        "confidence": confidence,
                    }
                )

    # 3. Reverse convention: source.id ↔ target.{source_table}_id
    src_lower = src_table.lower().rstrip("s")
    reverse_name = f"{src_lower}_id"
    for tc in tgt_cols:
        if tc.get("name", "").lower() == reverse_name:
            # Find source "id" column
            src_id = next((c for c in src_cols if c.get("name", "").lower() == "id"), None)
            if src_id:
                pair = (src_id.get("name", ""), tc.get("name", ""))
                if pair not in seen:
                    seen.add(pair)
                    type_match = _type_family(src_id.get("type", "")) == _type_family(
                        tc.get("type", "")
                    )
                    confidence = 0.8 if type_match else 0.4
                    keys.append(
                        {
                            "source_col": src_id.get("name", ""),
                            "target_col": tc.get("name", ""),
                            "match_type": "convention",
                            "confidence": confidence,
                        }
                    )

    return keys


def _type_family(type_str: str) -> str:
    """Map a database type string to a type family for compatibility."""
    t = type_str.lower().split("(")[0].strip()
    if t in _NUMERIC:
        return "numeric"
    if t in _TEXT:
        return "text"
    return t
