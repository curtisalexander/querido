from __future__ import annotations

from typing import TYPE_CHECKING

from querido.output import _fmt

if TYPE_CHECKING:
    from rich.console import Console


def print_inspect(
    table_name: str,
    columns: list[dict],
    row_count: int,
    console: Console | None = None,
    verbose: bool = False,
    table_comment: str | None = None,
) -> None:
    """Print table metadata as a Rich table."""
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    grid = Table(title=f"Table: {table_name}", show_lines=True)
    grid.add_column("Column", style="cyan bold")
    grid.add_column("Type", style="green")
    grid.add_column("Nullable", style="yellow")
    grid.add_column("Default", style="dim")
    grid.add_column("Primary Key", style="magenta")
    if verbose:
        grid.add_column("Comment", style="dim italic")

    for col in columns:
        row = [
            col["name"],
            col["type"],
            "YES" if col["nullable"] else "NO",
            str(col["default"]) if col["default"] is not None else "",
            "PK" if col.get("primary_key") else "",
        ]
        if verbose:
            row.append(col.get("comment") or "")
        grid.add_row(*row)

    console.print(grid)
    if table_comment:
        console.print(f"\n  Comment: [italic]{table_comment}[/italic]")
    console.print(f"\n  Row count: [bold]{row_count:,}[/bold]")


def print_preview(
    table_name: str,
    data: list[dict],
    limit: int,
    console: Console | None = None,
) -> None:
    """Print row data as a Rich table."""
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    if not data:
        console.print(f"[dim]No rows found in {table_name}.[/dim]")
        return

    grid = Table(title=f"Preview: {table_name} (limit {limit})")
    for key in data[0]:
        grid.add_column(key, style="cyan")

    for row in data:
        grid.add_row(*(str(v) if v is not None else "" for v in row.values()))

    console.print(grid)
    console.print(f"\n  Showing [bold]{len(data)}[/bold] row(s)")


def print_profile(
    table_name: str,
    data: list[dict],
    row_count: int,
    sampled: bool = False,
    sample_size: int | None = None,
    console: Console | None = None,
) -> None:
    """Print data profile as Rich tables (numeric and string sections)."""
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    if not data:
        console.print(f"[dim]No columns to profile in {table_name}.[/dim]")
        return

    numeric_rows = [r for r in data if r.get("min_val") is not None]
    string_rows = [r for r in data if r.get("min_length") is not None]

    if numeric_rows:
        grid = Table(title=f"Profile: {table_name} — Numeric Columns", show_lines=True)
        grid.add_column("Column", style="cyan bold")
        grid.add_column("Type", style="green")
        grid.add_column("Min", justify="right")
        grid.add_column("Max", justify="right")
        grid.add_column("Mean", justify="right")
        grid.add_column("Median", justify="right")
        grid.add_column("Stddev", justify="right")
        grid.add_column("Nulls", justify="right", style="yellow")
        grid.add_column("Null %", justify="right", style="yellow")
        grid.add_column("Distinct", justify="right")

        for r in numeric_rows:
            grid.add_row(
                str(r["column_name"]),
                str(r["column_type"]),
                _fmt(r["min_val"]),
                _fmt(r["max_val"]),
                _fmt(r["mean_val"]),
                _fmt(r["median_val"]),
                _fmt(r["stddev_val"]),
                _fmt(r["null_count"]),
                _fmt(r["null_pct"]),
                _fmt(r["distinct_count"]),
            )
        console.print(grid)

    if string_rows:
        grid = Table(title=f"Profile: {table_name} — String Columns", show_lines=True)
        grid.add_column("Column", style="cyan bold")
        grid.add_column("Type", style="green")
        grid.add_column("Min Len", justify="right")
        grid.add_column("Max Len", justify="right")
        grid.add_column("Distinct", justify="right")
        grid.add_column("Nulls", justify="right", style="yellow")
        grid.add_column("Null %", justify="right", style="yellow")

        for r in string_rows:
            grid.add_row(
                str(r["column_name"]),
                str(r["column_type"]),
                _fmt(r["min_length"]),
                _fmt(r["max_length"]),
                _fmt(r["distinct_count"]),
                _fmt(r["null_count"]),
                _fmt(r["null_pct"]),
            )
        console.print(grid)

    sample_note = ""
    if sampled and sample_size:
        sample_note = f" (sampled {sample_size:,} rows)"
    console.print(f"\n  Total rows: [bold]{row_count:,}[/bold]{sample_note}")


