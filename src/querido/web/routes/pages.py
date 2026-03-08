"""Full-page routes: landing page and table detail."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request) -> HTMLResponse:
    """Landing page — connection info and table list."""
    connector = request.app.state.connector
    tables = connector.get_tables()

    # Enrich with row counts
    from querido.sql.renderer import render_template

    for tbl in tables:
        try:
            count_sql = render_template("count", connector.dialect, table=tbl["name"])
            tbl["row_count"] = connector.execute(count_sql)[0]["cnt"]
        except Exception:
            tbl["row_count"] = None

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
    tables = connector.get_tables()
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
