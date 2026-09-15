from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from omni_retail.api.routers import (
    alerts,
    customers,
    expenses,
    inventory,
    kpis,
    orders,
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
)

DASHBOARD_DIR = Path(__file__).resolve().parent.parent.parent / "dashboard"


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

    for router in ROUTERS:
        app.include_router(router)

    if DASHBOARD_DIR.exists():
        app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")

    return app


app = create_app()