def print_search(
    pattern: str,
    results: list[dict],
    console: Console | None = None,
) -> None:
    """Print search results as a Rich table."""
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    if not results:
        console.print(f"[dim]No matches found for '{pattern}'.[/dim]")
        return

    grid = Table(title=f"Search: '{pattern}'", show_lines=True)
    grid.add_column("Table", style="cyan bold")
    grid.add_column("Type", style="green")
    grid.add_column("Match", style="yellow")
    grid.add_column("Column", style="cyan")
    grid.add_column("Column Type", style="dim")

    for r in results:
        grid.add_row(
            r["table_name"],
            r["table_type"],
            r["match_type"],
            r["column_name"] or "",
            r["column_type"] or "",
        )

    console.print(grid)
    console.print(f"\n  [bold]{len(results)}[/bold] match(es)")


def print_dist_numeric(
    dist_result: dict,
    console: Console | None = None,
) -> None:
    """Print numeric distribution as a horizontal bar chart."""
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text

    if console is None:
        console = Console()

    table_name = dist_result["table"]
    column = dist_result["column"]
    buckets = dist_result["buckets"]
    total_rows = dist_result["total_rows"]
    null_count = dist_result["null_count"]
    bar_width = 30

    if not buckets:
        console.print(f"[dim]No non-null values in {table_name}.{column}.[/dim]")
        return

    max_count = max(b["count"] for b in buckets)

    non_null_total = sum(b["count"] for b in buckets)

    grid = Table(title=f"Distribution: {table_name}.{column}", show_lines=True)
    grid.add_column("Bucket", style="cyan")
    grid.add_column("Count", justify="right")
    grid.add_column("%", justify="right")
    grid.add_column("", width=bar_width)

    for b in buckets:
        label = f"{_fmt(b['bucket_min'])} – {_fmt(b['bucket_max'])}"
        count = b["count"]
        pct = round(100.0 * count / non_null_total, 1) if non_null_total > 0 else 0
        w = int((count / max_count) * bar_width) if max_count > 0 else 0
        bar = Text("█" * w, style="green")
        grid.add_row(label, f"{count:,}", f"{pct}", bar)

    console.print(grid)
    null_note = f"  nulls: {null_count:,}" if null_count else ""
    console.print(f"\n  Total rows: [bold]{total_rows:,}[/bold]{null_note}")


def print_dist_categorical(
    dist_result: dict,
    console: Console | None = None,
) -> None:
    """Print categorical distribution as a frequency bar chart."""
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text

    if console is None:
        console = Console()

    table_name = dist_result["table"]
    column = dist_result["column"]
    values = dist_result["values"]
    total_rows = dist_result["total_rows"]
    null_count = dist_result["null_count"]
    bar_width = 30

    if not values:
        console.print(f"[dim]No non-null values in {table_name}.{column}.[/dim]")
        return

    max_count = max(v["count"] for v in values)

    value_total = sum(v["count"] for v in values)

    grid = Table(title=f"Distribution: {table_name}.{column}", show_lines=True)
    grid.add_column("Value", style="cyan")
    grid.add_column("Count", justify="right")
    grid.add_column("%", justify="right")
    grid.add_column("", width=bar_width)

    for v in values:
        label = str(v["value"]) if v["value"] is not None else "(NULL)"
        count = v["count"]
        pct = round(100.0 * count / value_total, 1) if value_total > 0 else 0
        w = int((count / max_count) * bar_width) if max_count > 0 else 0
        bar = Text("█" * w, style="green")
        grid.add_row(label, f"{count:,}", f"{pct}", bar)

    console.print(grid)
    null_note = f"  nulls: {null_count:,}" if null_count else ""
    console.print(f"\n  Total rows: [bold]{total_rows:,}[/bold]{null_note}")


def print_frequencies(
    table_name: str,
    freq_data: dict[str, list[dict]],
    row_count: int,
    console: Console | None = None,
) -> None:
    """Print top-N most frequent values per column as Rich tables."""
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    for col_name, rows in freq_data.items():
        if not rows:
            continue
        grid = Table(title=f"Top values: {table_name}.{col_name}", show_lines=True)
        grid.add_column("Value", style="cyan")
        grid.add_column("Count", justify="right")
        grid.add_column("%", justify="right", style="dim")

        for r in rows:
            pct = round(100.0 * r["count"] / row_count, 2) if row_count else 0
            grid.add_row(
                str(r["value"]) if r["value"] is not None else "(NULL)",
                f"{r['count']:,}",
                f"{pct}",
            )
        console.print(grid)
