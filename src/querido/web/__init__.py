"""FastAPI web application factory for ``qdo serve``."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from querido.connectors.base import Connector

_HERE = Path(__file__).resolve().parent


def create_app(connector: Connector, connection_name: str) -> FastAPI:
    """Build and return a configured FastAPI application.

    The *connector* is stored on ``app.state`` so route handlers can access it.
    """
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates

    app = FastAPI(title="qdo", docs_url=None, redoc_url=None)

    # State ----------------------------------------------------------------
    app.state.connector = connector
    app.state.connection_name = connection_name
    app.state.templates = Jinja2Templates(directory=str(_HERE / "templates"))
    app.state.running_queries: dict[str, object] = {}  # request_id → connector for cancel

    # Static files ---------------------------------------------------------
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

    # Error handlers -------------------------------------------------------
    import html as _html

    from fastapi import Request as _Req
    from fastapi.responses import HTMLResponse as _HTML

    @app.exception_handler(ValueError)
    async def value_error_handler(request: _Req, exc: ValueError) -> _HTML:
        return _HTML(f"<p class='error-msg'>{_html.escape(str(exc))}</p>", status_code=400)

    @app.exception_handler(LookupError)
    async def lookup_error_handler(request: _Req, exc: LookupError) -> _HTML:
        return _HTML(f"<p class='error-msg'>{_html.escape(str(exc))}</p>", status_code=404)

    # Routes ---------------------------------------------------------------
    from querido.web.routes.fragments import router as fragments_router
    from querido.web.routes.pages import router as pages_router
    from querido.web.routes.pivot import router as pivot_router

    app.include_router(pages_router)
    app.include_router(fragments_router)
    app.include_router(pivot_router)

    return app
