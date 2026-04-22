"""Table freshness scan — detect temporal columns and summarize recency."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from querido.connectors.base import Connector


class FreshnessResult(TypedDict):
    table: str
    row_count: int
    stale_after_days: int
    status: str
    selected_column: str | None
    candidate_count: int
    candidates: list[dict[str, Any]]
    latest_value: str | None
    earliest_value: str | None
    latest_age_days: float | None
    reason: str | None
    sql: str


_TEMPORAL_TYPE_TOKENS = ("date", "time", "timestamp")
_TEMPORAL_SUFFIXES = ("_at", "_date", "_ts", "_time", "_timestamp")
_HIGH_SIGNAL_NAME_TOKENS = (
    "updated",
    "modified",
    "last_seen",
    "last_sync",
    "synced",
    "loaded",
    "ingested",
    "event",
    "occurred",
    "happened",
    "created",
)
_PREFERRED_NAME_TOKENS = (
    "updated",
    "modified",
    "last_seen",
    "last_sync",
    "synced",
    "loaded",
    "ingested",
)


def get_freshness(
    connector: Connector,
    table: str,
    *,
    column: str | None = None,
    stale_after_days: int = 7,
) -> FreshnessResult:
    """Detect temporal columns and summarize table recency."""
    from querido.connectors.base import validate_table_name

    validate_table_name(table)

    columns = connector.get_columns(table)
    detected = _detect_temporal_candidates(columns)

    if column is not None:
        lowered = column.lower()
        detected = [candidate for candidate in detected if candidate["name"].lower() == lowered]

    if not detected:
        return _build_no_candidate_result(connector, table, stale_after_days=stale_after_days)

    from querido.sql.renderer import render_template

    sql = render_template("freshness", connector.dialect, columns=detected, table=table)
    row = connector.execute(sql)[0]
    row_count = int(row.get("_total_rows", 0) or 0)

    candidates = _build_candidate_results(detected, row, row_count=row_count)
    selected = _pick_selected_candidate(candidates)

    latest_value = selected.get("latest_value") if selected else None
    earliest_value = selected.get("earliest_value") if selected else None
    latest_age_days = selected.get("latest_age_days") if selected else None

    status = "unknown"
    reason: str | None = None
    if selected is None:
        reason = "Detected temporal columns, but none contained non-null values."
    elif latest_age_days is None:
        reason = f"Latest value in '{selected['name']}' could not be parsed as a date/time."
    elif latest_age_days <= stale_after_days:
        status = "fresh"
        reason = (
            f"Newest value in '{selected['name']}' is {latest_age_days:.1f} day(s) old "
            f"(threshold: {stale_after_days}d)."
        )
    else:
        status = "stale"
        reason = (
            f"Newest value in '{selected['name']}' is {latest_age_days:.1f} day(s) old "
            f"(threshold: {stale_after_days}d)."
        )

    return {
        "table": table,
        "row_count": row_count,
        "stale_after_days": stale_after_days,
        "status": status,
        "selected_column": selected.get("name") if selected else None,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "latest_value": latest_value,
        "earliest_value": earliest_value,
        "latest_age_days": latest_age_days,
        "reason": reason,
        "sql": sql,
    }


def _build_no_candidate_result(
    connector: Connector,
    table: str,
    *,
    stale_after_days: int,
) -> FreshnessResult:
    from querido.sql.renderer import render_template

    sql = render_template("count", connector.dialect, table=table)
    rows = connector.execute(sql)
    row_count = int(rows[0].get("cnt", 0) or 0) if rows else 0

    return {
        "table": table,
        "row_count": row_count,
        "stale_after_days": stale_after_days,
        "status": "unknown",
        "selected_column": None,
        "candidate_count": 0,
        "candidates": [],
        "latest_value": None,
        "earliest_value": None,
        "latest_age_days": None,
        "reason": "No temporal columns were detected from schema names or types.",
        "sql": sql,
    }


def _detect_temporal_candidates(columns: list[dict]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for col in columns:
        name = str(col.get("name", ""))
        col_type = str(col.get("type", ""))
        score, reasons = _temporal_score(name, col_type)
        if score <= 0:
            continue
        candidates.append(
            {
                "name": name,
                "type": col_type,
                "score": score,
                "reasons": reasons,
            }
        )
    return sorted(candidates, key=lambda item: (-int(item["score"]), str(item["name"])))


def _temporal_score(name: str, col_type: str) -> tuple[int, list[str]]:
    lowered_name = name.lower()
    lowered_type = col_type.lower()
    score = 0
    reasons: list[str] = []

    if any(token in lowered_type for token in _TEMPORAL_TYPE_TOKENS):
        score += 4
        reasons.append("temporal type")

    if lowered_name.endswith(_TEMPORAL_SUFFIXES):
        score += 3
        reasons.append("temporal suffix")

    if any(token in lowered_name for token in _HIGH_SIGNAL_NAME_TOKENS):
        score += 2
        reasons.append("temporal name")

    if any(token in lowered_name for token in _PREFERRED_NAME_TOKENS):
        score += 1
        reasons.append("recency-oriented name")

    return score, reasons


def _build_candidate_results(
    detected: list[dict[str, Any]],
    row: dict[str, Any],
    *,
    row_count: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for candidate in detected:
        name = candidate["name"]
        non_null_count = int(row.get(f"{name}_non_nulls", 0) or 0)
        null_count = max(row_count - non_null_count, 0)
        earliest_raw = row.get(f"{name}_min")
        latest_raw = row.get(f"{name}_max")
        earliest_value = _stringify_temporal(earliest_raw)
        latest_value = _stringify_temporal(latest_raw)
        latest_age_days = _age_days(latest_raw)

        candidates.append(
            {
                "name": name,
                "type": candidate["type"],
                "score": candidate["score"],
                "reasons": candidate["reasons"],
                "non_null_count": non_null_count,
                "null_count": null_count,
                "null_pct": round(100.0 * null_count / row_count, 2) if row_count else 0.0,
                "earliest_value": earliest_value,
                "latest_value": latest_value,
                "latest_age_days": latest_age_days,
            }
        )
    return candidates


def _pick_selected_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    populated = [
        candidate for candidate in candidates if int(candidate.get("non_null_count", 0)) > 0
    ]
    if not populated:
        return None
    return min(
        populated,
        key=lambda candidate: (
            candidate.get("latest_age_days") is None,
            float(candidate.get("latest_age_days") or 0.0),
            -int(candidate.get("score", 0) or 0),
            -int(candidate.get("non_null_count", 0) or 0),
            str(candidate.get("name", "")),
        ),
    )


def _parse_temporal(value: object) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            try:
                parsed = datetime.combine(date.fromisoformat(text), time.min)
            except ValueError:
                return None
    else:
        return None

    local_now = datetime.now().astimezone()
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=local_now.tzinfo)
    return parsed.astimezone(local_now.tzinfo)


def _age_days(value: object) -> float | None:
    parsed = _parse_temporal(value)
    if parsed is None:
        return None
    now = datetime.now(parsed.tzinfo)
    age = now - parsed
    return round(age.total_seconds() / 86400.0, 2)


def _stringify_temporal(value: object) -> str | None:
    parsed = _parse_temporal(value)
    if parsed is None:
        return str(value) if value is not None else None
    if parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0 and parsed.microsecond == 0:
        return parsed.date().isoformat()
    return parsed.isoformat(timespec="seconds")
