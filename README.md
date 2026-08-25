# OMNI Retail

A prototype business-intelligence and automation layer for a small-to-medium
retail business. It unifies orders, customers, payments, inventory,
expenses, and website traffic into one structured system, and calculates
the KPIs an owner would otherwise have to piece together by hand.

**Phase 1** (done): data models, a realistic synthetic dataset, and the
core business-logic/service layer.
**Phase 2** (done): a FastAPI JSON API over that service layer, and a
dashboard that consumes it. Automation/alerting and AI-assisted
analysis build on top of this in later phases.

## Project layout

```
omni_retail/
  database.py        # SQLAlchemy engine/session setup
  models/             # ORM models: Customer, Product, Order, OrderItem,
                       # Payment, Inventory, Expense, WebsiteVisit
  data/
    catalog.py         # hand-authored product catalog (name/category/price/cost)
    seed.py             # synthetic dataset generator (seeded, reproducible)
  services/
    analytics.py        # KPI calculations: revenue, AOV, top products,
                         # high-value customers, inventory status,
                         # expenses, estimated profit, conversion rate,
                         # revenue/traffic trends
  api/
    app.py               # FastAPI app: routers + static dashboard mount
    dependencies.py       # DB session dependency
    schemas.py             # Pydantic response models
    routers/                # one router per resource, each a thin wrapper
                             # around services/analytics.py
dashboard/
  index.html, styles.css, app.js   # static JS dashboard (Chart.js via CDN,
                                     # fetches the JSON API, no build step)
scripts/
  seed_db.py            # builds omni_retail.db and prints a KPI summary
  run_dashboard.py       # runs the API + dashboard on http://127.0.0.1:8000
tests/
  test_analytics.py     # business-logic tests against the seeded dataset
  test_api.py            # API tests (verify responses match the service layer)
```

## Getting started

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows
# .venv/bin/pip install -r requirements.txt     # macOS/Linux

python scripts/seed_db.py       # builds omni_retail.db with demo data
python -m pytest                 # run the test suite
python scripts/run_dashboard.py   # http://127.0.0.1:8000 (dashboard)
                                    # http://127.0.0.1:8000/docs (API docs)
```

## API

All endpoints are read-only GETs, most accepting optional `start`/`end`
(ISO date) query params to scope the period; omitting both returns
all-time figures. Every route is a thin wrapper around
`services/analytics.py` — no business logic lives in the API layer.

| Endpoint | Returns |
|---|---|
| `GET /api/kpis/summary` | revenue, orders, AOV, estimated profit, visitors, conversion rate — bundled for the dashboard cards |
| `GET /api/revenue` | total revenue |
| `GET /api/revenue/trend` | daily revenue + order count |
| `GET /api/orders/count` | order count |
| `GET /api/orders/average-value` | average order value |
| `GET /api/products/top?limit=&by=revenue\|units` | top products |
| `GET /api/customers/high-value?limit=` | top customers by spend |
| `GET /api/inventory/status` | healthy/low/out-of-stock counts + flagged items |
| `GET /api/expenses` | total + breakdown by category |
| `GET /api/profit/estimated` | estimated profit + its components |
| `GET /api/website/traffic` | visitors, sessions, conversions, conversion rate |
| `GET /api/website/traffic/trend` | daily traffic + conversion rate |
| `GET /api/website/conversion-rate` | conversion rate |

## Dashboard

A single-page dashboard (`dashboard/`) served by the same FastAPI app:
KPI cards with period-over-period deltas, a revenue/orders trend chart,
top products and high-value customer tables, low/out-of-stock
inventory alerts, an expense breakdown donut, and a website
traffic/conversion trend chart. A 7D/30D/90D range picker re-fetches
everything for the selected window. It's plain HTML/CSS/JS (Chart.js
via CDN, no build step) so it's easy to run, and talks to the API only
through `fetch()` — swapping in a framework-based frontend later
wouldn't require touching the backend.

## Data model

- **Customer** — profile + join date; spending/order stats are derived, not stored.
- **Product** — catalog entry with selling price and cost.
- **Order** / **OrderItem** — an order has one or more line items (product, quantity, unit price); `status` is one of `completed`, `pending`, `cancelled`, `refunded`.
- **Payment** — one per order, with method and status (`success`, `failed`, `refunded`).
- **Inventory** — current stock and reorder threshold per product; status (`healthy` / `low_stock` / `out_of_stock`) is computed, not stored.
- **Expense** — category, amount, date, description.
- **WebsiteVisit** — one row per (date, traffic source, device) with visitors/sessions/conversions.

## Business logic

All KPI definitions live in [`omni_retail/services/analytics.py`](omni_retail/services/analytics.py) so dashboards, alerts, and future AI features share one source of truth:

- **Revenue** — sum of line totals on `completed` orders only.
- **Average Order Value** — revenue ÷ order count.
- **Top Products** — ranked by revenue or units sold.
- **High-Value Customers** — ranked by total spend, with order count and AOV.
- **Inventory Status** — stock vs. reorder threshold → healthy / low / out of stock.
- **Expenses** — total and by category.
- **Estimated Profit** — revenue − cost of goods sold − operating expenses.
- **Website Conversion Rate** — conversions ÷ visitors × 100.

## Synthetic dataset

`omni_retail/data/seed.py` generates a reproducible (seeded) demo dataset with deliberate, realistic patterns instead of uniform randomness:

- A handful of catalog products are popular; several are slow movers.
- Customers fall into spending tiers (bargain / regular / VIP), producing genuine repeat and high-value customers.
- Order volume is seasonal (a Nov/Dec bump, a Feb dip) and split across in-store/online channels.
- A share of orders are cancelled, refunded, or still pending; payments include some failures.
- A few products are deliberately left low or out of stock.
- Logistics expenses spike sharply one month, for anomaly-detection demos.
- One recent week has a website traffic spike with conversions that don't follow — for the "traffic up, sales flat" automation scenario.

**Known simplification:** expenses are recorded once per month per category (like a real bill), while revenue is tracked per order. A rolling window that spans a month boundary can therefore include zero, one, or two months of a given expense category, which can make short-window profit figures noisy. This is acceptable for the prototype; a production system would prorate or accrue expenses daily.

## Next phases

- REST API layer (FastAPI) exposing the services above.
- Dashboard frontend.
- Automation/alerting (low stock, sales drops, expense anomalies, at-risk customers, conversion problems).
- AI-assisted natural-language queries and insight generation.
