# OMNI Retail

A prototype business-intelligence and automation layer for a small-to-medium
retail business. It unifies orders, customers, payments, inventory,
expenses, and website traffic into one structured system, and calculates
the KPIs an owner would otherwise have to piece together by hand.

**Phase 1** (done): data models, a realistic synthetic dataset, and the
core business-logic/service layer.
**Phase 2** (done): a FastAPI JSON API over that service layer, and a
dashboard that consumes it.
**Phase 3** (done): a rules-based automation/alerting layer (the
Action Center) that detects business conditions worth a human's
attention.
**Phase 4** (done): an AI Business Analyst agent that answers
natural-language questions, grounded in the same analytics/alerting
data -- read-only, no data modification or external actions yet.

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
                             # around services/analytics.py (or automation/)
  automation/
    models.py             # Alert dataclass, Severity/AlertType enums
    config.py               # per-rule thresholds
    rules.py                  # one detect_* function per business condition
    engine.py                  # runs every rule, returns alerts sorted by severity
  ai/
    intents.py             # keyword classifier: question -> one of 8 intents
    retrieval.py             # one gather_* "tool" per intent, calling services/automation
    synthesis.py               # evidence -> natural-language answer (pluggable; template today)
    agent.py                    # classify -> retrieve -> synthesize, with graceful fallbacks
dashboard/
  index.html, styles.css, app.js   # static JS dashboard (Chart.js via CDN,
                                     # fetches the JSON API, no build step)
scripts/
  seed_db.py            # builds omni_retail.db and prints a KPI summary
  run_dashboard.py       # runs the API + dashboard on http://127.0.0.1:8000
tests/
  test_analytics.py     # business-logic tests against the seeded dataset
  test_api.py            # API tests (verify responses match the service layer)
  test_automation.py      # rule threshold-crossing tests (deterministic, monkeypatched)
  test_ai_agent.py         # intent classification, grounded-answer, and error-handling tests
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
| `GET /api/alerts?severity=&type=` | currently-open alerts, most severe first |
| `GET /api/alerts/summary` | alert counts by severity and by type |
| `POST /api/assistant/ask` | ask the AI Business Analyst a question (JSON body: `{"question": "..."}`) |
| `GET /api/assistant/examples` | example questions the agent can currently answer |

## Automation & alerting

`omni_retail/automation/` detects business conditions worth a human's
attention and turns each one into a structured `Alert` (type, severity,
what happened, supporting data, a recommended action). Alerts are
computed on demand from current data — there's no alerts table — the
same way the dashboard's KPIs are computed on demand, which keeps this
trivial for a future AI agent to call directly instead of only through
the API.

| Rule | Condition | Data source |
|---|---|---|
| Low stock / out of stock | stock ≤ / = 0 vs. reorder threshold | `inventory_status_counts`, `low_stock_products` |
| Revenue drop | revenue down ≥15% (30d vs. prior 30d) | `revenue` |
| Expense spike | category spend up ≥50%, this calendar month vs. last | `expenses_by_category` |
| Traffic/conversion gap | visitors up ≥25% without conversion rate keeping pace | `website_traffic_summary` |
| Order failure pattern | ≥8% of orders (30d) cancelled or refunded | `order_status_counts` (new) |
| Customer win-back opportunity | top-15 customer by spend, 30+ days since last order | `high_value_customers`, `last_order_date` (new) |

Thresholds live in `automation/config.py` and were calibrated against
the seeded dataset. The dashboard's **Action Center** (top of the
Overview page) lists every open alert with a severity filter; the
sidebar badge shows the count of critical + warning alerts.

## AI Business Analyst

`omni_retail/ai/` answers natural-language business questions, grounded
in the same data the dashboard and Action Center already use. It's a
three-stage, read-only pipeline:

1. **`intents.py`** classifies the question into one of 8 supported
   topics with keyword matching -- not an LLM call. The system, not a
   language model, decides what gets investigated, so the agent can't
   skip investigation or look at the wrong data.
2. **`retrieval.py`** has one `gather_*` function per intent. Each is
   a thin, read-only call into `services/analytics.py` and/or
   `automation/rules.py` -- no business number is computed twice.
   Several intents cross-reference more than one source (e.g. "which
   customers are most valuable" also checks the churn-risk rule and
   flags any top spender who hasn't ordered recently).
3. **`synthesis.py`** turns the retrieved evidence into an answer.
   `TemplateAnswerSynthesizer` (used today) builds it deterministically
   from the numbers, with no external dependency. The interface is
   swappable: a future `LLMAnswerSynthesizer` would implement the same
   `synthesize(question, intent, evidence)` contract, using the
   identical evidence dict as grounding context, and nothing else in
   the pipeline would need to change.

`agent.py` wires the three stages together and handles failure
gracefully: an unrecognized question gets a helpful list of what it
can answer (not an error), and a retrieval failure is caught and
returns a low-confidence response instead of a 500.

**This phase is analysis only.** Every `gather_*` function is
read-only; there is no path from a question to a database write or an
external action. `retrieval.py`'s functions are already shaped like
tools (one function, one data need), so a later phase adding real LLM
tool-calling, agent actions, human-approval gates, or multi-agent
workflows would extend this package rather than restructure it.

## Dashboard

A single-page dashboard (`dashboard/`) served by the same FastAPI app:
an Action Center, an AI Business Analyst chat panel, KPI cards with
period-over-period deltas, a revenue/orders trend chart, top products
and high-value customer tables, low/out-of-stock inventory alerts, an
expense breakdown donut, and a website traffic/conversion trend chart.
A 7D/30D/90D range picker re-fetches everything for the selected
window (the Action Center and AI Assistant use their own
per-rule/per-question periods, independent of that picker). It's plain
HTML/CSS/JS (Chart.js via CDN, no build step) so it's easy to run, and
talks to the API only through `fetch()` — swapping in a
framework-based frontend later wouldn't require touching the backend.

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

- Real LLM-powered synthesis (`ai/synthesis.py`'s `AnswerSynthesizer` interface is ready for it) for more natural phrasing, multi-turn follow-up questions, and open-ended "why" investigation beyond the 8 fixed intents.
- Real tool-calling: let an LLM choose which `retrieval.py` function(s) to call instead of the fixed keyword classifier.
- Agent actions with human approval (e.g. drafting a reorder, a win-back email) -- still no unsupervised writes.
- Anomaly detection, forecasting, and customer segmentation beyond fixed thresholds.
- Multi-agent workflows and external integrations (e.g. actually sending the win-back email, filing the reorder).
