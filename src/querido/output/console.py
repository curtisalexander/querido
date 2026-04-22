from __future__ import annotations

from typing import TYPE_CHECKING

from querido.output import fmt_value

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
    from rich.panel import Panel
    from rich.table import Table

    if console is None:
        console = Console()

    nullable_count = sum(1 for col in columns if col["nullable"])
    pk_count = sum(1 for col in columns if col.get("primary_key"))

    title_parts = [f"[bold cyan]{table_name}[/bold cyan]", f"[dim]{row_count:,} rows[/dim]"]
    console.print("  " + "  ·  ".join(title_parts))

    summary_parts = [
        f"[green]{len(columns)} columns[/green]",
        f"[magenta]{pk_count} primary keys[/magenta]" if pk_count else "[dim]no primary key[/dim]",
        (
            f"[yellow]{nullable_count} nullable[/yellow]"
            if nullable_count
            else "[green]all not null[/green]"
        ),
    ]
    if verbose and table_comment:
        summary_parts.append("[cyan]table comment[/cyan]")

    console.print(
        Panel(
            "  •  ".join(summary_parts),
            border_style="cyan",
            title="Inspect Summary",
            padding=(0, 1),
        )
    )

    grid = Table(title="Column Detail", show_lines=True)
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
        from rich.text import Text

        label = Text("\n  Comment: ")
        label.append(table_comment, style="italic")
        console.print(label)
    console.print(f"\n  Row count: [bold]{row_count:,}[/bold]")


def print_preview(
    table_name: str,
    data: list[dict],
    limit: int,
    console: Console | None = None,
) -> None:
    """Print row data as a Rich table."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    if console is None:
        console = Console()

    if not data:
        console.print(f"[dim]No rows found in {table_name}.[/dim]")
        return

    console.print(f"  [bold cyan]{table_name}[/bold cyan]  ·  [dim]preview[/dim]")
    console.print(
        Panel(
            (
                f"[green]{len(data)} shown[/green]  •  "
                f"[magenta]limit {limit}[/magenta]  •  "
                f"[dim]{len(data[0])} columns[/dim]"
            ),
            border_style="cyan",
            title="Preview Summary",
            padding=(0, 1),
        )
    )

    grid = Table(title="Preview Rows")
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
    from rich.panel import Panel
    from rich.table import Table

    if console is None:
        console = Console()

    if not data:
        console.print(f"[dim]No columns to profile in {table_name}.[/dim]")
        return

    numeric_rows = [r for r in data if r.get("min_val") is not None]
    string_rows = [r for r in data if r.get("min_length") is not None]
    classified = {r["column_name"] for r in numeric_rows} | {r["column_name"] for r in string_rows}
    other_rows = [r for r in data if r["column_name"] not in classified]

    title_parts = [f"[bold cyan]{table_name}[/bold cyan]", f"[dim]{row_count:,} rows[/dim]"]
    if sampled and sample_size:
        title_parts.append(f"[dim]sampled {sample_size:,}[/dim]")
    console.print("  " + "  ·  ".join(title_parts))

    summary_parts = [
        f"[green]{len(numeric_rows)} numeric[/green]",
        f"[cyan]{len(string_rows)} string[/cyan]",
        f"[magenta]{len(other_rows)} other[/magenta]" if other_rows else "[dim]0 other[/dim]",
        f"[bold]{len(data)} columns[/bold]",
    ]
    if sampled and sample_size:
        summary_parts.append(f"[dim]sampled {sample_size:,}[/dim]")

    console.print(
        Panel(
            "  •  ".join(summary_parts),
            border_style="cyan",
            title="Profile Summary",
            padding=(0, 1),
        )
    )

    if numeric_rows:
        grid = Table(title="Numeric Columns", show_lines=True)
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
                fmt_value(r["min_val"]),
                fmt_value(r["max_val"]),
                fmt_value(r["mean_val"]),
                fmt_value(r["median_val"]),
                fmt_value(r["stddev_val"]),
                fmt_value(r["null_count"]),
                fmt_value(r["null_pct"]),
                fmt_value(r["distinct_count"]),
            )
        console.print(grid)

    if string_rows:
        grid = Table(title="String Columns", show_lines=True)
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
                fmt_value(r["min_length"]),
                fmt_value(r["max_length"]),
                fmt_value(r["distinct_count"]),
                fmt_value(r["null_count"]),
                fmt_value(r["null_pct"]),
            )
        console.print(grid)

    if other_rows:
        grid = Table(title="Other Columns", show_lines=True)
        grid.add_column("Column", style="cyan bold")
        grid.add_column("Type", style="green")
        grid.add_column("Nulls", justify="right", style="yellow")
        grid.add_column("Null %", justify="right", style="yellow")
        grid.add_column("Distinct", justify="right")

        for r in other_rows:
            grid.add_row(
                str(r["column_name"]),
                str(r["column_type"]),
                fmt_value(r["null_count"]),
                fmt_value(r["null_pct"]),
                fmt_value(r["distinct_count"]),
            )
        console.print(grid)

    sample_note = ""
    if sampled and sample_size:
        sample_note = f" (sampled {sample_size:,} rows)"
    console.print(f"\n  Total rows: [bold]{row_count:,}[/bold]{sample_note}")
    if sampled:
        console.print("  [dim]Sampled — use --no-sample for exact results (slower)[/dim]")


def print_dist(
    dist_result: dict,
    console: Console | None = None,
) -> None:
    """Print a distribution (numeric or categorical) as a horizontal bar chart."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    if console is None:
        console = Console()

    table_name = dist_result["table"]
    column = dist_result["column"]
    total_rows = dist_result["total_rows"]
    null_count = dist_result["null_count"]
    is_numeric = dist_result["mode"] == "numeric"
    items = dist_result["buckets"] if is_numeric else dist_result["values"]
    bar_width = 30

    if not items:
        console.print(f"[dim]No non-null values in {table_name}.{column}.[/dim]")
        return

    max_count = max(item["count"] for item in items)
    item_total = sum(item["count"] for item in items)

    title_parts = [
        f"[bold cyan]{table_name}.{column}[/bold cyan]",
        f"[dim]{dist_result['mode']}[/dim]",
        f"[dim]{total_rows:,} rows[/dim]",
    ]
    if dist_result.get("sampled") and dist_result.get("sample_size"):
        title_parts.append(f"[dim]sampled {dist_result['sample_size']:,}[/dim]")
    console.print("  " + "  ·  ".join(title_parts))

    summary_parts = [
        f"[green]{len(items)} {'buckets' if is_numeric else 'values'}[/green]",
        f"[magenta]{item_total:,} non-null rows[/magenta]",
        f"[yellow]{null_count:,} nulls[/yellow]" if null_count else "[dim]0 nulls[/dim]",
    ]

    console.print(
        Panel(
            "  •  ".join(summary_parts),
            border_style="cyan",
            title="Distribution Summary",
            padding=(0, 1),
        )
    )

    grid = Table(title="Distribution Detail", show_lines=True)
    grid.add_column("Bucket" if is_numeric else "Value", style="cyan")
    grid.add_column("Count", justify="right")
    grid.add_column("%", justify="right")
    grid.add_column("", width=bar_width)

    for item in items:
        if is_numeric:
            label = f"{fmt_value(item['bucket_min'])} - {fmt_value(item['bucket_max'])}"
        else:
            label = str(item["value"]) if item["value"] is not None else "(NULL)"
        count = item["count"]
        pct = round(100.0 * count / item_total, 1) if item_total > 0 else 0
        w = int((count / max_count) * bar_width) if max_count > 0 else 0
        bar = Text("\u2588" * w, style="green")
        grid.add_row(label, f"{count:,}", f"{pct}%", bar)

    console.print(grid)
    null_note = f"  nulls: {null_count:,}" if null_count else ""
    sample_note = ""
    if dist_result.get("sampled") and dist_result.get("sample_size"):
        sample_note = f" (sampled {dist_result['sample_size']:,} rows)"
    console.print(f"\n  Total rows: [bold]{total_rows:,}[/bold]{null_note}{sample_note}")


