const API_BASE = "";

const CATEGORY_COLORS = {
  rent: "#4f6df5",
  payroll: "#22c55e",
  marketing: "#f59e0b",
  logistics: "#ec4899",
  software: "#8b5cf6",
  utilities: "#06b6d4",
  other: "#94a3b8",
};

const state = {
  rangeDays: 30,
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

function setKPI(cardId, valueText, current, previous) {
  const card = document.getElementById(cardId);
  card.querySelector(".kpi-value").textContent = valueText;
  const deltaEl = card.querySelector(".kpi-delta");

  if (previous === 0 || previous === undefined || previous === null) {
    deltaEl.textContent = "";
    deltaEl.className = "kpi-delta";
    return;
  }
  const change = ((current - previous) / previous) * 100;
  const arrow = change >= 0 ? "▲" : "▼";
  deltaEl.textContent = `${arrow} ${Math.abs(change).toFixed(1)}% vs prior period`;
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
          backgroundColor: "#c7d2fe",
          yAxisID: "y1",
          borderRadius: 4,
        },
        {
          type: "line",
          label: "Revenue",
          data: points.map((p) => p.revenue),
          borderColor: "#4f6df5",
          backgroundColor: "#4f6df5",
          tension: 0.3,
          yAxisID: "y",
          pointRadius: 0,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: { position: "left", title: { display: true, text: "Revenue ($)" } },
        y1: { position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Orders" } },
      },
      plugins: { legend: { position: "bottom" } },
    },
  });
}

async function loadTopProducts(range) {
  const products = await fetchJSON("/api/products/top", { ...range, limit: 8, by: "revenue" });
  const tbody = document.querySelector("#top-products-table tbody");
  tbody.innerHTML = products
    .map(
      (p) => `<tr><td>${p.name}</td><td>${p.category}</td><td>${formatNumber(p.units_sold)}</td><td>${formatCurrency(p.revenue)}</td></tr>`
    )
    .join("") || `<tr><td colspan="4" class="empty-state">No sales in this period.</td></tr>`;
}

async function loadTopCustomers(range) {
  const customers = await fetchJSON("/api/customers/high-value", { ...range, limit: 8 });
  const tbody = document.querySelector("#top-customers-table tbody");
  tbody.innerHTML = customers
    .map(
      (c) =>
        `<tr><td>${c.name}</td><td>${formatNumber(c.order_count)}</td><td>${formatCurrency(c.average_order_value)}</td><td>${formatCurrency(c.total_spent)}</td></tr>`
    )
    .join("") || `<tr><td colspan="4" class="empty-state">No customer activity in this period.</td></tr>`;
}

async function loadInventory() {
  const status = await fetchJSON("/api/inventory/status");
  document.getElementById("inventory-summary").textContent = `${status.healthy} healthy · ${status.low_stock} low · ${status.out_of_stock} out of stock`;

  const list = document.getElementById("inventory-alerts");
  if (status.low_stock_items.length === 0) {
    list.innerHTML = `<li class="empty-state">All products are healthily stocked.</li>`;
    return;
  }
  list.innerHTML = status.low_stock_items
    .map(
      (item) => `
      <li class="alert-item">
        <div>
          <div class="name">${item.product_name}</div>
          <div class="meta">${item.category} · stock ${item.current_stock} / threshold ${item.reorder_threshold}</div>
        </div>
        <span class="badge ${item.status}">${item.status.replaceAll("_", " ")}</span>
      </li>`
    )
    .join("");
}

async function loadExpenses(range) {
  const data = await fetchJSON("/api/expenses", range);
  document.getElementById("expense-total").textContent = `Total ${formatCurrency(data.total)}`;

  const categories = Object.entries(data.by_category).sort((a, b) => b[1] - a[1]);
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
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      cutout: "65%",
    },
  });

  const legend = document.getElementById("expense-legend");
  legend.innerHTML = categories
    .map(
      ([name, amount]) => `
      <li>
        <span class="legend-swatch" style="background:${CATEGORY_COLORS[name] || "#cbd5e1"}"></span>
        <span>${name}</span>
        <span class="amount">${formatCurrency(amount)}</span>
      </li>`
    )
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
          backgroundColor: "#bae6fd",
          yAxisID: "y",
          borderRadius: 4,
        },
        {
          type: "line",
          label: "Conversion rate (%)",
          data: points.map((p) => p.conversion_rate),
          borderColor: "#ec4899",
          backgroundColor: "#ec4899",
          tension: 0.3,
          yAxisID: "y1",
          pointRadius: 0,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: { position: "left", title: { display: true, text: "Visitors" } },
        y1: { position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Conversion %" } },
      },
      plugins: { legend: { position: "bottom" } },
    },
  });
}

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

loadDashboard().catch((err) => console.error(err));
