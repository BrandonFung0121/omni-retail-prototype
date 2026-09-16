const API_BASE = "";

const CATEGORY_COLORS = {
  rent: "#4f46e5",
  payroll: "#059669",
  marketing: "#d97706",
  logistics: "#db2777",
  software: "#7c3aed",
  utilities: "#0891b2",
  other: "#94a3b8",
};

const AVATAR_COLORS = ["#4f46e5", "#2563eb", "#7c3aed", "#059669", "#0891b2", "#d97706", "#db2777"];

const ICONS = {
  lowStock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10.3 3.9 2.6 17.5A1.8 1.8 0 0 0 4.2 20h15.6a1.8 1.8 0 0 0 1.6-2.5L13.7 3.9a1.8 1.8 0 0 0-3.4 0Z"/><path d="M12 9.5v4M12 16.5h.01"/></svg>`,
  outOfStock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/></svg>`,
  info: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v5h1"/></svg>`,
  lightbulb: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.45.9 1.15.9 1.9V16h5.2v-.2c0-.75.3-1.45.9-1.9A6 6 0 0 0 12 3Z"/></svg>`,
};

const SEVERITY_ICON = {
  critical: ICONS.outOfStock,
  warning: ICONS.lowStock,
  info: ICONS.info,
};

const state = {
  rangeDays: 30,
  alertFilter: "all",
  alerts: [],
  agentActionsFilter: "all",
  agentActions: [],
  charts: {},
};

function toISODate(d) {
  return d.toISOString().slice(0, 10);
}

function dateRange(days, offsetDays = 0) {
  const end = new Date();
  end.setDate(end.getDate() - offsetDays);
  const start = new Date(end);
  start.setDate(start.getDate() - (days - 1));
  return { start: toISODate(start), end: toISODate(end) };
}