def print_template(
    template_result: dict,
    *,
    style: str = "table",
    console: Console | None = None,
) -> None:
    """Print a documentation template as a Rich table."""
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    table_name = template_result["table"]
    table_comment = template_result["table_comment"]
    row_count = template_result["row_count"]
    columns = template_result["columns"]

    grid = Table(title=f"Template: {table_name}", show_lines=True)
    grid.add_column("Column", style="cyan bold")
    grid.add_column("Type", style="green")
    grid.add_column("Nullable", style="yellow")
    grid.add_column("Distinct", justify="right")
    grid.add_column("Nulls", justify="right")
    grid.add_column("Min", justify="right")
    grid.add_column("Max", justify="right")
    grid.add_column("Sample Values", style="dim")
    grid.add_column("Business Definition", style="italic magenta")
    grid.add_column("Data Owner", style="italic magenta")
    grid.add_column("Notes", style="italic magenta")

    for col in columns:
        min_display = fmt_value(col.get("min_val")) or fmt_value(col.get("min_length"))
        max_display = fmt_value(col.get("max_val")) or fmt_value(col.get("max_length"))
        grid.add_row(
            col["name"],
            col["type"],
            "YES" if col["nullable"] else "NO",
            fmt_value(col["distinct_count"]),
            fmt_value(col["null_count"]),
            min_display,
            max_display,
            col["sample_values"] or "",
            "<business_definition>",
            "<data_owner>",
            "<notes>",
        )

    console.print(grid)
    if table_comment:
        from rich.text import Text

        label = Text("\n  Comment: ")
        label.append(table_comment, style="italic")
        console.print(label)
    console.print(f"\n  Row count: [bold]{row_count:,}[/bold]")


