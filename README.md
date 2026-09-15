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
**Phase 5** (done): a point-of-sale/transaction layer -- the first part
of the system that writes data. Completing a sale creates the order,
decrements inventory, and is immediately reflected everywhere else
(dashboard, alerts, AI assistant), since none of those recompute or
cache -- they just read current state.
**Phase 6** (done): a customer-facing storefront (`/store`) built on
the exact same `transactions.complete_sale()` as the POS -- browse,
cart, checkout with a simulated payment (success/decline), account
login/registration, and order history. Online and in-store sales are
the same kind of `Order` row; the admin dashboard, alerts, and AI
assistant don't know or care which channel a sale came from.
**Phase 7** (done): agentic actions with human approval. The AI turns
open alerts into structured, proposed business actions (a win-back
offer, a restock request, a follow-up task) -- but never runs any of
them itself. An admin reviews the evidence, can edit the proposed
parameters, and only then approves or rejects; approval triggers a
simulated external action (email, purchase order) behind a swappable
executor interface, and every step is kept in an auditable history.
**Phase 8** (done): an optional, opt-in real LLM agent mode for the AI
Business Analyst -- question -> LLM reasoning -> tool selection -> real
tool execution -> LLM synthesis -> grounded answer, in place of the
fixed keyword classifier. The Phase 4 deterministic pipeline remains
the permanent default and fallback; the LLM's only write-shaped
capability is proposing a Phase 7 action, and it structurally cannot
approve or execute one.

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
  transactions/
    models.py             # Cart/CartItem/SaleReceipt dataclasses + TransactionError hierarchy
    service.py               # complete_sale() -- the only place anything is written
  payments/
    models.py             # PaymentRequest/PaymentResult
    processor.py            # PaymentProcessor interface + SimulatedPaymentProcessor
  auth/
    passwords.py          # PBKDF2 password hashing (storefront accounts only)
    sessions.py            # in-memory bearer-token sessions
  actions/
    models.py             # ProposalDraft dataclass + action-lifecycle exceptions
    proposals.py            # Alert -> ProposalDraft, one builder per alert type
    executors.py              # ActionExecutor interface + simulated email/task/PO executors
    service.py                 # create_proposals/approve_action/reject_action/execute_action --
                                # the only place anything is written to agent_actions
dashboard/
  index.html, styles.css, app.js   # static JS admin dashboard (Chart.js via CDN,
                                     # fetches the JSON API, no build step)
storefront/
  index.html, styles.css, app.js   # static JS customer storefront, served at /store,
                                     # visually distinct from the admin dashboard
scripts/
  seed_db.py            # builds omni_retail.db and prints a KPI summary
  run_dashboard.py       # runs the API + dashboard on http://127.0.0.1:8000
tests/
  test_analytics.py     # business-logic tests against the seeded dataset
  test_api.py            # API tests (verify responses match the service layer)
  test_automation.py      # rule threshold-crossing tests (deterministic, monkeypatched)
  test_ai_agent.py         # intent classification, grounded-answer, and error-handling tests
  test_transactions.py      # complete_sale() unit tests, each isolated in its own in-memory DB
  test_pos_api.py            # POS/orders API tests, same isolation
  test_payments.py            # SimulatedPaymentProcessor unit tests
  test_storefront_api.py       # register/login/checkout/my-orders, same isolation
  test_actions.py               # proposal/approve/reject/execute lifecycle, service layer
  test_actions_api.py            # same lifecycle through the HTTP API
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

Most endpoints are read-only GETs accepting optional `start`/`end`
(ISO date) query params to scope the period; omitting both returns
all-time figures. Every route is a thin wrapper around
`services/analytics.py` (or `transactions`/`payments` for the two
write endpoints) — no business logic lives in the API layer.

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
| `GET /api/products` | full catalog with live stock -- for the POS product picker |
| `GET /api/customers/search?q=` | name/email typeahead -- for the POS customer picker |
| `POST /api/pos/checkout` | complete a sale (the only write endpoint in the API) |
| `GET /api/orders?status=&limit=&offset=` | paginated transaction list (admin, unauthenticated) |
| `GET /api/orders/{id}` | full line-item detail for one order (admin, unauthenticated) |
| `GET /api/products/{id}` | single product with live stock -- for the storefront Product Details page |
| `POST /api/storefront/auth/register` | create a storefront account |
| `POST /api/storefront/auth/login` | log in, returns a bearer token |
| `GET /api/storefront/me` | the logged-in customer (requires `Authorization: Bearer <token>`) |
| `POST /api/storefront/checkout` | complete an online purchase (guest or logged-in); same `complete_sale()` as POS |
| `GET /api/storefront/orders` | the logged-in customer's own order history |
| `GET /api/storefront/orders/{id}` | one of the logged-in customer's own orders (404 if it isn't theirs) |
| `POST /api/actions/generate` | run the AI's proposal pass against current alerts; returns only newly created proposals |
| `GET /api/actions?status=` | all agent actions, most recent first; optionally filter by status |
| `GET /api/actions/{id}` | one agent action, with full evidence/parameters/decision/result |
| `POST /api/actions/{id}/approve` | approve a proposed action (optionally with edited parameters) and execute it |
| `POST /api/actions/{id}/reject` | reject a proposed action (terminal; optional reason) |