async function fetchJSON(path, params = {}) {
  const url = new URL(API_BASE + path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) url.searchParams.set(key, value);
  });
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${path} failed: ${response.status}`);
  }
  return response.json();
}

function formatCurrency(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(
    value
  );
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatPercent(value) {
  return `${value.toFixed(1)}%`;
}

function escapeHTML(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function initials(name) {
  const parts = name.trim().split(/\s+/);
  const chars = parts.length > 1 ? [parts[0][0], parts[parts.length - 1][0]] : [parts[0][0]];
  return chars.join("").toUpperCase();
}

function colorForName(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function setKPI(cardId, valueText, current, previous) {
  const card = document.getElementById(cardId);
  card.querySelector(".kpi-value").textContent = valueText;
  const deltaEl = card.querySelector(".kpi-delta");

  if (!previous) {
    deltaEl.textContent = "";
    deltaEl.className = "kpi-delta";
    return;
  }
  const change = ((current - previous) / previous) * 100;
  const arrow = change >= 0 ? "▲" : "▼";
  deltaEl.textContent = `${arrow} ${Math.abs(change).toFixed(1)}%`;
  deltaEl.title = "vs. prior period of equal length";
  deltaEl.className = `kpi-delta ${change >= 0 ? "up" : "down"}`;
}

async function loadKPIs(current, previous) {
  const [kpiNow, kpiPrev] = await Promise.all([
    fetchJSON("/api/kpis/summary", current),
    fetchJSON("/api/kpis/summary", previous),
  ]);

  setKPI("kpi-revenue", formatCurrency(kpiNow.revenue), kpiNow.revenue, kpiPrev.revenue);
  setKPI("kpi-orders", formatNumber(kpiNow.orders), kpiNow.orders, kpiPrev.orders);
  setKPI("kpi-aov", formatCurrency(kpiNow.average_order_value), kpiNow.average_order_value, kpiPrev.average_order_value);
  setKPI("kpi-profit", formatCurrency(kpiNow.estimated_profit), kpiNow.estimated_profit, kpiPrev.estimated_profit);
  setKPI("kpi-visitors", formatNumber(kpiNow.website_visitors), kpiNow.website_visitors, kpiPrev.website_visitors);
  setKPI("kpi-conversion", formatPercent(kpiNow.conversion_rate), kpiNow.conversion_rate, kpiPrev.conversion_rate);
}

function baseChartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: {
        position: "bottom",
        labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, pointStyle: "circle", padding: 16, font: { family: "Inter", size: 12 } },
      },
      tooltip: {
        backgroundColor: "#14162b",
        padding: 10,
        cornerRadius: 8,
        titleFont: { family: "Inter", weight: "600" },
        bodyFont: { family: "Inter" },
        boxPadding: 4,
      },
    },
  };
}

function gridOptions() {
  return { color: "#eef0f7", drawTicks: false };
}

async function loadRevenueTrend(range) {
  const points = await fetchJSON("/api/revenue/trend", range);
  const ctx = document.getElementById("revenue-trend-chart");

  state.charts.revenue?.destroy();
  state.charts.revenue = new Chart(ctx, {
    data: {
      labels: points.map((p) => p.day),
      datasets: [
        {
          type: "bar",
          label: "Orders",
          data: points.map((p) => p.orders),
          backgroundColor: "#dbe2fe",
          hoverBackgroundColor: "#c7d2fe",
          yAxisID: "y1",
          borderRadius: 4,
          maxBarThickness: 18,
        },
        {
          type: "line",
          label: "Revenue",
          data: points.map((p) => p.revenue),
          borderColor: "#4f46e5",
          backgroundColor: "#4f46e5",
          tension: 0.35,
          yAxisID: "y",
          pointRadius: 0,
          pointHoverRadius: 4,
          borderWidth: 2.5,
        },
      ],
    },
    options: {
      ...baseChartOptions(),
      scales: {
        x: { grid: { display: false }, ticks: { font: { family: "Inter", size: 11 }, color: "#9297ac", maxRotation: 0, autoSkip: true } },
        y: {
          position: "left",
          grid: gridOptions(),
          ticks: { font: { family: "Inter", size: 11 }, color: "#9297ac", callback: (v) => `$${formatNumber(v)}` },
          title: { display: true, text: "Revenue", font: { family: "Inter", size: 11, weight: "600" }, color: "#9297ac" },
        },
        y1: {
          position: "right",
          grid: { drawOnChartArea: false },
          ticks: { font: { family: "Inter", size: 11 }, color: "#9297ac", stepSize: 1 },
          title: { display: true, text: "Orders", font: { family: "Inter", size: 11, weight: "600" }, color: "#9297ac" },
        },
      },
    },
  });
}

async function loadTopProducts(range) {
  const products = await fetchJSON("/api/products/top", { ...range, limit: 8, by: "revenue" });
  const tbody = document.querySelector("#top-products-table tbody");
  tbody.innerHTML =
    products
      .map(
        (p) => `<tr>
          <td><span class="cell-primary">${escapeHTML(p.name)}</span></td>
          <td><span class="category-pill">${escapeHTML(p.category)}</span></td>
          <td class="num">${formatNumber(p.units_sold)}</td>
          <td class="num">${formatCurrency(p.revenue)}</td>
        </tr>`
      )
      .join("") || `<tr><td colspan="4" class="empty-state">No sales in this period.</td></tr>`;
}

async function loadTopCustomers(range) {
  const customers = await fetchJSON("/api/customers/high-value", { ...range, limit: 8 });
  const tbody = document.querySelector("#top-customers-table tbody");
  tbody.innerHTML =
    customers
      .map((c) => {
        const color = colorForName(c.name);
        return `<tr>
          <td>
            <span class="cell-primary">
              <span class="avatar" style="background:${color}">${initials(c.name)}</span>
              ${escapeHTML(c.name)}
            </span>
          </td>
          <td class="num">${formatNumber(c.order_count)}</td>
          <td class="num">${formatCurrency(c.average_order_value)}</td>
          <td class="num">${formatCurrency(c.total_spent)}</td>
        </tr>`;
      })
      .join("") || `<tr><td colspan="4" class="empty-state">No customer activity in this period.</td></tr>`;
}

async function loadInventory() {
  const status = await fetchJSON("/api/inventory/status");

  const summary = document.getElementById("inventory-summary");
  summary.innerHTML = `
    <span class="stat-chip healthy"><span class="dot"></span>${status.healthy} healthy</span>
    <span class="stat-chip low_stock"><span class="dot"></span>${status.low_stock} low stock</span>
    <span class="stat-chip out_of_stock"><span class="dot"></span>${status.out_of_stock} out of stock</span>
  `;

  const list = document.getElementById("inventory-alerts");
  if (status.low_stock_items.length === 0) {
    list.innerHTML = `<li class="empty-state">All products are healthily stocked.</li>`;
    return;
  }
  list.innerHTML = status.low_stock_items
    .map((item) => {
      const cap = item.reorder_threshold * 1.5 || 1;
      const fillPct = Math.max(4, Math.min(100, (item.current_stock / cap) * 100));
      const icon = item.status === "out_of_stock" ? ICONS.outOfStock : ICONS.lowStock;
      return `
      <li class="alert-item ${item.status}">
        <div class="alert-icon">${icon}</div>
        <div class="alert-main">
          <div class="name">${escapeHTML(item.product_name)}</div>
          <div class="meta">${escapeHTML(item.category)} · ${item.current_stock} in stock / ${item.reorder_threshold} threshold</div>
          <div class="stock-bar-track"><div class="stock-bar-fill" style="width:${fillPct}%"></div></div>
        </div>
        <span class="badge ${item.status}">${item.status.replaceAll("_", " ")}</span>
      </li>`;
    })
    .join("");
}

async function loadExpenses(range) {
  const data = await fetchJSON("/api/expenses", range);
  document.getElementById("expense-total").textContent = `${formatCurrency(data.total)} total`;

  const categories = Object.entries(data.by_category).sort((a, b) => b[1] - a[1]);
  const total = categories.reduce((sum, [, amount]) => sum + amount, 0) || 1;
  const ctx = document.getElementById("expense-chart");

  state.charts.expenses?.destroy();
  state.charts.expenses = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: categories.map(([name]) => name),
      datasets: [
        {
          data: categories.map(([, amount]) => amount),
          backgroundColor: categories.map(([name]) => CATEGORY_COLORS[name] || "#cbd5e1"),
          borderWidth: 2,
          borderColor: "#ffffff",
          hoverOffset: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#14162b",
          padding: 10,
          cornerRadius: 8,
          titleFont: { family: "Inter", weight: "600" },
          bodyFont: { family: "Inter" },
        },
      },
      cutout: "68%",
    },
  });

  const legend = document.getElementById("expense-legend");
  legend.innerHTML = categories
    .map(([name, amount]) => {
      const pct = ((amount / total) * 100).toFixed(0);
      return `
      <li>
        <span class="legend-swatch" style="background:${CATEGORY_COLORS[name] || "#cbd5e1"}"></span>
        <span class="legend-name">${escapeHTML(name)}</span>
        <span class="amount">${formatCurrency(amount)}</span>
        <span class="pct">${pct}%</span>
      </li>`;
    })
    .join("");
}

async function loadTrafficTrend(range) {
  const points = await fetchJSON("/api/website/traffic/trend", range);
  const ctx = document.getElementById("traffic-trend-chart");

  state.charts.traffic?.destroy();
  state.charts.traffic = new Chart(ctx, {
    data: {
      labels: points.map((p) => p.day),
      datasets: [
        {
          type: "bar",
          label: "Visitors",
          data: points.map((p) => p.visitors),
          backgroundColor: "#cdeaf3",
          hoverBackgroundColor: "#a8dde9",
          yAxisID: "y",
          borderRadius: 4,
          maxBarThickness: 18,
        },
        {
          type: "line",
          label: "Conversion rate (%)",
          data: points.map((p) => p.conversion_rate),
          borderColor: "#db2777",
          backgroundColor: "#db2777",
          tension: 0.35,
          yAxisID: "y1",
          pointRadius: 0,
          pointHoverRadius: 4,
          borderWidth: 2.5,
        },
      ],
    },
    options: {
      ...baseChartOptions(),
      scales: {
        x: { grid: { display: false }, ticks: { font: { family: "Inter", size: 11 }, color: "#9297ac", maxRotation: 0, autoSkip: true } },
        y: {
          position: "left",
          grid: gridOptions(),
          ticks: { font: { family: "Inter", size: 11 }, color: "#9297ac" },
          title: { display: true, text: "Visitors", font: { family: "Inter", size: 11, weight: "600" }, color: "#9297ac" },
        },
        y1: {
          position: "right",
          grid: { drawOnChartArea: false },
          ticks: { font: { family: "Inter", size: 11 }, color: "#9297ac", callback: (v) => `${v}%` },
          title: { display: true, text: "Conversion", font: { family: "Inter", size: 11, weight: "600" }, color: "#9297ac" },
        },
      },
    },
  });
}

function renderAlertSummary(alerts) {
  const critical = alerts.filter((a) => a.severity === "critical").length;
  const warning = alerts.filter((a) => a.severity === "warning").length;
  const info = alerts.filter((a) => a.severity === "info").length;

  document.getElementById("alert-summary").innerHTML = `
    <span class="stat-chip critical"><span class="dot"></span>${critical} critical</span>
    <span class="stat-chip warning"><span class="dot"></span>${warning} warning</span>
    <span class="stat-chip info"><span class="dot"></span>${info} info</span>
  `;

  const badge = document.getElementById("nav-alert-badge");
  const urgent = critical + warning;
  badge.textContent = urgent > 0 ? String(urgent) : "";
}

function renderAlertList() {
  const list = document.getElementById("alert-list");
  const filtered = state.alertFilter === "all" ? state.alerts : state.alerts.filter((a) => a.severity === state.alertFilter);

  if (filtered.length === 0) {
    list.innerHTML = `<li class="empty-state">No ${state.alertFilter === "all" ? "" : state.alertFilter + " "}alerts right now — everything looks healthy.</li>`;
    return;
  }

  list.innerHTML = filtered
    .map((a) => {
      const linkedAction = state.agentActions.find((action) => action.source_alert_id === a.id);
      const actionLinkHtml = linkedAction
        ? `<button type="button" class="qa-link-btn" data-jump-action="${linkedAction.id}">View proposed action: ${escapeHTML(
            AGENT_ACTION_TYPE_LABELS[linkedAction.action_type] || linkedAction.action_type
          )} &rarr;</button>`
        : "";
      return `
      <li class="action-item ${a.severity}" data-alert-id="${escapeHTML(a.id)}">
        <div class="action-icon">${SEVERITY_ICON[a.severity] || ICONS.info}</div>
        <div class="action-main">
          <div class="action-top">
            <span class="action-title">${escapeHTML(a.title)}</span>
            <span class="severity-badge ${a.severity}">${a.severity}</span>
          </div>
          <p class="action-desc">${escapeHTML(a.description)}</p>
          <div class="action-recommend">${ICONS.lightbulb}<span>${escapeHTML(a.recommended_action)}</span></div>
          ${actionLinkHtml}
        </div>
      </li>`;
    })
    .join("");

  list.querySelectorAll("[data-jump-action]").forEach((btn) => {
    btn.addEventListener("click", () => jumpToAgentAction(Number(btn.dataset.jumpAction)));
  });
}

async function loadAlerts() {
  state.alerts = await fetchJSON("/api/alerts");
  renderAlertSummary(state.alerts);
  renderAlertList();
}

document.querySelectorAll("#alert-filter-row button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("#alert-filter-row button").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    state.alertFilter = button.dataset.severity;
    renderAlertList();
  });
});

const INTENT_LABELS = {
  revenue_explanation: "Revenue",
  product_performance: "Products",
  restock_priority: "Restock",
  top_customers: "Customers",
  churn_risk: "Churn Risk",
  expense_anomalies: "Expenses",
  traffic_conversion: "Traffic",
  business_issues_summary: "Business Issues",
  unknown: "Unclear",
};

// A small, curated subset of the assistant's supported questions --
// picked to (a) read naturally to a first-time viewer and (b) reliably
// classify under the deterministic keyword pipeline (ai/intents.py),
// so the demo works the same whether Phase 8 LLM mode is on or off.
// Clicking one always goes through the real submitQuestion() ->
// /api/assistant/ask flow below, never a canned/local answer.
const ASSISTANT_STARTER_QUESTIONS = [
  "What should I focus on right now?",
  "Which products are performing best?",
  "Are there any inventory risks?",
  "Which customers are at risk of churning?",
];

function renderAssistantStarters() {
  const container = document.getElementById("assistant-examples");
  container.innerHTML = ASSISTANT_STARTER_QUESTIONS.map(
    (q) => `<button type="button" class="assistant-chip">${escapeHTML(q)}</button>`
  ).join("");
  container.querySelectorAll(".assistant-chip").forEach((chip) => {
    chip.addEventListener("click", () => submitQuestion(chip.textContent));
  });
}

// Business-friendly labels for AgentResponse.generated_by ("template" |
// "llm" -- see ai/models.py). Never surface the raw internal values.
const GENERATED_BY_LABELS = {
  llm: { label: "AI reasoning", cls: "llm" },
  template: { label: "Quick answer", cls: "template" },
};

// Humanized labels for AgentResponse.tool_trace[].tool (see
// ai/llm/tools.py's TOOL_REGISTRY) -- shown instead of raw tool/function
// names so the "What I checked" disclosure reads as business capability,
// not implementation detail.
const TOOL_LABELS = {
  get_revenue_explanation: "Revenue trend",
  get_product_performance: "Product performance",
  get_restock_priority: "Restock priorities",
  get_top_customers: "Top customers",
  get_churn_risk: "Customer churn risk",
  get_expense_anomalies: "Expense patterns",
  get_traffic_conversion: "Website traffic & conversion",
  get_business_issues_summary: "Open business issues",
  search_customers: "Customer search",
  get_order: "Order lookup",
  get_product: "Product lookup",
  propose_action: "Proposed a follow-up action",
};

// Display metadata for known AgentResponse.supporting_metrics keys (see
// omni_retail/ai/synthesis.py). Unrecognized scalar keys still render,
// generically labeled/formatted, so a future metric doesn't just vanish.
const METRIC_LABELS = {
  current_revenue: { label: "Current Revenue", format: "currency" },
  previous_revenue: { label: "Previous Revenue", format: "currency" },
  pct_change: { label: "Change", format: "change" },
  out_of_stock_count: { label: "Out of Stock", format: "number" },
  low_stock_count: { label: "Low Stock", format: "number" },
  total_this_month: { label: "Total This Month", format: "currency" },
  current_visitors: { label: "Visitors", format: "number" },
  previous_visitors: { label: "Previous Visitors", format: "number" },
  current_conversion_rate: { label: "Conversion Rate", format: "rate" },
  previous_conversion_rate: { label: "Previous Conversion Rate", format: "rate" },
  total_alerts: { label: "Open Issues", format: "number" },
  critical: { label: "Critical", format: "number" },
  warning: { label: "Warning", format: "number" },
};

function humanizeKey(key) {
  return key
    .replace(/^get_/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatMetricValue(value, format) {
  if (format === "currency") return formatCurrency(value);
  if (format === "change") return `${value > 0 ? "+" : ""}${Number(value).toFixed(1)}%`;
  if (format === "rate") return `${Number(value).toFixed(1)}%`;
  return formatNumber(value);
}

function renderQaModeBadge(generatedBy) {
  const meta = GENERATED_BY_LABELS[generatedBy] || GENERATED_BY_LABELS.template;
  return `<span class="qa-mode-badge ${meta.cls}">${escapeHTML(meta.label)}</span>`;
}

// Only top-level scalar metrics are shown as chips -- nested lists/dicts
// (e.g. biggest_decliners, top_customers) are already reflected in the
// prose answer and aren't safe to summarize generically without risking
// a misleading chip, so they're left out rather than guessed at.
function renderQaMetrics(metrics) {
  const entries = Object.entries(metrics || {}).filter(([, v]) => typeof v === "number" || typeof v === "string");
  if (!entries.length) return "";
  const chips = entries
    .map(([key, value]) => {
      const meta = METRIC_LABELS[key];
      const label = meta ? meta.label : humanizeKey(key);
      const display = typeof value === "number" ? formatMetricValue(value, meta ? meta.format : "number") : escapeHTML(String(value));
      return `<span class="qa-metric-chip"><span class="qa-metric-label">${escapeHTML(label)}</span><span class="qa-metric-value">${display}</span></span>`;
    })
    .join("");
  return `<div class="qa-metrics">${chips}</div>`;
}

// Collapsed by default -- shows which business capabilities were used to
// ground this answer, without exposing raw tool names/arguments/JSON.
function renderQaToolTrace(trace) {
  if (!trace || !trace.length) return "";
  const items = trace
    .map((t) => {
      const label = TOOL_LABELS[t.tool] || humanizeKey(t.tool);
      return `<li class="qa-trace-item ${t.ok ? "ok" : "error"}"><span class="qa-trace-dot"></span>${escapeHTML(label)}</li>`;
    })
    .join("");
  return `<details class="qa-tool-trace agent-action-evidence"><summary>What I checked</summary><ul class="qa-trace-list">${items}</ul></details>`;
}

// ---------- cross-navigation between Assistant / Alerts / Agent Actions ----------
// Only ever wired up when the target is currently resolvable in already-
// loaded live data -- never fabricates a link for an id that doesn't
// (or no longer) resolves to a real row.
function jumpToListItem(containerId, matchFn) {
  const container = document.getElementById(containerId);
  if (!container) return false;
  const item = Array.from(container.children).find(matchFn);
  if (!item) return false;
  item.scrollIntoView({ behavior: "smooth", block: "center" });
  item.classList.add("jump-highlight");
  setTimeout(() => item.classList.remove("jump-highlight"), 1600);
  return true;
}

function jumpToAlert(alertId) {
  if (state.alertFilter !== "all") {
    state.alertFilter = "all";
    document.querySelectorAll("#alert-filter-row button").forEach((b) => b.classList.toggle("active", b.dataset.severity === "all"));
    renderAlertList();
  }
  jumpToListItem("alert-list", (el) => el.dataset.alertId === String(alertId));
}

function jumpToAgentAction(actionId) {
  if (state.agentActionsFilter !== "all") {
    state.agentActionsFilter = "all";
    document.querySelectorAll("#agent-actions-filter-row button").forEach((b) => b.classList.toggle("active", b.dataset.status === "all"));
    renderAgentActionsList();
  }
  jumpToListItem("agent-actions-list", (el) => el.dataset.actionId === String(actionId));
}

function renderQaLoadingCard(question) {
  const thread = document.getElementById("assistant-thread");
  const emptyState = thread.querySelector(".empty-state");
  if (emptyState) emptyState.remove();

  const card = document.createElement("div");
  card.className = "qa-card";
  card.innerHTML = `
    <div class="qa-question">${escapeHTML(question)}</div>
    <div class="qa-loading"><span class="dot"></span><span class="dot"></span><span class="dot"></span> Analyzing your data...</div>
  `;
  thread.prepend(card);
  return card;
}

function renderQaResult(card, data) {
  const intentLabel = INTENT_LABELS[data.intent] || data.intent;
  const pillClass = data.confidence === "low" ? "intent-pill low" : "intent-pill";

  const actionsHtml = data.recommended_actions.length
    ? `<ul class="qa-actions">${data.recommended_actions
        .map((a) => `<li>${ICONS.lightbulb}<span>${escapeHTML(a)}</span></li>`)
        .join("")}</ul>`
    : "";

  const relatedAlerts = (data.related_alert_ids || [])
    .map((id) => state.alerts.find((a) => a.id === id))
    .filter(Boolean);
  const alertRefHtml = relatedAlerts.length
    ? `<div class="qa-alert-ref">Related in the Action Center: ${relatedAlerts
        .map((a) => `<button type="button" class="qa-link-btn" data-jump-alert="${escapeHTML(a.id)}">${escapeHTML(a.title)}</button>`)
        .join(" ")}</div>`
    : "";

  card.innerHTML = `
    <div class="qa-question-row">
      <div class="qa-question"><span class="${pillClass}">${escapeHTML(intentLabel)}</span>${escapeHTML(data.question)}</div>
      ${renderQaModeBadge(data.generated_by)}
    </div>
    <p class="qa-answer">${escapeHTML(data.answer)}</p>
    ${renderQaMetrics(data.supporting_metrics)}
    ${actionsHtml}
    ${renderQaToolTrace(data.tool_trace)}
    ${alertRefHtml}
  `;

  card.querySelectorAll("[data-jump-alert]").forEach((btn) => {
    btn.addEventListener("click", () => jumpToAlert(btn.dataset.jumpAlert));
  });
}

function renderQaError(card, question) {
  card.innerHTML = `
    <div class="qa-question">${escapeHTML(question)}</div>
    <p class="qa-answer">Something went wrong reaching the assistant. Please try again.</p>
  `;
}

async function submitQuestion(question) {
  question = (question || "").trim();
  if (!question) return;

  const button = document.querySelector("#assistant-form button");
  button.disabled = true;
  const card = renderQaLoadingCard(question);

  try {
    const response = await fetch("/api/assistant/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!response.ok) throw new Error(`ask failed: ${response.status}`);
    const data = await response.json();
    renderQaResult(card, data);
  } catch (err) {
    console.error(err);
    renderQaError(card, question);
  } finally {
    button.disabled = false;
  }
}

document.getElementById("assistant-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.getElementById("assistant-input");
  const question = input.value;
  input.value = "";
  submitQuestion(question);
});

/* ---------- Agent Actions (Phase 7) ---------- */

const AGENT_ACTION_TYPE_LABELS = {
  win_back_offer: "Win-Back Offer",
  restock_request: "Restock Request",
  followup_task: "Follow-Up Task",
};

const AGENT_ACTION_ICONS = {
  win_back_offer: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16v12H4z"/><path d="m4 7 8 6 8-6"/></svg>`,
  restock_request: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="4.5" rx="1.2"/><path d="M4.5 8.5V19a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5V8.5"/><path d="M10 13h4"/></svg>`,
  followup_task: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 12.5 11 14.5 15.5 9.5"/><circle cx="12" cy="12" r="9"/></svg>`,
};

