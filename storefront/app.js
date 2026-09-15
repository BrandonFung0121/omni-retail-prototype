const API_BASE = "";

const state = {
  products: [],
  cart: loadCart(),
  auth: loadAuth(),
  route: "/",
  routeParam: null,
  idempotencyKey: null,
};

// ---------- storage ----------
function loadCart() {
  try {
    return JSON.parse(localStorage.getItem("omni_shop_cart") || "[]");
  } catch {
    return [];
  }
}
function saveCart() {
  localStorage.setItem("omni_shop_cart", JSON.stringify(state.cart));
}
function loadAuth() {
  try {
    return JSON.parse(localStorage.getItem("omni_shop_auth") || "null") || { token: null, customer: null };
  } catch {
    return { token: null, customer: null };
  }
}
function saveAuth() {
  localStorage.setItem("omni_shop_auth", JSON.stringify(state.auth));
}

// ---------- helpers ----------
function escapeHTML(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}
function formatCurrency(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}
function initials(name) {
  const parts = (name || "").trim().split(/\s+/);
  return parts.length > 1 ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase() : (parts[0]?.[0] || "?").toUpperCase();
}

async function api(path, { method = "GET", body, auth = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && state.auth.token) headers.Authorization = `Bearer ${state.auth.token}`;
  const response = await fetch(API_BASE + path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || `Request failed (${response.status})`);
    error.status = response.status;
    error.detail = data.detail;
    throw error;
  }
  return data;
}

// ---------- routing ----------
function parseHash() {
  const hash = (location.hash || "#/").slice(1) || "/";
  const parts = hash.split("/").filter(Boolean);
  if (parts.length === 0) return { route: "/", param: null };
  if (parts[0] === "product" && parts[1]) return { route: "/product", param: parts[1] };
  return { route: "/" + parts[0], param: null };
}

function navigate() {
  const { route, param } = parseHash();
  state.route = route;
  state.routeParam = param;

  document.querySelectorAll(".view").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(".shop-nav a").forEach((el) => el.classList.remove("active"));

  if (route === "/orders" && !state.auth.token) {
    location.hash = "#/login";
    return;
  }
  if (route === "/checkout" && state.cart.length === 0) {
    location.hash = "#/cart";
    return;
  }

  const viewId = { "/": "view-home", "/products": "view-products", "/product": "view-product", "/cart": "view-cart", "/checkout": "view-checkout", "/login": "view-login", "/register": "view-register", "/orders": "view-orders" }[route] || "view-home";
  document.getElementById(viewId).classList.add("active");
  document.querySelector(`.shop-nav a[data-route="${route === "/product" ? "/products" : route}"]`)?.classList.add("active");
  window.scrollTo(0, 0);

  if (route === "/") renderHome();
  if (route === "/products") renderCatalogue();
  if (route === "/product") renderProductDetail(Number(param));
  if (route === "/cart") renderCart();
  if (route === "/checkout") startCheckout();
  if (route === "/orders") loadMyOrders();
}
window.addEventListener("hashchange", navigate);

// ---------- account menu ----------
function renderAccountMenu() {
  const el = document.getElementById("shop-account");
  if (state.auth.token && state.auth.customer) {
    el.innerHTML = `
      <div class="account-chip">
        <span class="account-avatar">${initials(state.auth.customer.name)}</span>
        <span>${escapeHTML(state.auth.customer.name.split(" ")[0])}</span>
      </div>
      <button type="button" class="account-logout" id="logout-btn">Log out</button>
    `;
    document.getElementById("logout-btn").addEventListener("click", () => {
      state.auth = { token: null, customer: null };
      saveAuth();
      renderAccountMenu();
      location.hash = "#/";
    });
  } else {
    el.innerHTML = `<a href="#/login" class="btn btn-secondary">Log in</a>`;
  }
}

function updateCartCount() {
  const count = state.cart.reduce((sum, i) => sum + i.quantity, 0);
  const el = document.getElementById("cart-count");
  el.textContent = String(count);
  el.dataset.zero = count === 0 ? "true" : "false";
}