## Point of sale & transactions

`omni_retail/transactions/` is the only part of this codebase that
writes to the database. `complete_sale(session, cart)` is a pure
function -- session and a `Cart` in, a `SaleReceipt` out, or a specific
`TransactionError` raised -- with no knowledge of HTTP, the POS UI, or
any particular front end. **Both** the POS API (`/api/pos/checkout`)
and the storefront API (`/api/storefront/checkout`) build a `Cart` and
call this exact same function; neither reimplements any part of
checkout. Online vs. in-store is just `Cart.channel`.

Every validation check (empty cart, non-positive quantity, unknown
product, insufficient stock -- re-checked against *current* DB state,
so a product that went out of stock between browsing and checkout is
caught here too -- invalid discount, unknown customer, invalid payment
method) runs **before** the first database write, so a rejected sale
is guaranteed to leave the database untouched.

**Payment** (`omni_retail/payments/`): `complete_sale()` charges the
cart via a `PaymentProcessor` interface before writing anything.
`SimulatedPaymentProcessor` (the only implementation today) never
contacts a real provider or stores real card data; it uses Stripe's
own well-known test-card convention (`4242...4242` succeeds,
`4000...0002` declines) so the decline path is genuinely
demonstrable. A successful charge writes the sale exactly as before:
`Order` COMPLETED, `Inventory` decremented, `Payment` SUCCESS. A
**declined** charge still writes an audit record -- `Order` CANCELLED
with its line items, `Payment` FAILED, referencing the same
`PaymentResult` -- but inventory is never touched. Swapping in a real
provider later means writing a `StripePaymentProcessor` and passing an
instance to `complete_sale()`; nothing else changes.

**Duplicate submissions:** the storefront generates one idempotency
key per checkout attempt; resending the same key (a double-click, a
network retry) replays the first `SaleReceipt` instead of charging
twice. The cache lives at the API layer (`api/routers/storefront.py`),
not inside `complete_sale()`, keeping the transaction function itself
free of HTTP-level concerns.

**Discounts:** a cart discount (percent or a fixed dollar amount) is
pro-rated across line items and baked directly into each
`OrderItem.unit_price` (the price actually charged). `Order.discount_total`
records the dollar amount for receipts/audits. This means
`services/analytics.py` needed **zero changes** for discounts --
revenue, AOV, and everything else already sum `quantity × unit_price`,
which is already the post-discount price.

**"Customer purchase history" needed no new code.** Nothing in this
app stores customer stats as counters -- `high_value_customers()`,
`last_order_date()`, etc. all compute from `Order`/`OrderItem` on every
call. The moment a sale is completed, every dashboard number, every
alert, and the AI agent's next answer are already correct.

**Guest checkout:** `Order.customer_id` is nullable. A `None` means a
guest sale; `high_value_customers()` already inner-joins `Order` to
`Customer`, so guest orders simply don't appear in customer rankings,
which is correct.

## Customer storefront

`storefront/` (served at `/store`) is a separate, visually distinct
static site -- warm/retail branding, a serif display font, hash-routed
views (Home, Catalogue with search/filter, Product Details, Cart,
Checkout, Login/Register, My Orders) -- from the indigo/dark admin
dashboard at `/`. Each has a header link to the other, for demoing
both sides of the system. Checkout is a visible state machine: Review
→ Payment → **Processing** (a brief animated wait, purely a frontend
UX beat -- the backend call is already synchronous and fast) →
Success or Failure → Confirmation. A failed payment leaves the cart
untouched so the customer can just retry.