def print_lineage(
    lineage_result: dict,
    console: Console | None = None,
) -> None:
    """Print a view definition with syntax highlighting."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax

    if console is None:
        console = Console()

    view_name = lineage_result["view"]
    dialect = lineage_result["dialect"]
    definition = lineage_result["definition"]

    syntax = Syntax(definition, "sql", theme="monokai", line_numbers=True)
    panel = Panel(syntax, title=f"View: {view_name} ({dialect})", border_style="cyan")
    console.print(panel)


def print_snowflake_lineage(
    lineage_result: dict,
    console: Console | None = None,
) -> None:
    """Print Snowflake lineage results as a Rich tree or table."""
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    object_name = lineage_result["object"]
    direction = lineage_result["direction"]
    entries = lineage_result["entries"]

    if not entries:
        console.print(f"[dim]No {direction} lineage found for '{object_name}'.[/dim]")
        return

    grid = Table(
        title=f"Lineage: {object_name} ({direction})",
        show_lines=True,
    )

    # GET_LINEAGE returns columns like SOURCE_OBJECT_NAME, TARGET_OBJECT_NAME, etc.
    # Show whatever columns the query returned.
    for key in entries[0]:
        grid.add_column(key, style="cyan")
    for row in entries:
        grid.add_row(*(str(v) if v is not None else "" for v in row.values()))

    console.print(grid)
    console.print(f"\n  [bold]{len(entries)}[/bold] lineage entries")


def print_metadata(
    meta: dict,
    console: Console | None = None,
) -> None:
    """Print stored metadata as Rich output."""
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    table_name = meta.get("table", "")
    console.print(f"\n  [bold cyan]{table_name}[/bold cyan]")

    desc = meta.get("table_description", "")
    if desc and not str(desc).startswith("<"):
        console.print(f"  {desc}")
    owner = meta.get("data_owner", "")
    if owner and not str(owner).startswith("<"):
        console.print(f"  Owner: {owner}")
    freq = meta.get("update_frequency", "")
    if freq and not str(freq).startswith("<"):
        console.print(f"  Update frequency: {freq}")
    notes = meta.get("notes", "")
    if notes and str(notes).strip():
        console.print(f"  Notes: {notes.strip()}")

    console.print(f"  Row count: [bold]{meta.get('row_count', 0):,}[/bold]")

    columns = meta.get("columns", [])
    if columns:
        grid = Table(title="Columns", show_lines=True)
        grid.add_column("Name", style="cyan bold")
        grid.add_column("Type", style="green")
        grid.add_column("Description", style="dim")
        grid.add_column("Nulls", justify="right")
        grid.add_column("Distinct", justify="right")

        for col in columns:
            desc_val = col.get("description", "")
            if str(desc_val).startswith("<"):
                desc_val = ""
            grid.add_row(
                col.get("name", ""),
                col.get("type", ""),
                desc_val,
                str(col.get("null_count", "")),
                str(col.get("distinct_count", "")),
            )
        console.print(grid)


def print_metadata_list(
    connection: str,
    entries: list[dict],
    console: Console | None = None,
) -> None:
    """Print metadata file listing."""
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    if not entries:
        console.print(f"[dim]No metadata stored for {connection}.[/dim]")
        return

    grid = Table(title=f"Metadata: {connection}")
    grid.add_column("Table", style="cyan")
    grid.add_column("Completeness", justify="right")
    grid.add_column("Path", style="dim")

    for entry in entries:
        grid.add_row(
            entry.get("table", ""),
            f"{entry.get('completeness', 0):.0f}%",
            entry.get("path", ""),
        )

    console.print(grid)


def print_metadata_search(
    result: dict,
    console: Console | None = None,
) -> None:
    """Print metadata-search results."""
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    matches = result.get("results") or []
    query = result.get("query", "")
    connection = result.get("connection", "")
    if not matches:
        console.print(
            f"[dim]No metadata matches for [/dim][bold]{query}[/bold][dim] in {connection}.[/dim]"
        )
        return

    grid = Table(title=f"Metadata Search: {query}")
    grid.add_column("Kind", style="magenta")
    grid.add_column("Table", style="cyan")
    grid.add_column("Column", style="green")
    grid.add_column("Score", justify="right")
    grid.add_column("Matched")
    grid.add_column("Excerpt", overflow="fold")

    for row in matches:
        grid.add_row(
            str(row.get("kind", "")),
            str(row.get("table", "")),
            str(row.get("column") or ""),
            f"{float(row.get('score', 0)):.3f}",
            ", ".join(str(term) for term in row.get("matched_terms") or []),
            str(row.get("excerpt", "")),
        )

    console.print(grid)


def print_explain(
    result: dict,
    console: Console | None = None,
) -> None:
    """Print query execution plan with syntax highlighting."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax

    if console is None:
        console = Console()

    plan = result.get("plan", "")
    dialect = result.get("dialect", "")
    analyzed = result.get("analyzed", False)
    title = f"Query Plan ({dialect})"
    if analyzed:
        title += " [ANALYZE]"

    console.print(
        Panel(
            Syntax(plan, "text", theme="monokai", line_numbers=False),
            title=title,
            expand=True,
        )
    )


def print_diff(
    result: dict,
    console: Console | None = None,
) -> None:
    """Print schema diff as Rich output."""
    from rich.console import Console

    if console is None:
        console = Console()

    added = result["added"]
    removed = result["removed"]
    changed = result["changed"]
    unchanged = result["unchanged_count"]

    console.print(
        f"\n  Schema diff: [cyan]{result['left']}[/cyan] → [cyan]{result['right']}[/cyan]"
    )
    if isinstance(result.get("previous_row_count"), int) and isinstance(
        result.get("current_row_count"), int
    ):
        delta = result.get("row_count_delta")
        delta_text = f"{delta:+,}" if isinstance(delta, int) else "n/a"
        console.print(
            f"  Row count: [cyan]{result['previous_row_count']:,}[/cyan] → "
            f"[cyan]{result['current_row_count']:,}[/cyan]  ([bold]{delta_text}[/bold])"
        )

    if not added and not removed and not changed:
        console.print("  [green]Schemas are identical.[/green]")
        return

    if added:
        from rich.table import Table

        grid = Table(title="Added (in right only)", show_lines=True)
        grid.add_column("Column", style="green bold")
        grid.add_column("Type", style="green")
        grid.add_column("Nullable")
        for col in added:
            grid.add_row(
                col["name"],
                col["type"],
                "YES" if col["nullable"] else "NO",
            )
        console.print(grid)

    if removed:
        from rich.table import Table

        grid = Table(title="Removed (in left only)", show_lines=True)
        grid.add_column("Column", style="red bold")
        grid.add_column("Type", style="red")
        grid.add_column("Nullable")
        for col in removed:
            grid.add_row(
                col["name"],
                col["type"],
                "YES" if col["nullable"] else "NO",
            )
        console.print(grid)

    if changed:
        from rich.table import Table

        grid = Table(title="Changed", show_lines=True)
        grid.add_column("Column", style="yellow bold")
        grid.add_column("Left Type")
        grid.add_column("Right Type")
        grid.add_column("Left Nullable")
        grid.add_column("Right Nullable")
        for col in changed:
            grid.add_row(
                col["name"],
                col["left_type"],
                col["right_type"],
                "YES" if col["left_nullable"] else "NO",
                "YES" if col["right_nullable"] else "NO",
            )
        console.print(grid)

    console.print(f"\n  {unchanged} unchanged column(s)")