// ---------- products ----------
async function loadProducts() {
  state.products = await api("/api/products");
  const categories = [...new Set(state.products.map((p) => p.category))].sort();
  const select = document.getElementById("catalogue-category");
  select.innerHTML = `<option value="">All categories</option>` + categories.map((c) => `<option value="${escapeHTML(c)}">${escapeHTML(c)}</option>`).join("");
}

function productCardHTML(p) {
  const flag = p.status !== "healthy" ? `<span class="stock-flag ${p.status}">${p.status === "out_of_stock" ? "Out of stock" : "Low stock"}</span>` : "";
  return `
    <a href="#/product/${p.product_id}" class="product-card">
      <div class="product-card-media">${flag}${escapeHTML(p.name[0])}</div>
      <div class="product-card-body">
        <span class="product-card-category">${escapeHTML(p.category)}</span>
        <span class="product-card-name">${escapeHTML(p.name)}</span>
        <span class="product-card-price">${formatCurrency(p.selling_price)}</span>
      </div>
    </a>`;
}

function renderHome() {
  const featured = [...state.products].sort((a, b) => b.selling_price - a.selling_price).slice(0, 4);
  document.getElementById("home-featured").innerHTML = featured.map(productCardHTML).join("");
}

function renderCatalogue() {
  const query = document.getElementById("catalogue-search").value.trim().toLowerCase();
  const category = document.getElementById("catalogue-category").value;
  const sort = document.getElementById("catalogue-sort").value;

  let items = state.products.filter((p) => {
    const matchesQuery = !query || p.name.toLowerCase().includes(query) || p.category.toLowerCase().includes(query);
    const matchesCategory = !category || p.category === category;
    return matchesQuery && matchesCategory;
  });

  if (sort === "price-asc") items.sort((a, b) => a.selling_price - b.selling_price);
  else if (sort === "price-desc") items.sort((a, b) => b.selling_price - a.selling_price);
  else items.sort((a, b) => a.name.localeCompare(b.name));

  document.getElementById("catalogue-grid").innerHTML =
    items.map(productCardHTML).join("") || `<p class="empty-panel">No products match your search.</p>`;
}

async function renderProductDetail(productId) {
  const body = document.getElementById("product-detail-body");
  body.innerHTML = "<p>Loading...</p>";
  try {
    const p = await api(`/api/products/${productId}`);
    const statusLabel = { healthy: "In stock", low_stock: "Low stock — order soon", out_of_stock: "Out of stock" }[p.status];
    body.innerHTML = `
      <div class="product-detail-media">${escapeHTML(p.name[0])}</div>
      <div>
        <div class="product-detail-category">${escapeHTML(p.category)}</div>
        <h1 class="product-detail-name">${escapeHTML(p.name)}</h1>
        <div class="product-detail-price">${formatCurrency(p.selling_price)}</div>
        <p class="product-detail-desc">${/^[aeiou]/i.test(p.category) ? "An" : "A"} ${escapeHTML(p.category.toLowerCase())} favorite. Sourced from OMNI Retail's regular catalogue — the same item your local store carries.</p>
        <div class="product-detail-stock ${p.status}">${statusLabel}</div>
        <div class="qty-picker">
          <button type="button" id="pd-dec">&minus;</button>
          <span id="pd-qty">1</span>
          <button type="button" id="pd-inc">+</button>
        </div>
        <button type="button" class="btn btn-primary btn-lg" id="pd-add-btn" ${p.current_stock <= 0 ? "disabled" : ""}>
          ${p.current_stock <= 0 ? "Out of Stock" : "Add to Cart"}
        </button>
      </div>
    `;
    let qty = 1;
    const qtyEl = document.getElementById("pd-qty");
    document.getElementById("pd-dec").addEventListener("click", () => {
      qty = Math.max(1, qty - 1);
      qtyEl.textContent = String(qty);
    });
    document.getElementById("pd-inc").addEventListener("click", () => {
      qty = Math.min(p.current_stock, qty + 1);
      qtyEl.textContent = String(qty);
    });
    document.getElementById("pd-add-btn").addEventListener("click", () => {
      addToCart(p, qty);
    });
  } catch (err) {
    body.innerHTML = `<p class="empty-panel">Couldn't find that product.</p>`;
  }
}

