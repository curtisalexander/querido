import typer

app = typer.Typer(help="Generate documentation templates for tables.")


@app.callback(invoke_without_command=True)
def template(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    sample_values: int = typer.Option(
        3, "--sample-values", min=0, max=10, help="Number of sample values per column (0 to skip)."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
) -> None:
    """Generate a documentation template for a table.

    Auto-populates column metadata (name, type, nullable, distinct count,
    min/max, sample values) and leaves placeholders for business definitions,
    data owner, and notes.
    """
    from querido.cli._util import (
        check_table_exists,
        friendly_errors,
        is_numeric_type,
        maybe_show_sql,
        set_last_sql,
    )

    @friendly_errors
    def _run() -> None:
        from querido.config import resolve_connection
        from querido.connectors.base import validate_column_name, validate_table_name
        from querido.connectors.factory import create_connector
        from querido.sql.renderer import render_template

        validate_table_name(table)
        config = resolve_connection(connection, db_type)

        with create_connector(config) as connector:
            from rich.console import Console

            console = Console(stderr=True)

            check_table_exists(connector, table)

            with console.status(f"Generating template for [bold]{table}[/bold]…"):
                # 1. Get column metadata (inspect)
                columns = connector.get_columns(table)
                table_comment = connector.get_table_comment(table)

                # 2. Get row count
                count_sql = render_template("count", connector.dialect, table=table)
                maybe_show_sql(count_sql)
                set_last_sql(count_sql)
                row_count = connector.execute(count_sql)[0]["cnt"]

                # 3. Get profile stats (distinct, nulls, min/max)
                col_info = [
                    {
                        "name": validate_column_name(c["name"]),
                        "type": c["type"],
                        "numeric": is_numeric_type(c["type"]),
                    }
                    for c in columns
                ]
                profile_sql = render_template(
                    "profile", connector.dialect, columns=col_info, source=table
                )
                maybe_show_sql(profile_sql)
                set_last_sql(profile_sql)
                profile_data = connector.execute(profile_sql)

                # Index profile by column name
                profile_by_col: dict[str, dict] = {}
                for row in profile_data:
                    profile_by_col[row["column_name"]] = row

                # 4. Get sample values (preview a few rows)
                sample_rows: list[dict] = []
                if sample_values > 0:
                    preview_sql = render_template(
                        "preview", connector.dialect, table=table, limit=sample_values
                    )
                    maybe_show_sql(preview_sql)
                    set_last_sql(preview_sql)
                    sample_rows = connector.execute(preview_sql)

            # 5. Build template rows
            template_rows: list[dict] = []
            for col in columns:
                name = col["name"]
                stats = profile_by_col.get(name, {})

                # Collect sample values for this column
                samples: list[str] = []
                if sample_rows:
                    for row in sample_rows:
                        val = row.get(name)
                        if val is not None:
                            samples.append(str(val))

                template_rows.append(
                    {
                        "name": name,
                        "type": col["type"],
                        "nullable": col["nullable"],
                        "primary_key": col.get("primary_key", False),
                        "comment": col.get("comment") or "",
                        "distinct_count": stats.get("distinct_count"),
                        "null_count": stats.get("null_count"),
                        "null_pct": stats.get("null_pct"),
                        "min_val": stats.get("min_val"),
                        "max_val": stats.get("max_val"),
                        "min_length": stats.get("min_length"),
                        "max_length": stats.get("max_length"),
                        "sample_values": ", ".join(samples) if samples else "",
                    }
                )

            template_result = {
                "table": table,
                "table_comment": table_comment or "",
                "row_count": row_count,
                "columns": template_rows,
            }

            from querido.cli._util import get_output_format

            fmt = get_output_format()
            if fmt == "rich":
                from querido.output.console import print_template

                print_template(template_result)
            else:
                from querido.output.formats import format_template

                print(format_template(template_result, fmt))

    _run()