const AGENT_PARAM_LABELS = {
  offer_percent: "Offer (%)",
  message: "Message",
  customer_email: "Customer email",
  restock_quantity: "Restock quantity",
  product_name: "Product",
  task: "Task",
  priority: "Priority",
};

// This is a single-admin prototype with no login system on the dashboard
// side (the "BF" chip in the topbar is decorative) -- every approval/
// rejection is attributed to this fixed name rather than a real session.
const AGENT_ACTIONS_DECIDER = "Brandon Fung";

function renderAgentActionsSummary(actions) {
  const counts = { proposed: 0, approved: 0, executed: 0, failed: 0, rejected: 0 };
  actions.forEach((a) => {
    counts[a.status] = (counts[a.status] || 0) + 1;
  });

  document.getElementById("agent-actions-summary").innerHTML = `
    <span class="stat-chip proposed"><span class="dot"></span>${counts.proposed} proposed</span>
    <span class="stat-chip executed"><span class="dot"></span>${counts.executed} executed</span>
    <span class="stat-chip failed"><span class="dot"></span>${counts.failed} failed</span>
    <span class="stat-chip rejected"><span class="dot"></span>${counts.rejected} rejected</span>
  `;

  const badge = document.getElementById("nav-actions-badge");
  badge.textContent = counts.proposed > 0 ? String(counts.proposed) : "";
}