def print_joins(
    result: dict,
    console: Console | None = None,
) -> None:
    """Print join key candidates as Rich tables."""
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    candidates = result["candidates"]
    if not candidates:
        console.print(f"[dim]No join candidates found for {result['source']}.[/dim]")
        return

    for cand in candidates:
        grid = Table(title=f"{result['source']} → {cand['target_table']}")
        grid.add_column("Source Column", style="cyan")
        grid.add_column("Target Column", style="green")
        grid.add_column("Match Type", style="dim")
        grid.add_column("Confidence", justify="right")

        for key in cand["join_keys"]:
            conf = f"{key['confidence']:.0%}"
            grid.add_row(
                key["source_col"],
                key["target_col"],
                key["match_type"],
                conf,
            )

        console.print(grid)

    console.print(f"\n  [bold]{len(candidates)}[/bold] table(s) with join candidates")


def print_quality(
    result: dict,
    console: Console | None = None,
) -> None:
    """Print data quality summary as a Rich table."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    if console is None:
        console = Console()

    columns = result["columns"]
    if not columns:
        console.print("[dim]No columns to check.[/dim]")
        return

    row_count = result["row_count"]
    sampled = result.get("sampled", False)
    sample_size = result.get("sample_size")

    row_str = f"{row_count:,} rows"
    if sampled and sample_size:
        row_str += f" — sampled {sample_size:,}"

    failed = [col for col in columns if col.get("status") == "fail"]
    warned = [col for col in columns if col.get("status") == "warn"]
    ok_count = sum(1 for col in columns if col.get("status") == "ok")
    duplicate_rows = result.get("duplicate_rows")

    title_parts = [f"[bold cyan]{result['table']}[/bold cyan]", f"[dim]{row_str}[/dim]"]
    console.print("  " + "  ·  ".join(title_parts))

    summary_parts = [
        f"[green]{ok_count} ok[/green]",
        f"[yellow]{len(warned)} warn[/yellow]",
        f"[red]{len(failed)} fail[/red]",
    ]
    if duplicate_rows is not None:
        if duplicate_rows > 0:
            summary_parts.append(f"[yellow]{duplicate_rows:,} duplicate rows[/yellow]")
        else:
            summary_parts.append("[green]no duplicate rows[/green]")
    if sampled and sample_size:
        summary_parts.append(f"[dim]sampled {sample_size:,}[/dim]")

    console.print(
        Panel(
            "  •  ".join(summary_parts),
            border_style="cyan",
            title="Quality Summary",
            padding=(0, 1),
        )
    )

    grid = Table(
        title="Column Detail",
        show_lines=True,
    )
    grid.add_column("Column", style="cyan bold")
    grid.add_column("Type", style="dim")
    grid.add_column("Nulls", justify="right")
    grid.add_column("Null %", justify="right")
    grid.add_column("Distinct", justify="right")
    grid.add_column("Unique %", justify="right")
    grid.add_column("Status")
    grid.add_column("Issues", style="dim")

    status_styles = {
        "ok": "[green]OK[/green]",
        "warn": "[yellow]WARN[/yellow]",
        "fail": "[red]FAIL[/red]",
    }

    for col in columns:
        null_pct = float(col["null_pct"])
        uniqueness_pct = float(col["uniqueness_pct"])
        null_style = "red" if null_pct >= 90 else "yellow" if null_pct >= 20 else "dim"
        unique_style = (
            "red"
            if col["status"] == "fail"
            else "yellow"
            if col["status"] == "warn"
            else "dim"
        )
        grid.add_row(
            col["name"],
            col["type"],
            f"{col['null_count']:,}",
            f"[{null_style}]{null_pct:.1f}%[/{null_style}]",
            f"{col['distinct_count']:,}",
            f"[{unique_style}]{uniqueness_pct:.1f}%[/{unique_style}]",
            status_styles.get(col["status"], col["status"]),
            "; ".join(col["issues"]) if col["issues"] else "",
        )

    console.print(grid)

    if sampled:
        console.print("\n  [dim]Sampled — use --no-sample for exact results (slower)[/dim]")


def print_assert_check(
    result: dict,
    console: Console | None = None,
) -> None:
    """Print assertion result."""
    from rich.console import Console

    if console is None:
        console = Console()

    passed = result["passed"]
    status = "[bold green]PASSED[/bold green]" if passed else "[bold red]FAILED[/bold red]"
    name = result.get("name")
    label = f"  {name}: " if name else "  Assertion: "

    op_labels = {"eq": "==", "gt": ">", "lt": "<", "gte": ">=", "lte": "<="}
    op_sym = op_labels.get(result["operator"], result["operator"])

    console.print(f"\n{label}{status}")
    console.print(f"  actual={result['actual']}  expected {op_sym} {result['expected']}")


def print_pivot(
    result: dict,
    console: Console | None = None,
) -> None:
    """Print pivot / aggregation results as a Rich table."""
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    rows = result["rows"]
    if not rows:
        console.print("[dim]Pivot returned no rows.[/dim]")
        return

    grid = Table(title="Pivot Results")
    for header in result["headers"]:
        grid.add_column(header, style="cyan")

    for row in rows:
        grid.add_row(*(str(v) if v is not None else "" for v in row.values()))

    console.print(grid)
    console.print(f"\n  [bold]{result['row_count']}[/bold] group(s)")


def print_values(
    result: dict,
    console: Console | None = None,
) -> None:
    """Print distinct values as a Rich table."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    if console is None:
        console = Console()

    values = result["values"]
    col = result["column"]
    tbl = result["table"]
    truncated = result["truncated"]

    title_parts = [f"[bold cyan]{tbl}.{col}[/bold cyan]"]
    if truncated:
        title_parts.append(f"[yellow]top {len(values)} of {result['distinct_count']:,}[/yellow]")
    else:
        title_parts.append(f"[dim]{result['distinct_count']:,} distinct[/dim]")
    console.print("  " + "  ·  ".join(title_parts))

    summary_parts = [
        f"[green]{len(values)} shown[/green]",
        f"[magenta]{result['distinct_count']:,} distinct[/magenta]",
        (
            f"[yellow]{result['null_count']:,} nulls[/yellow]"
            if result["null_count"] > 0
            else "[dim]0 nulls[/dim]"
        ),
    ]
    if truncated:
        summary_parts.append("[yellow]truncated[/yellow]")

    console.print(
        Panel(
            "  •  ".join(summary_parts),
            border_style="cyan",
            title="Values Summary",
            padding=(0, 1),
        )
    )

    grid = Table(title="Value Detail")
    grid.add_column("Value", style="cyan")
    grid.add_column("Count", justify="right")

    for row in values:
        val = str(row["value"]) if row["value"] is not None else "(NULL)"
        grid.add_row(val, f"{row['count']:,}")

    console.print(grid)


