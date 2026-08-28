from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
)

DASHBOARD_DIR = Path(__file__).resolve().parent.parent.parent / "dashboard"


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

    if DASHBOARD_DIR.exists():
        app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")

    return app


app = create_app()