function renderAgentActionParamField(key, value) {
  const label = AGENT_PARAM_LABELS[key] || key;
  if (key === "message" || (typeof value === "string" && value.length > 60)) {
    return `
      <label class="agent-param-label">${escapeHTML(label)}</label>
      <textarea class="agent-action-param-textarea" data-param="${key}" data-param-type="string" rows="3">${escapeHTML(
      String(value)
    )}</textarea>`;
  }
  if (typeof value === "number") {
    return `
      <label class="agent-param-label">${escapeHTML(label)}</label>
      <input type="number" class="agent-action-param-input" data-param="${key}" data-param-type="number" value="${value}" />`;
  }
  return `
    <label class="agent-param-label">${escapeHTML(label)}</label>
    <input type="text" class="agent-action-param-input" data-param="${key}" data-param-type="string" value="${escapeHTML(
    String(value)
  )}" />`;
}

function renderAgentActionEvidence(evidence) {
  const rows = Object.entries(evidence || {})
    .map(
      ([key, value]) =>
        `<div class="agent-evidence-row"><span>${escapeHTML(key.replace(/_/g, " "))}</span><span>${escapeHTML(
          String(value)
        )}</span></div>`
    )
    .join("");
  return `<details class="agent-action-evidence"><summary>Supporting evidence</summary><div class="agent-evidence-grid">${rows}</div></details>`;
}

