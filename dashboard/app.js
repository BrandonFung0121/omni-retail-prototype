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

loadDashboard().catch((err) => console.error(err));
