"""HTMX fragment endpoints — return partial HTML for tab content."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/fragments")


@router.get("/inspect/{table}", response_class=HTMLResponse)
async def inspect_fragment(request: Request, table: str) -> HTMLResponse:
    """Inspect tab content."""
    from querido.connectors.base import validate_table_name
    from querido.core.inspect import get_inspect

    validate_table_name(table)
    connector = request.app.state.connector
    result = get_inspect(connector, table, verbose=True)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/inspect.html",
        {
            "table_name": table,
            "columns": result["columns"],
            "row_count": result["row_count"],
            "table_comment": result["table_comment"],
        },
    )


@router.get("/preview/{table}", response_class=HTMLResponse)
async def preview_fragment(request: Request, table: str, limit: int = 50) -> HTMLResponse:
    """Preview tab content."""
    from querido.connectors.base import validate_table_name
    from querido.core.preview import get_preview

    validate_table_name(table)
    connector = request.app.state.connector
    data = get_preview(connector, table, limit=limit)

    headers = list(data[0].keys()) if data else []

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/preview.html",
        {
            "table_name": table,
            "headers": headers,
            "rows": data,
            "limit": limit,
        },
    )


@router.get("/profile/{table}", response_class=HTMLResponse)
async def profile_fragment(request: Request, table: str) -> HTMLResponse:
    """Profile tab content."""
    from querido.connectors.base import validate_table_name
    from querido.core.profile import get_profile

    validate_table_name(table)
    connector = request.app.state.connector
    result = get_profile(connector, table)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/profile.html",
        {
            "table_name": table,
            "stats": result["stats"],
            "row_count": result["row_count"],
            "sampled": result["sampled"],
            "sample_size": result["sample_size"],
        },
    )


@router.get("/dist/{table}/{column}", response_class=HTMLResponse)
async def dist_fragment(request: Request, table: str, column: str) -> HTMLResponse:
    """Distribution panel content for a single column."""
    from querido.connectors.base import validate_column_name, validate_table_name
    from querido.core.dist import get_distribution

    validate_table_name(table)
    validate_column_name(column)
    connector = request.app.state.connector
    result = get_distribution(connector, table, column)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/dist.html",
        {"dist_result": result},
    )


@router.get("/template/{table}", response_class=HTMLResponse)
async def template_fragment(request: Request, table: str) -> HTMLResponse:
    """Template tab content."""
    from querido.connectors.base import validate_table_name
    from querido.core.template import get_template

    validate_table_name(table)
    connector = request.app.state.connector
    result = get_template(connector, table)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/template.html",
        {"template": result},
    )


@router.get("/lineage/{table}", response_class=HTMLResponse)
async def lineage_fragment(request: Request, table: str) -> HTMLResponse:
    """Lineage tab content."""
    from querido.connectors.base import validate_table_name
    from querido.core.lineage import get_view_definition

    validate_table_name(table)
    connector = request.app.state.connector
    try:
        result = get_view_definition(connector, table)
    except LookupError:
        return HTMLResponse("<p class='empty-msg'>Not a view — no lineage available.</p>")

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/lineage.html",
        {"lineage": result},
    )


@router.get("/search", response_class=HTMLResponse)
async def search_fragment(request: Request, q: str = "") -> HTMLResponse:
    """Search/filter table list."""
    from querido.core.search import search_metadata

    connector = request.app.state.connector

    if not q.strip():
        tables = connector.get_tables()
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "partials/table_list.html",
            {"tables": tables},
        )

    results = search_metadata(connector, q, "all")

    # Deduplicate to unique table names while preserving match info
    seen: set[str] = set()
    tables = []
    for r in results:
        if r["table_name"] not in seen:
            seen.add(r["table_name"])
            tables.append({"name": r["table_name"], "type": r["table_type"]})

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/table_list.html",
        {"tables": tables, "query": q},
    )