def print_freshness(
    result: dict,
    console: Console | None = None,
) -> None:
    """Print freshness scan results as a Rich summary + candidate table."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    if console is None:
        console = Console()

    status = result.get("status", "unknown")
    selected = result.get("selected_column")
    candidates = result.get("candidates") or []
    row_count = int(result.get("row_count", 0) or 0)
    status_label = {
        "fresh": "[green]FRESH[/green]",
        "stale": "[red]STALE[/red]",
        "unknown": "[yellow]UNKNOWN[/yellow]",
    }.get(status, str(status).upper())

    console.print(
        "  [bold cyan]Freshness[/bold cyan]  ·  "
        f"[dim]{result.get('table', '')}[/dim]  ·  {status_label}"
    )

    summary_parts = [
        f"[green]{row_count:,} rows[/green]",
        f"[cyan]{len(candidates)} candidate columns[/cyan]",
        (
            f"[magenta]selected: {selected}[/magenta]"
            if selected
            else "[dim]no selected column[/dim]"
        ),
    ]
    latest_age_days = result.get("latest_age_days")
    if latest_age_days is not None:
        summary_parts.append(f"[yellow]{latest_age_days:.1f}d old[/yellow]")

    console.print(
        Panel(
            "  •  ".join(summary_parts),
            border_style="cyan",
            title="Freshness Summary",
            padding=(0, 1),
        )
    )

    reason = result.get("reason")
    if reason:
        console.print(f"  [dim]{reason}[/dim]")

    if not candidates:
        return

    grid = Table(title="Temporal Candidates")
    grid.add_column("Column", style="cyan bold")
    grid.add_column("Type", style="dim")
    grid.add_column("Null %", justify="right")
    grid.add_column("Earliest")
    grid.add_column("Latest")
    grid.add_column("Age", justify="right")
    grid.add_column("Signals", style="dim")

    for candidate in candidates:
        age = candidate.get("latest_age_days")
        age_str = f"{age:.1f}d" if age is not None else "—"
        name = str(candidate.get("name", ""))
        if name == selected:
            name = f"{name} [selected]"
        grid.add_row(
            name,
            str(candidate.get("type", "")),
            f"{float(candidate.get('null_pct', 0.0)):.1f}%",
            str(candidate.get("earliest_value") or "—"),
            str(candidate.get("latest_value") or "—"),
            age_str,
            ", ".join(candidate.get("reasons") or []),
        )

    console.print(grid)


def _print_values_summary(result: dict, *, truncated: bool, console: Console) -> None:
    parts = [f"  [bold]{result['distinct_count']:,}[/bold] distinct values"]
    if result["null_count"] > 0:
        parts.append(f"[dim]{result['null_count']:,} nulls[/dim]")
    if truncated:
        parts.append("[yellow]truncated[/yellow]")
    console.print("\n" + "  |  ".join(parts))


def print_plan(
    result: dict,
    console: Console | None = None,
) -> None:
    """Print a generic dry-run plan payload."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    if console is None:
        console = Console()

    action = str(result.get("action", "plan"))
    executable = bool(result.get("executable", True))
    status = "[green]READY[/green]" if executable else "[yellow]BLOCKED[/yellow]"

    console.print(f"  [bold cyan]Plan[/bold cyan]  ·  [dim]{action}[/dim]  ·  {status}")
    console.print(
        Panel(
            str(result.get("summary", "")),
            border_style="cyan",
            title="Plan Summary",
            padding=(0, 1),
        )
    )

    details = Table(title="Plan Detail")
    details.add_column("Field", style="cyan bold")
    details.add_column("Value", style="dim")

    for key in ("action", "mode", "destination", "format", "table", "output_path", "limit"):
        value = result.get(key)
        if value not in (None, "", []):
            details.add_row(key, str(value))

    sql = result.get("sql")
    if sql:
        details.add_row("sql", str(sql))

    effects = result.get("effects") or []
    if effects:
        details.add_row("effects", " | ".join(str(item) for item in effects))

    writes = result.get("writes") or []
    if writes:
        details.add_row("writes", " | ".join(str(item) for item in writes))

    console.print(details)