// ---------- cart ----------
function addToCart(product, quantity) {
  const existing = state.cart.find((i) => i.product_id === product.product_id);
  if (existing) {
    existing.quantity = Math.min(product.current_stock, existing.quantity + quantity);
  } else {
    state.cart.push({
      product_id: product.product_id,
      name: product.name,
      selling_price: product.selling_price,
      quantity: Math.min(product.current_stock, quantity),
      current_stock: product.current_stock,
    });
  }
  saveCart();
  updateCartCount();
}

function changeCartQty(productId, delta) {
  const item = state.cart.find((i) => i.product_id === productId);
  if (!item) return;
  item.quantity = Math.max(0, item.quantity + delta);
  state.cart = state.cart.filter((i) => i.quantity > 0);
  saveCart();
  updateCartCount();
  renderCart();
}

function removeFromCart(productId) {
  state.cart = state.cart.filter((i) => i.product_id !== productId);
  saveCart();
  updateCartCount();
  renderCart();
}

function cartSubtotal() {
  return state.cart.reduce((sum, i) => sum + i.selling_price * i.quantity, 0);
}

function renderCart() {
  const list = document.getElementById("cart-list");
  list.innerHTML =
    state.cart
      .map(
        (item) => `
      <li class="cart-line">
        <div class="cart-line-media">${escapeHTML(item.name[0])}</div>
        <div class="cart-line-info">
          <div class="cart-line-name">${escapeHTML(item.name)}</div>
          <div class="cart-line-price">${formatCurrency(item.selling_price)} each</div>
        </div>
        <div class="cart-line-qty">
          <button type="button" data-action="dec" data-id="${item.product_id}">&minus;</button>
          <span>${item.quantity}</span>
          <button type="button" data-action="inc" data-id="${item.product_id}">+</button>
        </div>
        <div class="cart-line-total">${formatCurrency(item.selling_price * item.quantity)}</div>
        <button type="button" class="cart-line-remove" data-action="remove" data-id="${item.product_id}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
        </button>
      </li>`
      )
      .join("") || `<li class="empty-panel">Your cart is empty. <a href="#/products" class="btn btn-primary">Start Shopping</a></li>`;

  list.querySelectorAll("button[data-action]").forEach((btn) => {
    const id = Number(btn.dataset.id);
    btn.addEventListener("click", () => {
      if (btn.dataset.action === "inc") changeCartQty(id, 1);
      else if (btn.dataset.action === "dec") changeCartQty(id, -1);
      else removeFromCart(id);
    });
  });

  document.getElementById("cart-subtotal").textContent = formatCurrency(cartSubtotal());
}

document.getElementById("cart-checkout-btn").addEventListener("click", () => {
  location.hash = "#/checkout";
});

// ---------- checkout ----------
function setCheckoutStep(step) {
  const stepIndicator = { processing: "payment", success: "confirm", failed: "confirm" }[step] || step;
  document.querySelectorAll("#checkout-steps li").forEach((li) => li.classList.toggle("active", li.dataset.step === stepIndicator));
  ["review", "payment", "processing", "success", "failed"].forEach((s) => {
    document.getElementById(`checkout-step-${s}`).hidden = s !== step;
  });
}

function startCheckout() {
  state.idempotencyKey = null;
  setCheckoutStep("review");
  document.getElementById("checkout-error").textContent = "";

  document.getElementById("checkout-review-list").innerHTML = state.cart
    .map((i) => `<li><span>${escapeHTML(i.name)} &times;${i.quantity}</span><span>${formatCurrency(i.selling_price * i.quantity)}</span></li>`)
    .join("");

  const identity = document.getElementById("checkout-identity");
  identity.innerHTML = state.auth.token
    ? `Checking out as <strong>${escapeHTML(state.auth.customer.name)}</strong> (${escapeHTML(state.auth.customer.email)}).`
    : `Checking out as <strong>Guest</strong>. <a href="#/login">Log in</a> to save this order to an account.`;

  renderCheckoutSummary();
}