function sourceAlertLinkHtml(action) {
  if (!action.source_alert_id) return "";
  const alert = state.alerts.find((a) => a.id === action.source_alert_id);
  if (!alert) return "";
  return `<button type="button" class="qa-link-btn" data-jump-alert="${escapeHTML(action.source_alert_id)}">Source alert: ${escapeHTML(
    alert.title
  )} &rarr;</button>`;
}

function renderAgentActionAuditTrail(action) {
  const steps = [{ label: "Proposed", at: action.created_at, detail: "" }];
  if (action.decided_at) {
    const verb = action.status === "rejected" ? "Rejected" : "Approved";
    const who = action.decided_by ? `By ${action.decided_by}.` : "";
    const reason = action.status === "rejected" && action.rejection_reason ? ` ${action.rejection_reason}` : "";
    steps.push({ label: verb, at: action.decided_at, detail: `${who}${reason}`.trim() });
  }
  if (action.executed_at) {
    const ok = action.status === "executed";
    const detail = action.execution_result ? (ok ? action.execution_result.detail : action.execution_result.failure_reason) : "";
    steps.push({ label: ok ? "Executed" : "Execution failed", at: action.executed_at, detail: detail || "" });
  }
  const rows = steps
    .map(
      (s) => `
      <li>
        <span class="audit-step-label">${escapeHTML(s.label)}</span>
        <span class="audit-step-time">${new Date(s.at).toLocaleString()}</span>
        ${s.detail ? `<span class="audit-step-detail">${escapeHTML(s.detail)}</span>` : ""}
      </li>`
    )
    .join("");
  return `<details class="agent-action-evidence"><summary>Audit trail</summary><ul class="audit-trail-list">${rows}</ul></details>`;
}

function renderAgentActionDecisionInfo(action) {
  const parts = [];
  if (action.decided_by) {
    parts.push(
      `<div>Decided by <strong>${escapeHTML(action.decided_by)}</strong> on ${new Date(
        action.decided_at
      ).toLocaleString()}</div>`
    );
  }
  if (action.status === "rejected" && action.rejection_reason) {
    parts.push(`<div>Reason: ${escapeHTML(action.rejection_reason)}</div>`);
  }
  if (action.execution_result && action.status === "executed") {
    parts.push(
      `<div class="agent-action-result success">${ICONS.lightbulb}<span>${escapeHTML(
        action.execution_result.detail
      )} <em>(ref ${escapeHTML(action.execution_result.reference)})</em></span></div>`
    );
  }
  if (action.execution_result && action.status === "failed") {
    parts.push(
      `<div class="agent-action-result failure">${escapeHTML(
        action.execution_result.failure_reason || "Execution failed."
      )}</div>`
    );
  }
  return parts.length ? `<div class="agent-action-decision">${parts.join("")}</div>` : "";
}

function renderAgentActionItem(action) {
  const typeLabel = AGENT_ACTION_TYPE_LABELS[action.action_type] || action.action_type;
  const icon = AGENT_ACTION_ICONS[action.action_type] || ICONS.info;

  const bodyHtml =
    action.status === "proposed"
      ? `
        <div class="agent-action-params">
          ${Object.entries(action.proposed_parameters)
            .map(([key, value]) => renderAgentActionParamField(key, value))
            .join("")}
        </div>
        <div class="agent-action-buttons">
          <button type="button" class="agent-action-approve-btn" data-action-id="${action.id}">Approve</button>
          <button type="button" class="agent-action-reject-btn" data-action-id="${action.id}">Reject</button>
        </div>
      `
      : renderAgentActionDecisionInfo(action);

  return `
    <li class="action-item agent-action-item ${action.status}" data-action-id="${action.id}">
      <div class="action-icon">${icon}</div>
      <div class="action-main">
        <div class="action-top">
          <span class="action-title">${escapeHTML(typeLabel)}</span>
          <span class="agent-risk-badge ${action.risk_level}">${action.risk_level} risk</span>
          <span class="agent-status-badge ${action.status}">${action.status}</span>
        </div>
        <p class="action-desc">${escapeHTML(action.business_reason)}</p>
        <div class="action-recommend">${ICONS.lightbulb}<span>${escapeHTML(action.expected_outcome)}</span></div>
        ${sourceAlertLinkHtml(action)}
        ${renderAgentActionEvidence(action.supporting_evidence)}
        ${renderAgentActionAuditTrail(action)}
        ${bodyHtml}
      </div>
    </li>`;
}

function renderAgentActionsList() {
  const list = document.getElementById("agent-actions-list");
  const filtered =
    state.agentActionsFilter === "all"
      ? state.agentActions
      : state.agentActions.filter((a) => a.status === state.agentActionsFilter);

  if (filtered.length === 0) {
    list.innerHTML =
      state.agentActionsFilter === "all"
        ? `<li class="empty-state">No proposed actions right now. The AI proposes actions here when it finds something in the Action Center worth acting on.</li>`
        : `<li class="empty-state">No ${state.agentActionsFilter} actions right now.</li>`;
    return;
  }

  list.innerHTML = filtered.map(renderAgentActionItem).join("");

  list.querySelectorAll(".agent-action-approve-btn").forEach((button) => {
    button.addEventListener("click", () => approveAgentAction(Number(button.dataset.actionId)));
  });
  list.querySelectorAll(".agent-action-reject-btn").forEach((button) => {
    button.addEventListener("click", () => rejectAgentAction(Number(button.dataset.actionId)));
  });
  list.querySelectorAll("[data-jump-alert]").forEach((btn) => {
    btn.addEventListener("click", () => jumpToAlert(btn.dataset.jumpAlert));
  });
}