**Auth is intentionally lightweight -- a prototype login, not
production security.** `omni_retail/auth/` hashes passwords with
stdlib PBKDF2-HMAC-SHA256 (no bcrypt/argon2 dependency) and issues an
opaque bearer token backed by an in-memory `dict` (no JWT library, no
persistent session store). Two demo accounts are seeded with known
credentials (`demo@omniretail.test` / `password123`, plus a second
regular-tier account) so the purchase flow can be shown without
registering first -- registration is equally functional for any other
account, seeded or not.

**"My Orders" is deliberately not the same endpoint the admin
dashboard uses.** `GET /api/orders/{id}` is fine for an unauthenticated
internal staff tool, but a customer-facing equivalent must not let any
visitor enumerate other customers' order details by guessing IDs --
`GET /api/storefront/orders/{id}` checks `order.customer_id` against
the logged-in customer and 404s otherwise.

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

**Phase 4 itself remains analysis only** -- every `gather_*` function
is read-only. Phase 7 (below) is the first part of this codebase where
the AI's output can lead to a write, and even then only through an
explicit human approval step.

## LLM agent mode (Phase 8)

`omni_retail/ai/llm/` is an optional second path through the AI
Business Analyst, alongside (never instead of) the Phase 4 pipeline:

```
User question -> LLM reasoning -> tool selection -> tool execution
    -> tool result -> LLM reasoning/synthesis -> grounded answer
```

**Opt-in and fail-safe by construction.** It only activates when
`OMNI_LLM_ENABLED=true` *and* `ANTHROPIC_API_KEY` is set. Missing
either, a missing `anthropic` package, a provider timeout/failure, or
the bounded tool-call loop running out its budget all fall straight
back to the deterministic Phase 4 pipeline (`ai/agent.py`) -- the app
never breaks and never silently returns an ungrounded answer. A
genuine programming bug is deliberately *not* caught by that fallback:
`ai/agent.py` only catches `LLMProviderError` and
`OrchestrationLimitExceeded` by name, so a real bug stays visible
instead of masquerading as "the LLM was unavailable."

**Provider-abstracted.** `ai/llm/provider.py` defines a vendor-neutral
`LLMProvider` interface; `ai/llm/anthropic_provider.py` is the only
file that imports the `anthropic` SDK. Swapping or adding a provider
means writing one more class and wiring it into
`ai/llm/__init__.py::get_provider()` -- the orchestrator and `agent.py`
never change.

**Tools reuse Phase 4 and Phase 7 verbatim -- nothing is duplicated.**
`ai/llm/tools.py` registers:
- 8 read-only tools, one per Phase 4 intent, each calling the same
  `ai/retrieval.py` gatherer and `TemplateAnswerSynthesizer` the
  deterministic pipeline uses, so the LLM's evidence is identical to
  what a human would see from the fixed pipeline.
- `search_customers`, `get_order`, `get_product` -- thin read-only
  wrappers around `services/analytics.py`, for drilling into a specific
  record.
- `propose_action` -- the one write-shaped tool. It can only call
  `actions/service.py::create_manual_proposal()`, which can only
  construct an `AgentAction` with `status=PROPOSED` (hardcoded, not a
  parameter). **`approve_action` and `execute_action` are never
  registered as tools**, so no model output can express approving or
  executing anything -- combined with `execute_action()`'s existing
  `ActionNotApprovedError` guard, an LLM-originated proposal goes
  through the exact same human-review gate as a Phase 7 rule-derived
  one.

**Bounded and traced.** The loop in `ai/llm/orchestrator.py` stops
after `OMNI_LLM_MAX_ITERATIONS` round trips or `OMNI_LLM_MAX_TOOL_CALLS`
total tool calls, whichever comes first, raising
`OrchestrationLimitExceeded` (caught by `agent.py`) rather than running
unbounded. An unknown or malformed tool call from the model is
recoverable *within* the loop -- it's fed back as a tool error result,
not treated as a fatal failure. Every tool call is logged and recorded
on the response as `tool_trace` (empty for the deterministic path).

See `.env.example` for the full list of environment variables.

## Agent actions & human approval

`omni_retail/actions/` turns open alerts (from the same
`automation/rules.py` used by the Action Center) into structured,
proposed business actions -- and enforces that **none of them run
without an explicit human decision**.