function renderCheckoutSummary() {
  const subtotal = cartSubtotal();
  document.getElementById("checkout-summary").innerHTML = `
    <h2>Order Summary</h2>
    <div class="summary-row"><span>Items</span><span>${state.cart.reduce((s, i) => s + i.quantity, 0)}</span></div>
    <div class="summary-row total"><span>Total</span><span>${formatCurrency(subtotal)}</span></div>
  `;
}

document.getElementById("checkout-to-payment-btn").addEventListener("click", () => setCheckoutStep("payment"));

document.querySelectorAll('input[name="payment-method"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    document.getElementById("card-fields").style.display = radio.value === "credit_card" && radio.checked ? "block" : "none";
  });
});

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function placeOrder() {
  const errorEl = document.getElementById("checkout-error");
  errorEl.textContent = "";
  const method = document.querySelector('input[name="payment-method"]:checked').value;
  const cardNumber = document.getElementById("card-number").value.trim();

  if (method === "credit_card" && !cardNumber) {
    errorEl.textContent = "Enter a card number (try 4242 4242 4242 4242).";
    return;
  }

  if (!state.idempotencyKey) {
    state.idempotencyKey = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);
  }

  const placeBtn = document.getElementById("place-order-btn");
  placeBtn.disabled = true;
  setCheckoutStep("processing");

  const payload = {
    items: state.cart.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
    payment_method: method,
    channel: "online",
    card_number: method === "credit_card" ? cardNumber : null,
    idempotency_key: state.idempotencyKey,
  };

  try {
    const [receipt] = await Promise.all([api("/api/storefront/checkout", { method: "POST", body: payload, auth: true }), delay(1100)]);

    if (receipt.status === "completed") {
      state.cart = [];
      saveCart();
      updateCartCount();
      showSuccess(receipt);
    } else {
      showFailed(receipt);
    }
  } catch (err) {
    await delay(300);
    errorEl.textContent = err.detail || "Something went wrong. Please try again.";
    setCheckoutStep("payment");
  } finally {
    placeBtn.disabled = false;
  }
}
document.getElementById("place-order-btn").addEventListener("click", placeOrder);

document.getElementById("retry-payment-btn").addEventListener("click", () => {
  state.idempotencyKey = null; // a retry is a new attempt, not a resend of the failed one
  setCheckoutStep("payment");
});

function receiptHTML(receipt) {
  const lines = receipt.lines
    .map((l) => `<div class="r-line"><span>${escapeHTML(l.product_name)} &times;${l.quantity}</span><span>${formatCurrency(l.line_total)}</span></div>`)
    .join("");
  return `
    ${lines}
    <div class="r-line r-total"><span>Total</span><span>${formatCurrency(receipt.total)}</span></div>
    <div class="r-meta">Payment: ${escapeHTML(receipt.payment_method.replaceAll("_", " "))} &middot; Ref ${escapeHTML(receipt.payment_reference)}</div>
  `;
}

function showSuccess(receipt) {
  setCheckoutStep("success");
  document.getElementById("success-order-ref").textContent = `Order #${receipt.order_id} — confirmation sent to ${state.auth.customer ? state.auth.customer.email : "your email"}.`;
  document.getElementById("success-receipt").innerHTML = receiptHTML(receipt);
}

function showFailed(receipt) {
  setCheckoutStep("failed");
  document.getElementById("failed-reason").textContent = receipt.failure_reason || "Your payment could not be processed.";
}

// ---------- auth ----------
document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("login-error");
  errorEl.textContent = "";
  try {
    const data = await api("/api/storefront/auth/login", {
      method: "POST",
      body: { email: document.getElementById("login-email").value.trim(), password: document.getElementById("login-password").value },
    });
    state.auth = data;
    saveAuth();
    renderAccountMenu();
    location.hash = "#/orders";
  } catch (err) {
    errorEl.textContent = err.detail || "Login failed.";
  }
});

document.getElementById("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("register-error");
  errorEl.textContent = "";
  try {
    const data = await api("/api/storefront/auth/register", {
      method: "POST",
      body: {
        name: document.getElementById("register-name").value.trim(),
        email: document.getElementById("register-email").value.trim(),
        password: document.getElementById("register-password").value,
      },
    });
    state.auth = data;
    saveAuth();
    renderAccountMenu();
    location.hash = "#/";
  } catch (err) {
    errorEl.textContent = err.detail || "Registration failed.";
  }
});

