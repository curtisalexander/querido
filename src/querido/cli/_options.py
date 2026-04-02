"""Shared CLI option definitions for reuse across command modules."""

import typer

table_opt = typer.Option(..., "--table", "-t", help="Table name.")
conn_opt = typer.Option(..., "--connection", "-c", help="Named connection or file path.")
dbtype_opt = typer.Option(
    None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
)
