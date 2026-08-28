from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from omni_retail.api.routers import (
    alerts,
    assistant,
    customers,
    expenses,
    inventory,
    kpis,
    orders,
    pos,
    products,
    profit,
    revenue,
    storefront,
    website,
)

ROUTERS = (
    kpis.router,
    revenue.router,
    orders.router,
    products.router,
    customers.router,
    inventory.router,
    expenses.router,
    profit.router,
    website.router,
    alerts.router,
    assistant.router,
    pos.router,
    storefront.router,
)

DASHBOARD_DIR = Path(__file__).resolve().parent.parent.parent / "dashboard"
STOREFRONT_DIR = Path(__file__).resolve().parent.parent.parent / "storefront"


class NoCacheHTMLMiddleware(BaseHTTPMiddleware):
    """Prevent the browser from caching index.html.

    The dashboard's own cache-busting scheme (styles.css?v=N,
    app.js?v=N) only works if the browser re-fetches index.html to see
    a new version number in the first place. Without this, browsers
    apply heuristic caching to the HTML document itself, so a bumped
    asset version can sit on disk indefinitely while every visitor
    keeps loading the stale document that still points at the old one
    -- this caused a real fix to appear "not to work" repeatedly during
    development. Static assets (JS/CSS/images) are left with their
    default caching; only text/html responses are affected.
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


def create_app() -> FastAPI:
    app = FastAPI(title="OMNI Retail API", version="0.1.0")

    # Permissive for local prototype use; tighten allow_origins before any
    # real deployment.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(NoCacheHTMLMiddleware)

    for router in ROUTERS:
        app.include_router(router)

    # Starlette's Mount("/store", ...) only matches "/store/..." -- the bare
    # "/store" (no trailing slash, which is what a typed URL or a plain link
    # href="/store" produces) 404s without this explicit redirect.
    @app.get("/store", include_in_schema=False)
    def _redirect_to_store() -> RedirectResponse:
        return RedirectResponse(url="/store/")

    # /store (customer storefront) must be mounted before / (admin
    # dashboard), since the root mount is a catch-all.
    if STOREFRONT_DIR.exists():
        app.mount("/store", StaticFiles(directory=STOREFRONT_DIR, html=True), name="storefront")

    if DASHBOARD_DIR.exists():
        app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")

    return app


app = create_app()
