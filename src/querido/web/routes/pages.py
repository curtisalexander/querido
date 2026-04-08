"""Full-page routes: landing page and table detail."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

if TYPE_CHECKING:
    from querido.connectors.base import Connector

router = APIRouter()


def _get_tables_with_counts(connector: Connector) -> list[dict]:
    """Fetch table list enriched with row counts (blocking)."""
    from querido.sql.renderer import render_template

    tables = connector.get_tables()
    for tbl in tables:
        try:
            count_sql = render_template("count", connector.dialect, table=tbl["name"])
            tbl["row_count"] = connector.execute(count_sql)[0]["cnt"]
        except Exception:
            tbl["row_count"] = None
    return tables


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request) -> HTMLResponse:
    """Landing page — connection info and table list."""
    connector = request.app.state.connector
    loop = asyncio.get_running_loop()
    executor = request.app.state.executor
    tables = await loop.run_in_executor(executor, partial(_get_tables_with_counts, connector))

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "landing.html",
        {
            "connection_name": request.app.state.connection_name,
            "tables": tables,
        },
    )


@router.get("/table/{name}", response_class=HTMLResponse)
async def table_detail(request: Request, name: str) -> HTMLResponse:
    """Table detail page with tab navigation."""
    from querido.connectors.base import validate_table_name

    validate_table_name(name)

    connector = request.app.state.connector
    loop = asyncio.get_running_loop()
    tables = await loop.run_in_executor(request.app.state.executor, connector.get_tables)
    table_info = next((t for t in tables if t["name"] == name), None)
    table_type = table_info["type"] if table_info else "table"

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "table.html",
        {
            "connection_name": request.app.state.connection_name,
            "table_name": name,
            "table_type": table_type,
            "tables": tables,
        },
    )