function collectEditedParameters(actionId) {
  const item = document.querySelector(`.agent-action-item[data-action-id="${actionId}"]`);
  const edited = {};
  item.querySelectorAll("[data-param]").forEach((el) => {
    edited[el.dataset.param] = el.dataset.paramType === "number" ? Number(el.value) : el.value;
  });
  return edited;
}

async function approveAgentAction(actionId) {
  const buttons = document.querySelectorAll(
    `.agent-action-item[data-action-id="${actionId}"] button`
  );
  buttons.forEach((b) => (b.disabled = true));
  try {
    const response = await fetch(`/api/actions/${actionId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decided_by: AGENT_ACTIONS_DECIDER, edited_parameters: collectEditedParameters(actionId) }),
    });
    if (!response.ok) throw new Error(`approve failed: ${response.status}`);
    await loadAgentActions();
    await loadAlerts();
  } catch (err) {
    console.error(err);
    buttons.forEach((b) => (b.disabled = false));
  }
}

async function rejectAgentAction(actionId) {
  const buttons = document.querySelectorAll(
    `.agent-action-item[data-action-id="${actionId}"] button`
  );
  buttons.forEach((b) => (b.disabled = true));
  try {
    const response = await fetch(`/api/actions/${actionId}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decided_by: AGENT_ACTIONS_DECIDER }),
    });
    if (!response.ok) throw new Error(`reject failed: ${response.status}`);
    await loadAgentActions();
  } catch (err) {
    console.error(err);
    buttons.forEach((b) => (b.disabled = false));
  }
}

async function loadAgentActions() {
  state.agentActions = await fetchJSON("/api/actions");
  renderAgentActionsSummary(state.agentActions);
  renderAgentActionsList();
  renderAlertList(); // refresh alert -> action cross-links now that actions are current
}

async function generateAgentActions() {
  try {
    await fetch("/api/actions/generate", { method: "POST" });
  } catch (err) {
    console.error(err);
  }
  await loadAgentActions();
}

document.querySelectorAll("#agent-actions-filter-row button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("#agent-actions-filter-row button").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    state.agentActionsFilter = button.dataset.status;
    renderAgentActionsList();
  });
});

document.getElementById("agent-actions-refresh-btn").addEventListener("click", () => {
  generateAgentActions().catch((err) => console.error(err));
});

const POS_ICONS = {
  remove: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>`,
  check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 13l4 4L19 7"/></svg>`,
};

const pos = {
  products: [],
  cart: [], // { product_id, name, selling_price, quantity, current_stock }
  customer: null, // { customer_id, name, email } | null (guest)
};

const tx = { status: "", limit: 20, offset: 0, lastCount: 0 };

function posSubtotal() {
  return pos.cart.reduce((sum, item) => sum + item.selling_price * item.quantity, 0);
}

function posDiscountPreview(subtotal) {
  const type = document.getElementById("pos-discount-type").value;
  const raw = parseFloat(document.getElementById("pos-discount-value").value);
  const value = Number.isFinite(raw) ? raw : 0;
  if (!type || value <= 0) return 0;
  if (type === "percent") return subtotal * Math.min(Math.max(value, 0), 100) / 100;
  return Math.min(Math.max(value, 0), subtotal);
}

async function loadPosProducts() {
  pos.products = await fetchJSON("/api/products");
  renderPosProductGrid();
}

function renderPosProductGrid() {
  const query = document.getElementById("pos-product-search").value.trim().toLowerCase();
  const grid = document.getElementById("pos-product-grid");
  const filtered = query
    ? pos.products.filter((p) => p.name.toLowerCase().includes(query) || p.category.toLowerCase().includes(query))
    : pos.products;

  grid.innerHTML =
    filtered
      .map((p) => {
        const outOfStock = p.current_stock <= 0;
        const stockLabel = outOfStock ? "Out of stock" : `${p.current_stock} in stock`;
        return `
        <button type="button" class="pos-product-card" data-product-id="${p.product_id}" ${outOfStock ? "disabled" : ""}>
          <span class="pos-product-name">${escapeHTML(p.name)}</span>
          <span class="pos-product-meta">
            <span class="pos-product-price">${formatCurrency(p.selling_price)}</span>
            <span class="pos-product-stock ${p.status}">${stockLabel}</span>
          </span>
        </button>`;
      })
      .join("") || `<p class="empty-state">No products match "${escapeHTML(query)}".</p>`;

  grid.querySelectorAll(".pos-product-card").forEach((card) => {
    card.addEventListener("click", () => addToCart(Number(card.dataset.productId)));
  });
}

function addToCart(productId) {
  const product = pos.products.find((p) => p.product_id === productId);
  if (!product) return;

  const existing = pos.cart.find((item) => item.product_id === productId);
  if (existing) {
    if (existing.quantity < product.current_stock) existing.quantity += 1;
  } else if (product.current_stock > 0) {
    pos.cart.push({
      product_id: product.product_id,
      name: product.name,
      selling_price: product.selling_price,
      quantity: 1,
      current_stock: product.current_stock,
    });
  }
  renderCart();
}

function changeCartQuantity(productId, delta) {
  const item = pos.cart.find((i) => i.product_id === productId);
  if (!item) return;
  item.quantity = Math.min(item.current_stock, Math.max(0, item.quantity + delta));
  pos.cart = pos.cart.filter((i) => i.quantity > 0);
  renderCart();
}

function removeFromCart(productId) {
  pos.cart = pos.cart.filter((i) => i.product_id !== productId);
  renderCart();
}

function renderCart() {
  const list = document.getElementById("pos-cart-list");
  list.innerHTML =
    pos.cart
      .map(
        (item) => `
      <li class="pos-cart-item">
        <div class="pos-cart-item-info">
          <div class="pos-cart-item-name">${escapeHTML(item.name)}</div>
          <div class="pos-cart-item-price">${formatCurrency(item.selling_price)} each</div>
        </div>
        <div class="pos-qty-control">
          <button type="button" data-action="dec" data-product-id="${item.product_id}">&minus;</button>
          <span class="pos-qty-value">${item.quantity}</span>
          <button type="button" data-action="inc" data-product-id="${item.product_id}">+</button>
        </div>
        <button type="button" class="pos-cart-remove" data-action="remove" data-product-id="${item.product_id}">${POS_ICONS.remove}</button>
      </li>`
      )
      .join("") || `<li class="empty-state">Cart is empty. Click a product to add it.</li>`;

  list.querySelectorAll("button[data-action]").forEach((btn) => {
    const productId = Number(btn.dataset.productId);
    btn.addEventListener("click", () => {
      if (btn.dataset.action === "inc") changeCartQuantity(productId, 1);
      else if (btn.dataset.action === "dec") changeCartQuantity(productId, -1);
      else removeFromCart(productId);
    });
  });

  updatePosSummary();
}

function updatePosSummary() {
  const subtotal = posSubtotal();
  const discount = posDiscountPreview(subtotal);
  document.getElementById("pos-subtotal").textContent = formatCurrency(subtotal);
  document.getElementById("pos-discount-display").textContent = `-${formatCurrency(discount)}`;
  document.getElementById("pos-total").textContent = formatCurrency(Math.max(0, subtotal - discount));
}

