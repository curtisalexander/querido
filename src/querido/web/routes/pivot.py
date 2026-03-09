"""Pivot builder endpoints."""

from __future__ import annotations

from functools import partial

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/table/{name}/pivot", response_class=HTMLResponse)
async def pivot_page(request: Request, name: str) -> HTMLResponse:
    """Pivot builder page with column/aggregation selection form."""
    import asyncio

    from querido.connectors.base import validate_table_name

    validate_table_name(name)
    connector = request.app.state.connector

    loop = asyncio.get_running_loop()
    columns = await loop.run_in_executor(None, connector.get_columns, name)
    tables = await loop.run_in_executor(None, connector.get_tables)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pivot.html",
        {
            "connection_name": request.app.state.connection_name,
            "table_name": name,
            "columns": columns,
            "tables": tables,
        },
    )


@router.post("/fragments/pivot/{table}", response_class=HTMLResponse)
async def pivot_result(
    request: Request,
    table: str,
    rows: list[str] = Form(...),  # noqa: B008
    values: list[str] = Form(...),  # noqa: B008
    agg: str = Form("COUNT"),
) -> HTMLResponse:
    """Execute pivot query and return result table fragment."""
    import asyncio

    from querido.connectors.base import validate_column_name, validate_table_name
    from querido.core.pivot import get_pivot

    validate_table_name(table)
    for col in rows:
        validate_column_name(col)
    for col in values:
        validate_column_name(col)

    import html as _html

    valid_aggs = {"COUNT", "SUM", "AVG", "MIN", "MAX"}
    if agg.upper() not in valid_aggs:
        return HTMLResponse(
            f"<p class='error-msg'>Invalid aggregation: {_html.escape(agg)}. "
            f"Must be one of: {', '.join(sorted(valid_aggs))}</p>"
        )

    connector = request.app.state.connector
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, partial(get_pivot, connector, table, rows=rows, values=values, agg=agg.upper())
    )

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/pivot_result.html",
        {
            "headers": result["headers"],
            "rows": result["rows"],
            "sql": result["sql"],
        },
    )