def print_estimate(
    result: dict,
    console: Console | None = None,
) -> None:
    """Print a generic estimate payload."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    if console is None:
        console = Console()

    action = str(result.get("action", "estimate"))
    cost_hint = str(result.get("cost_hint", "unknown")).upper()

    console.print(
        "  [bold cyan]Estimate[/bold cyan]  ·  "
        f"[dim]{action}[/dim]  ·  [yellow]{cost_hint}[/yellow]"
    )
    console.print(
        Panel(
            str(result.get("summary", "")),
            border_style="cyan",
            title="Estimate Summary",
            padding=(0, 1),
        )
    )

    details = Table(title="Estimate Detail")
    details.add_column("Field", style="cyan bold")
    details.add_column("Value", style="dim")

    for key in (
        "dialect",
        "complexity",
        "cost_hint",
        "row_estimate",
        "row_estimate_source",
        "output_row_ceiling",
        "destination",
        "format",
        "table",
        "output_path",
    ):
        value = result.get(key)
        if value not in (None, "", []):
            details.add_row(key, str(value))

    if result.get("notes"):
        details.add_row("notes", " | ".join(str(x) for x in result["notes"]))
    if result.get("sql"):
        details.add_row("sql", str(result["sql"]))

    console.print(details)


def print_search(
    result: dict,
    console: Console | None = None,
) -> None:
    """Print ranked command-search results."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    if console is None:
        console = Console()

    query = str(result.get("query", ""))
    matches = result.get("results") or []

    console.print(f"  [bold cyan]Search[/bold cyan]  ·  [dim]{query}[/dim]")
    console.print(
        Panel(
            (
                f"{result.get('result_count', 0)} match(es) across "
                f"{result.get('searched_command_count', 0)} commands."
            ),
            border_style="cyan",
            title="Command Discovery",
            padding=(0, 1),
        )
    )

    if not matches:
        console.print("[dim]No strong command matches found.[/dim]")
        return

    table = Table(title="Matches", show_lines=True)
    table.add_column("Command", style="cyan bold", no_wrap=True)
    table.add_column("Score", justify="right", style="dim")
    table.add_column("Why", style="dim")
    table.add_column("Help", style="green")

    for match in matches:
        detail = str(match.get("rationale", ""))
        subcommands = match.get("subcommands") or []
        if subcommands:
            detail += f"\n[dim]subcommands:[/dim] {', '.join(str(x) for x in subcommands)}"
        table.add_row(
            str(match.get("name", "")),
            f"{float(match.get('score', 0.0)):.3f}",
            detail,
            str(match.get("help_command", "")),
        )

    console.print(table)


def print_catalog(
    catalog: dict,
    console: Console | None = None,
) -> None:
    """Print the database catalog as a Rich table."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    if console is None:
        console = Console()

    tables = catalog["tables"]
    if not tables:
        console.print("[dim]No tables found.[/dim]")
        return

    table_count = catalog["table_count"]
    view_count = sum(1 for t in tables if t.get("type") == "view")
    base_table_count = sum(1 for t in tables if t.get("type") == "table")
    enriched_count = sum(1 for t in tables if t.get("table_description") or t.get("data_owner"))
    total_columns = sum(len(t.get("columns") or []) for t in tables)
    largest = max(
        (t for t in tables if t.get("row_count") is not None),
        key=lambda t: int(t.get("row_count") or 0),
        default=None,
    )

    console.print(f"  [bold cyan]Catalog[/bold cyan]  ·  [dim]{table_count} objects[/dim]")

    summary_parts = [
        f"[green]{base_table_count} tables[/green]",
        f"[cyan]{view_count} views[/cyan]" if view_count else "[dim]0 views[/dim]",
        (
            f"[magenta]{total_columns:,} columns[/magenta]"
            if total_columns
            else "[dim]columns unavailable[/dim]"
        ),
    ]
    if enriched_count:
        summary_parts.append(f"[yellow]{enriched_count} enriched[/yellow]")
    if largest is not None:
        summary_parts.append(
            f"[dim]largest: {largest['name']} ({int(largest['row_count']):,} rows)[/dim]"
        )

    console.print(
        Panel(
            "  •  ".join(summary_parts),
            border_style="cyan",
            title="Catalog Summary",
            padding=(0, 1),
        )
    )

    grid = Table(title="Object Detail")
    grid.add_column("Table", style="cyan bold")
    grid.add_column("Type", style="green")
    grid.add_column("Columns", justify="right")
    grid.add_column("Rows", justify="right")
    grid.add_column("Notes", style="dim")

    for t in tables:
        col_count = str(len(t["columns"])) if t["columns"] is not None else "-"
        row_count = f"{t['row_count']:,}" if t["row_count"] is not None else "-"
        notes_parts = []
        if t.get("table_description"):
            notes_parts.append(str(t["table_description"]))
        if t.get("data_owner"):
            notes_parts.append(f"owner: {t['data_owner']}")
        notes = "  |  ".join(notes_parts)
        grid.add_row(t["name"], t["type"], col_count, row_count, notes)

    console.print(grid)


def print_catalog_functions(
    result: dict,
    console: Console | None = None,
) -> None:
    """Print the function catalog as a Rich table."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    if console is None:
        console = Console()

    if not result.get("supported", True):
        console.print("[dim]Function catalog unavailable.[/dim]")
        if result.get("reason"):
            console.print(f"[dim]{result['reason']}[/dim]")
        return

    functions = result.get("functions") or []
    if not functions:
        console.print("[dim]No functions found.[/dim]")
        return

    schema_count = len({f.get("schema", "") for f in functions})
    overloaded = sum(1 for f in functions if int(f.get("overload_count", 0) or 0) > 1)

    console.print(
        f"  [bold cyan]Function Catalog[/bold cyan]  ·  [dim]{result['dialect']}[/dim]"
    )
    console.print(
        Panel(
            "  •  ".join(
                [
                    f"[green]{result['function_count']:,} functions[/green]",
                    f"[cyan]{schema_count} schemas[/cyan]",
                    f"[magenta]{overloaded} overloaded[/magenta]",
                ]
            ),
            border_style="cyan",
            title="Function Summary",
            padding=(0, 1),
        )
    )

    grid = Table(title="Function Detail")
    grid.add_column("Name", style="cyan bold")
    grid.add_column("Schema", style="green")
    grid.add_column("Type")
    grid.add_column("Overloads", justify="right")
    grid.add_column("Returns")
    grid.add_column("Notes", style="dim")

    for entry in functions:
        return_types = ", ".join(entry.get("return_types") or []) or "—"
        notes_parts = []
        languages = entry.get("languages") or []
        if languages:
            notes_parts.append(f"lang: {', '.join(languages)}")
        notes = entry.get("notes") or []
        if notes:
            notes_parts.append(", ".join(notes))
        if entry.get("description"):
            notes_parts.append(str(entry["description"]))
        grid.add_row(
            str(entry.get("name", "")),
            str(entry.get("schema", "")),
            str(entry.get("type", "")),
            f"{int(entry.get('overload_count', 0) or 0):,}",
            return_types,
            "  |  ".join(notes_parts),
        )

    console.print(grid)