document.getElementById("pos-product-search").addEventListener("input", renderPosProductGrid);
document.getElementById("pos-discount-type").addEventListener("change", (e) => {
  document.getElementById("pos-discount-value").disabled = !e.target.value;
  if (!e.target.value) document.getElementById("pos-discount-value").value = "";
  updatePosSummary();
});
document.getElementById("pos-discount-value").addEventListener("input", updatePosSummary);

function setSelectedCustomer(customer) {
  pos.customer = customer;
  const guestBtn = document.getElementById("pos-guest-toggle");
  const chip = document.getElementById("pos-selected-customer");
  const searchInput = document.getElementById("pos-customer-search");

  if (customer) {
    guestBtn.classList.remove("active");
    chip.innerHTML = `${escapeHTML(customer.name)} <button type="button" id="pos-clear-customer">&times;</button>`;
    chip.querySelector("#pos-clear-customer").addEventListener("click", () => {
      searchInput.value = "";
      setSelectedCustomer(null);
    });
    document.getElementById("pos-customer-results").innerHTML = "";
  } else {
    guestBtn.classList.add("active");
    chip.innerHTML = "";
  }
}

let customerSearchTimer = null;
document.getElementById("pos-customer-search").addEventListener("input", (e) => {
  clearTimeout(customerSearchTimer);
  const q = e.target.value.trim();
  const results = document.getElementById("pos-customer-results");
  if (!q) {
    results.innerHTML = "";
    return;
  }
  customerSearchTimer = setTimeout(async () => {
    const customers = await fetchJSON("/api/customers/search", { q, limit: 8 });
    results.innerHTML = customers
      .map((c) => `<button type="button" class="pos-customer-result" data-id="${c.customer_id}">${escapeHTML(c.name)} &middot; ${escapeHTML(c.email)}</button>`)
      .join("");
    results.querySelectorAll(".pos-customer-result").forEach((btn) => {
      const customer = customers.find((c) => String(c.customer_id) === btn.dataset.id);
      btn.addEventListener("click", () => setSelectedCustomer(customer));
    });
  }, 250);
});

document.getElementById("pos-guest-toggle").addEventListener("click", () => {
  document.getElementById("pos-customer-search").value = "";
  document.getElementById("pos-customer-results").innerHTML = "";
  setSelectedCustomer(null);
});

function resetPosForm() {
  pos.cart = [];
  pos.customer = null;
  document.getElementById("pos-discount-type").value = "";
  document.getElementById("pos-discount-value").value = "";
  document.getElementById("pos-discount-value").disabled = true;
  document.getElementById("pos-payment-method").value = "cash";
  document.getElementById("pos-customer-search").value = "";
  document.getElementById("pos-customer-results").innerHTML = "";
  document.getElementById("pos-error").textContent = "";
  setSelectedCustomer(null);
  renderCart();
}

function showReceipt(receipt) {
  const card = document.getElementById("pos-receipt-card");
  const linesHtml = receipt.lines
    .map(
      (l) => `<div class="pos-receipt-line"><span class="name">${escapeHTML(l.product_name)} &times;${l.quantity}</span><span class="amount">${formatCurrency(l.line_total)}</span></div>`
    )
    .join("");

  card.innerHTML = `
    <div class="pos-receipt-header">
      <div class="pos-receipt-check">${POS_ICONS.check}</div>
      <h3>Sale complete</h3>
      <p>Order #${receipt.order_id}</p>
    </div>
    <div class="pos-receipt-lines">${linesHtml}</div>
    <div class="pos-receipt-totals">
      <div class="pos-summary-row"><span>Subtotal</span><span>${formatCurrency(receipt.subtotal)}</span></div>
      <div class="pos-summary-row"><span>Discount</span><span>-${formatCurrency(receipt.discount_total)}</span></div>
      <div class="pos-summary-row pos-summary-total"><span>Total</span><span>${formatCurrency(receipt.total)}</span></div>
    </div>
    <div class="pos-receipt-meta">
      <span>Customer: ${escapeHTML(receipt.customer_name)}</span>
      <span>Payment: ${escapeHTML(receipt.payment_method.replaceAll("_", " "))} &middot; ${escapeHTML(receipt.payment_status)}</span>
    </div>
    <div class="pos-receipt-actions">
      <button type="button" class="secondary" id="receipt-close-btn">Close</button>
      <button type="button" class="primary" id="receipt-new-sale-btn">New Sale</button>
    </div>
  `;
  document.getElementById("pos-receipt-overlay").classList.add("open");
  document.getElementById("receipt-close-btn").addEventListener("click", closeReceiptOverlay);
  document.getElementById("receipt-new-sale-btn").addEventListener("click", closeReceiptOverlay);
}

function closeReceiptOverlay() {
  document.getElementById("pos-receipt-overlay").classList.remove("open");
}

document.getElementById("pos-checkout-btn").addEventListener("click", async () => {
  const errorEl = document.getElementById("pos-error");
  errorEl.textContent = "";

  if (pos.cart.length === 0) {
    errorEl.textContent = "Cart is empty -- add at least one item.";
    return;
  }

  const discountType = document.getElementById("pos-discount-type").value;
  const button = document.getElementById("pos-checkout-btn");
  button.disabled = true;

  const payload = {
    items: pos.cart.map((item) => ({ product_id: item.product_id, quantity: item.quantity })),
    payment_method: document.getElementById("pos-payment-method").value,
    customer_id: pos.customer ? pos.customer.customer_id : null,
    channel: "in_store",
    discount_type: discountType || null,
    discount_value: discountType ? parseFloat(document.getElementById("pos-discount-value").value) || 0 : 0,
  };

  try {
    const response = await fetch("/api/pos/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      errorEl.textContent = data.detail || "Checkout failed. Please try again.";
      return;
    }

    showReceipt(data);
    resetPosForm();
    await Promise.all([loadPosProducts(), loadTransactions(), loadDashboard(), loadAlerts(), generateAgentActions()]);
  } catch (err) {
    console.error(err);
    errorEl.textContent = "Couldn't reach the server. Please try again.";
  } finally {
    button.disabled = false;
  }
});

document.querySelectorAll("#transactions-status-filter button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("#transactions-status-filter button").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    tx.status = button.dataset.status;
    tx.offset = 0;
    loadTransactions().catch((err) => console.error(err));
  });
});

let txRequestSeq = 0;

async function loadTransactions() {
  // Guard against out-of-order responses: if the page's initial unfiltered
  // load is still in flight when the user clicks a filter, that older
  // request can resolve *after* the new filtered one and overwrite it with
  // the wrong (unfiltered) rows. Only the most recently issued request is
  // allowed to render.
  const seq = ++txRequestSeq;
  const params = { limit: tx.limit, offset: tx.offset };
  if (tx.status) params.status = tx.status;
  const orders = await fetchJSON("/api/orders", params);
  if (seq !== txRequestSeq) return;

  tx.lastCount = orders.length;
  renderTransactionsTable(orders);
  updateTransactionsPagination();
}