// ---------- my orders ----------
async function loadMyOrders() {
  const body = document.getElementById("orders-body");
  body.innerHTML = "<p>Loading...</p>";
  try {
    const orders = await api("/api/storefront/orders", { auth: true });
    if (orders.length === 0) {
      body.innerHTML = `<div class="empty-panel">No orders yet. <a href="#/products" class="btn btn-primary">Start Shopping</a></div>`;
      return;
    }
    body.innerHTML = `
      <table class="orders-table">
        <thead><tr><th>Order</th><th>Date</th><th>Items</th><th>Total</th><th>Status</th></tr></thead>
        <tbody>
          ${orders
            .map(
              (o) => `
            <tr data-order-id="${o.order_id}">
              <td>#${o.order_id}</td>
              <td>${escapeHTML(o.order_datetime.replace("T", " ").slice(0, 16))}</td>
              <td>${o.item_count}</td>
              <td>${formatCurrency(o.total)}</td>
              <td><span class="order-status-pill ${o.status}">${escapeHTML(o.status)}</span></td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    `;
    body.querySelectorAll("tr[data-order-id]").forEach((row) => {
      row.addEventListener("click", () => showMyOrderDetail(Number(row.dataset.orderId)));
    });
  } catch (err) {
    body.innerHTML = `<div class="empty-panel">Couldn't load your orders.</div>`;
  }
}

async function showMyOrderDetail(orderId) {
  const overlay = document.getElementById("order-detail-overlay");
  const card = document.getElementById("order-detail-card");
  card.innerHTML = "<p style='padding:20px'>Loading...</p>";
  overlay.classList.add("open");
  try {
    const order = await api(`/api/storefront/orders/${orderId}`, { auth: true });
    const lines = order.lines
      .map((l) => `<div class="r-line"><span>${escapeHTML(l.product_name)} &times;${l.quantity}</span><span>${formatCurrency(l.line_total)}</span></div>`)
      .join("");
    card.innerHTML = `
      <div style="padding:22px">
        <h2 style="margin-bottom:4px">Order #${order.order_id}</h2>
        <p style="color:var(--text-tertiary);font-size:12.5px;margin-bottom:16px">${escapeHTML(order.order_datetime.replace("T", " ").slice(0, 16))} &middot; <span class="order-status-pill ${order.status}">${escapeHTML(order.status)}</span></p>
        ${lines}
        <div class="r-line r-total"><span>Total</span><span>${formatCurrency(order.total)}</span></div>
        <div class="r-meta">Payment: ${escapeHTML((order.payment_method || "-").replaceAll("_", " "))} &middot; ${escapeHTML(order.payment_status || "-")}</div>
        <button type="button" class="btn btn-secondary btn-full" id="order-detail-close" style="margin-top:18px">Close</button>
      </div>
    `;
    document.getElementById("order-detail-close").addEventListener("click", () => overlay.classList.remove("open"));
  } catch (err) {
    card.innerHTML = `<p style="padding:20px">Couldn't load that order.</p>`;
  }
}
document.getElementById("order-detail-overlay").addEventListener("click", (e) => {
  if (e.target.id === "order-detail-overlay") e.currentTarget.classList.remove("open");
});

// ---------- search / filters ----------
document.getElementById("header-search").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const q = e.target.value.trim();
    location.hash = "#/products";
    setTimeout(() => {
      document.getElementById("catalogue-search").value = q;
      renderCatalogue();
    }, 0);
  }
});
document.getElementById("catalogue-search").addEventListener("input", renderCatalogue);
document.getElementById("catalogue-category").addEventListener("change", renderCatalogue);
document.getElementById("catalogue-sort").addEventListener("change", renderCatalogue);

// ---------- init ----------
(async function init() {
  renderAccountMenu();
  updateCartCount();
  try {
    await loadProducts();
  } catch (err) {
    console.error(err);
  }
  navigate();
})();