def print_query(
    columns: list[str],
    rows: list[dict],
    row_count: int,
    *,
    limited: bool = False,
    sql: str = "",
    console: Console | None = None,
) -> None:
    """Print ad-hoc query results as a Rich table."""
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    if not rows:
        console.print("[dim]Query returned no rows.[/dim]")
        return

    grid = Table(title="Query Results")
    for col in columns:
        grid.add_column(col, style="cyan")

    for row in rows:
        grid.add_row(*(str(v) if v is not None else "" for v in row.values()))

    console.print(grid)
    suffix = " (limit reached)" if limited else ""
    console.print(f"\n  [bold]{row_count}[/bold] row(s) returned{suffix}")


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
                f"{pct}%",
            )
        console.print(grid)


def print_context(
    result: dict,
    console: Console | None = None,
) -> None:
    """Print rich table context as a structured Rich layout."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    if console is None:
        console = Console()

    row_count = result.get("row_count", 0)
    dialect = result.get("dialect", "")
    sampled = result.get("sampled", False)
    sample_size = result.get("sample_size")
    table_name = result.get("table", "")
    table_desc = result.get("table_description") or result.get("table_comment") or ""
    data_owner = result.get("data_owner")
    columns = result.get("columns", [])

    primary_key_count = sum(1 for col in columns if col.get("primary_key"))
    nullable_count = sum(1 for col in columns if col.get("nullable"))
    metadata_count = sum(
        1
        for col in columns
        if col.get("description") or col.get("valid_values") or col.get("pii")
    )
    sampled_columns = sum(1 for col in columns if col.get("sample_values"))

    # Header
    count_str = f"{row_count:,}"
    if sampled and sample_size:
        count_str += f" ({sample_size:,} sampled)"
    title_parts = [f"[bold cyan]{table_name}[/bold cyan]"]
    if dialect:
        title_parts.append(f"[dim]{dialect}[/dim]")
    title_parts.append(f"[dim]{count_str} rows[/dim]")
    console.print("  " + "  ·  ".join(title_parts))
    if table_desc:
        console.print(f"  [italic dim]{table_desc}[/italic dim]")
    if data_owner:
        console.print(f"  [dim]owner:[/dim] {data_owner}")
    console.print(
        Panel(
            "  •  ".join(
                [
                    f"[green]{len(columns)} columns[/green]",
                    (
                        f"[magenta]{primary_key_count} primary keys[/magenta]"
                        if primary_key_count
                        else "[dim]no primary key[/dim]"
                    ),
                    (
                        f"[yellow]{nullable_count} nullable[/yellow]"
                        if nullable_count
                        else "[green]all not null[/green]"
                    ),
                    (
                        f"[cyan]{sampled_columns} with sample values[/cyan]"
                        if sampled_columns
                        else "[dim]no sample values[/dim]"
                    ),
                    (
                        f"[yellow]{metadata_count} enriched[/yellow]"
                        if metadata_count
                        else "[dim]no stored metadata[/dim]"
                    ),
                ]
            ),
            border_style="cyan",
            title="Context Summary",
            padding=(0, 1),
        )
    )

    # Columns table
    grid = Table(title="Column Detail", show_lines=True)
    grid.add_column("Column", style="cyan bold", no_wrap=True)
    grid.add_column("Type", style="dim", no_wrap=True)
    grid.add_column("Null %", justify="right", style="dim")
    grid.add_column("Distinct", justify="right", style="dim")
    grid.add_column("Range / Sample Values", style="dim")
    grid.add_column("Notes", style="dim")

    for col in columns:
        null_pct = col.get("null_pct")
        if isinstance(null_pct, (int, float)):
            if float(null_pct) >= 90:
                null_style = "red"
            elif float(null_pct) >= 20:
                null_style = "yellow"
            else:
                null_style = "dim"
            null_str = f"[{null_style}]{float(null_pct):.1f}%[/{null_style}]"
        else:
            null_str = "—"

        distinct = col.get("distinct_count")
        distinct_str = f"{distinct:,}" if distinct is not None else "—"

        sample = col.get("sample_values")
        min_v = col.get("min")
        max_v = col.get("max")

        if sample:
            range_str = ", ".join(str(v) for v in sample[:5])
            if len(sample) > 5:
                range_str += " …"
        elif min_v is not None and max_v is not None:
            range_str = f"{fmt_value(min_v)}  →  {fmt_value(max_v)}"
        else:
            range_str = "—"

        notes_parts = []
        if col.get("primary_key"):
            notes_parts.append("[cyan]PK[/cyan]")
        if col.get("nullable") is False:
            notes_parts.append("[green]not null[/green]")
        if col.get("pii"):
            notes_parts.append("[red]PII[/red]")
        if isinstance(null_pct, (int, float)) and float(null_pct) >= 20.0:
            notes_parts.append("[yellow]null-heavy[/yellow]")
        valid_values = col.get("valid_values")
        if valid_values:
            allowed = ", ".join(str(v) for v in valid_values[:3])
            if len(valid_values) > 3:
                allowed += " …"
            notes_parts.append(f"[magenta]allowed:[/magenta] {allowed}")
        if col.get("description"):
            notes_parts.append(f"[italic]{col['description']}[/italic]")
        notes_str = "  ".join(notes_parts)

        grid.add_row(
            col.get("name", ""),
            col.get("type", ""),
            null_str,
            distinct_str,
            range_str,
            notes_str,
        )

    console.print(grid)
    if sampled:
        console.print("\n  [dim]Sampled — use --no-sample for exact results (slower)[/dim]")


# ---------------------------------------------------------------------------
# Registry — maps command names to output functions for dispatch_output()
# ---------------------------------------------------------------------------
_CLASSIFY_CATEGORY_LABELS = {
    "constant": ("Constant", "dim", "1 distinct value"),
    "sparse": ("Sparse", "yellow", ">90% null"),
    "high_cardinality": ("High Cardinality", "red", "likely IDs/unique keys"),
    "time": ("Time", "magenta", "date/time columns"),
    "measure": ("Measure", "green", "numeric columns"),
    "low_cardinality": ("Low Cardinality", "cyan", "<50 distinct values"),
    "other": ("Other", "dim", ""),
}


def print_classify(
    table_name: str,
    classification: dict,
    stats: list[dict],
    row_count: int,
    sampled: bool = False,
    sample_size: int | None = None,
    console: Console | None = None,
) -> None:
    """Print column classification as grouped Rich tables."""
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    categories = classification.get("categories", {})

    if not categories:
        console.print(f"[dim]No columns to classify in {table_name}.[/dim]")
        return

    stats_by_name: dict[str, dict] = {}
    for s in stats:
        stats_by_name[s.get("column_name", "")] = s

    sample_note = ""
    if sampled and sample_size:
        sample_note = f"  (sampled {sample_size:,})"
    console.print(
        f"\n[bold]Column Classification: {table_name}[/bold]  ({row_count:,} rows{sample_note})\n"
    )

    for cat_key in (
        "constant",
        "sparse",
        "high_cardinality",
        "time",
        "measure",
        "low_cardinality",
        "other",
    ):
        col_names = categories.get(cat_key, [])
        if not col_names:
            continue

        label, _style, hint = _CLASSIFY_CATEGORY_LABELS.get(cat_key, (cat_key, "dim", ""))
        title = f"{label} ({len(col_names)} columns)"
        if hint:
            title += f" — {hint}"

        grid = Table(title=title, show_lines=False)
        grid.add_column("Column", style="cyan bold")
        grid.add_column("Type", style="green")
        grid.add_column("Null %", justify="right", style="yellow")
        grid.add_column("Distinct", justify="right")

        for name in col_names:
            s = stats_by_name.get(name, {})
            grid.add_row(
                name,
                str(s.get("column_type", "")),
                fmt_value(s.get("null_pct")),
                fmt_value(s.get("distinct_count")),
            )
        console.print(grid)
        console.print()


REGISTRY: dict[str, object] = {
    "search": print_search,
    "inspect": print_inspect,
    "preview": print_preview,
    "profile": print_profile,
    "estimate": print_estimate,
    "plan": print_plan,
    "context": print_context,
    "dist": print_dist,
    "freshness": print_freshness,
    "template": print_template,
    "lineage": print_lineage,
    "snowflake_lineage": print_snowflake_lineage,
    "metadata": print_metadata,
    "metadata_list": print_metadata_list,
    "metadata_search": print_metadata_search,
    "explain": print_explain,
    "diff": print_diff,
    "joins": print_joins,
    "quality": print_quality,
    "assert_check": print_assert_check,
    "pivot": print_pivot,
    "values": print_values,
    "catalog": print_catalog,
    "catalog_functions": print_catalog_functions,
    "query": print_query,
    "frequencies": print_frequencies,
    "classify": print_classify,
}