function renderTransactionsTable(orders) {
  const tbody = document.querySelector("#transactions-table tbody");
  tbody.innerHTML =
    orders
      .map(
        (o) => `
      <tr class="clickable-row" data-order-id="${o.order_id}">
        <td class="num">#${o.order_id}</td>
        <td>${escapeHTML(o.order_datetime.replace("T", " ").slice(0, 16))}</td>
        <td>${escapeHTML(o.customer_name)}</td>
        <td><span class="category-pill">${escapeHTML(o.channel.replaceAll("_", " "))}</span></td>
        <td class="num">${formatNumber(o.item_count)}</td>
        <td class="num">${formatCurrency(o.total)}</td>
        <td>${escapeHTML((o.payment_method || "-").replaceAll("_", " "))}</td>
        <td><span class="badge status-${o.status}">${escapeHTML(o.status)}</span></td>
      </tr>`
      )
      .join("") || `<tr><td colspan="8" class="empty-state">No transactions in this view.</td></tr>`;

  tbody.querySelectorAll("tr.clickable-row").forEach((row) => {
    row.addEventListener("click", () => showOrderDetail(Number(row.dataset.orderId)));
  });
}

function updateTransactionsPagination() {
  document.getElementById("transactions-prev").disabled = tx.offset === 0;
  document.getElementById("transactions-next").disabled = tx.lastCount < tx.limit;
  const page = Math.floor(tx.offset / tx.limit) + 1;
  document.getElementById("transactions-page-label").textContent = `Page ${page}`;
}

document.getElementById("transactions-prev").addEventListener("click", () => {
  tx.offset = Math.max(0, tx.offset - tx.limit);
  loadTransactions().catch((err) => console.error(err));
});
document.getElementById("transactions-next").addEventListener("click", () => {
  tx.offset += tx.limit;
  loadTransactions().catch((err) => console.error(err));
});

async function showOrderDetail(orderId) {
  const card = document.getElementById("order-detail-card");
  card.innerHTML = `<div class="qa-loading"><span class="dot"></span><span class="dot"></span><span class="dot"></span> Loading order...</div>`;
  document.getElementById("order-detail-overlay").classList.add("open");

  try {
    const order = await fetchJSON(`/api/orders/${orderId}`);
    const linesHtml = order.lines
      .map(
        (l) => `<div class="pos-receipt-line"><span class="name">${escapeHTML(l.product_name)} &times;${l.quantity}</span><span class="amount">${formatCurrency(l.line_total)}</span></div>`
      )
      .join("");
    card.innerHTML = `
      <div class="pos-receipt-header">
        <h3>Order #${order.order_id}</h3>
        <p>${escapeHTML(order.order_datetime.replace("T", " ").slice(0, 16))} &middot; ${escapeHTML(order.customer_name)}</p>
      </div>
      <div class="pos-receipt-lines">${linesHtml}</div>
      <div class="pos-receipt-totals">
        <div class="pos-summary-row"><span>Subtotal</span><span>${formatCurrency(order.subtotal)}</span></div>
        <div class="pos-summary-row"><span>Discount</span><span>-${formatCurrency(order.discount_total)}</span></div>
        <div class="pos-summary-row pos-summary-total"><span>Total</span><span>${formatCurrency(order.total)}</span></div>
      </div>
      <div class="pos-receipt-meta">
        <span>Status: ${escapeHTML(order.status)}</span>
        <span>Channel: ${escapeHTML(order.channel.replaceAll("_", " "))}</span>
        <span>Payment: ${escapeHTML((order.payment_method || "-").replaceAll("_", " "))} &middot; ${escapeHTML(order.payment_status || "-")}</span>
      </div>
      <div class="pos-receipt-actions">
        <button type="button" class="primary" id="order-detail-close-btn">Close</button>
      </div>
    `;
    document.getElementById("order-detail-close-btn").addEventListener("click", closeOrderDetailOverlay);
  } catch (err) {
    console.error(err);
    card.innerHTML = `<p class="empty-state">Couldn't load that order.</p>`;
  }
}

function closeOrderDetailOverlay() {
  document.getElementById("order-detail-overlay").classList.remove("open");
}

[document.getElementById("pos-receipt-overlay"), document.getElementById("order-detail-overlay")].forEach((overlay) => {
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.classList.remove("open");
  });
});

async function loadDashboard() {
  const current = dateRange(state.rangeDays, 0);
  const previous = dateRange(state.rangeDays, state.rangeDays);

  document.getElementById("range-label").textContent = `${current.start} to ${current.end}`;

  await Promise.all([
    loadKPIs(current, previous),
    loadRevenueTrend(current),
    loadTopProducts(current),
    loadTopCustomers(current),
    loadInventory(),
    loadExpenses(current),
    loadTrafficTrend(current),
  ]);
}

document.querySelectorAll(".range-picker button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".range-picker button").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    state.rangeDays = Number(button.dataset.days);
    loadDashboard().catch((err) => console.error(err));
  });
});

// Mobile sidebar toggle
const sidebar = document.getElementById("sidebar");
const scrim = document.getElementById("sidebar-scrim");
const navToggle = document.getElementById("mobile-nav-toggle");

function closeSidebar() {
  sidebar.classList.remove("open");
  scrim.classList.remove("open");
  navToggle.setAttribute("aria-expanded", "false");
}

navToggle.addEventListener("click", () => {
  const isOpen = sidebar.classList.toggle("open");
  scrim.classList.toggle("open", isOpen);
  navToggle.setAttribute("aria-expanded", String(isOpen));
});
scrim.addEventListener("click", closeSidebar);
document.querySelectorAll(".nav-link").forEach((link) => link.addEventListener("click", closeSidebar));

// Scroll-spy: highlight the nav link for the section currently in view
const navLinks = document.querySelectorAll(".nav-link");
const sections = Array.from(navLinks)
  .map((link) => document.getElementById(link.dataset.nav))
  .filter(Boolean);

const spyObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      navLinks.forEach((link) => link.classList.toggle("active", link.dataset.nav === entry.target.id));
    });
  },
  { rootMargin: "-40% 0px -55% 0px" }
);
sections.forEach((section) => spyObserver.observe(section));

// Initial data load, coordinated so a failure anywhere surfaces a visible,
// dismissable-by-retry banner instead of leaving sections silently blank
// (previously each load only logged to the console on failure).
async function loadAll() {
  document.getElementById("load-error-banner").hidden = true;
  try {
    await Promise.all([loadDashboard(), loadAlerts(), generateAgentActions(), loadPosProducts(), loadTransactions()]);
  } catch (err) {
    console.error(err);
    document.getElementById("load-error-banner").hidden = false;
  }
}

document.getElementById("load-error-retry").addEventListener("click", () => {
  loadAll();
});

renderAssistantStarters();
loadAll();
