"""SQL assertion execution — compare query result against expected value."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector

# Supported comparison operators
OPERATORS = {
    "eq": lambda a, e: a == e,
    "gt": lambda a, e: a > e,
    "lt": lambda a, e: a < e,
    "gte": lambda a, e: a >= e,
    "lte": lambda a, e: a <= e,
}


def run_assertion(
    connector: Connector,
    sql: str,
    *,
    operator: str = "eq",
    expected: float,
    name: str | None = None,
) -> dict:
    """Execute *sql* and compare the first column of the first row.

    Returns::

        {
            "passed": bool,
            "actual": number,
            "expected": number,
            "operator": str,
            "name": str | None,
            "sql": str,
        }

    Raises ``ValueError`` if the query returns no rows or the operator
    is invalid.
    """
    if operator not in OPERATORS:
        raise ValueError(
            f"Invalid operator: {operator!r}. "
            f"Must be one of: {', '.join(sorted(OPERATORS))}"
        )

    rows = connector.execute(sql)
    if not rows:
        raise ValueError("Assertion query returned no rows.")

    first_row = rows[0]
    first_col = next(iter(first_row.values()))

    # Coerce to float for numeric comparison
    try:
        actual = float(first_col) if first_col is not None else None
    except (TypeError, ValueError):
        actual = first_col

    passed = False if actual is None else OPERATORS[operator](actual, expected)

    return {
        "passed": passed,
        "actual": actual,
        "expected": expected,
        "operator": operator,
        "name": name,
        "sql": sql,
    }