**Lifecycle:** `proposed -> approved -> executed | failed`, or
`proposed -> rejected` (terminal). Every action records its business
reason, supporting evidence (the alert's own data), proposed
parameters, expected outcome, a risk level, who decided it and when,
and the execution result -- so `AI recommendation -> human decision ->
executed action -> result` is always visible for any action, not just
the most recent one.

| Alert type | Proposed action | Editable parameters |
|---|---|---|
| Customer win-back opportunity | Win-back offer: a drafted message and discount % | offer %, message text, recipient email |
| Low stock / out of stock | Restock request | restock quantity |
| Revenue drop, expense spike, traffic/conversion gap, order failure pattern | Follow-up task (also how a non-customer, non-stock alert gets acknowledged) | task description, priority |

**The approval gate lives in the service layer, not the API.**
`execute_action()` raises `ActionNotApprovedError` for anything that
isn't `APPROVED` -- checked directly by tests that call it without
going through `approve_action()` first, so the guarantee holds
regardless of caller, not just because the API doesn't expose an
"execute" button. Approving an action calls `approve_action()` then
immediately `execute_action()` in the same request (there's no job
queue in this prototype), but they remain two distinct functions so a
future version could queue execution asynchronously without touching
what "approved" means.

**External actions are simulated behind an `ActionExecutor`
interface** (`actions/executors.py`), the same pattern as
`payments.PaymentProcessor`: `SimulatedEmailExecutor` (win-back offers),
`SimulatedTaskExecutor` (follow-up tasks), and
`SimulatedPurchaseOrderExecutor` (restocks) each return a structured
result with no real email sent and no real supplier contacted.
Connecting a real email provider, CRM, or supplier/ERP API later means
writing a class that implements `execute()` and registering it in
`EXECUTORS`; nothing about the approval workflow, the API, or the
dashboard changes. The restock executor also has a deterministic
failure mode (a supplier can't fulfill more than 500 units in one
purchase order) so the `executed` vs. `failed` distinction is
genuinely demonstrable, not just theoretical.

**Proposal generation is idempotent.** Re-running it never creates a
duplicate proposal for an alert that already has an open one --
unless the prior proposal for that alert was rejected, since the
business condition may have changed since then and is worth
re-proposing.

**No admin-user table exists in this prototype**, so `decided_by` is a
free-text name (the dashboard sends a fixed "Brandon Fung", the same
way the topbar's "BF" chip is a static demo indicator, not a real
session) rather than a foreign key.

## Dashboard

A single-page dashboard (`dashboard/`) served by the same FastAPI app:
an Action Center, an AI Business Analyst chat panel, an Agent Actions
panel (review evidence, edit safe parameters, approve/reject, see
execution results and full decision history -- filterable by status),
a Point of Sale screen (product grid, cart, discount, guest-or-existing
customer, payment method, receipt confirmation), a Transactions list
with status filtering and a receipt-detail view, KPI cards with
period-over-period deltas, a revenue/orders trend chart, top products
and high-value customer tables, low/out-of-stock inventory alerts, an
expense breakdown donut, and a website traffic/conversion trend chart.
Completing a sale on the POS screen immediately refreshes the KPIs,
Action Center, Agent Actions proposals, and product/transaction lists
-- and so does a sale completed on the customer storefront, with no
special-casing (see below). A sidebar link ("View Storefront") jumps
to `/store`.
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

- Multi-turn conversation (follow-up questions that reference earlier answers) for the LLM agent mode, instead of one question per orchestration run.
- A second `LLMProvider` implementation to prove the abstraction in `ai/llm/provider.py` genuinely holds across vendors.
- Anomaly detection, forecasting, and customer segmentation beyond fixed thresholds.
- Multi-agent workflows and real external integrations behind the existing `ActionExecutor` interface (actually sending the win-back email, filing the purchase order with a supplier/ERP API).
- Asynchronous/queued execution once approved, instead of the current synchronous approve-then-execute in one request.
- A real admin-user/session system so `AgentAction.decided_by` is a foreign key, not a fixed demo name.
- Refunds/cancellations as a second write path alongside `complete_sale()`.
- Receipt printing/emailing, and barcode-scanner input for the POS product picker.
- A real `StripePaymentProcessor` implementing the existing `PaymentProcessor` interface -- the checkout flow and `complete_sale()` wouldn't need to change.
- Production-grade storefront auth (signed/expiring tokens, a real session store) in place of the current in-memory prototype version.
- Product images, reviews, and a "you might also like" recommendation surface on the storefront.
- Order fulfillment/shipping status as a stage beyond `completed`, surfaced on both My Orders and the admin Transactions view.
