/* "Ask OMNI" shopping assistant widget.
 *
 * Talks to POST /api/storefront/assistant/ask, sending the current
 * client-side cart (state.cart, from app.js) as context and applying
 * any suggested cart_action through the EXACT same addToCart() the
 * catalogue's "Add to Cart" button uses -- no separate cart logic.
 * Each question is answered independently (no chat history is sent),
 * matching the admin AI Assistant's stateless-per-question design.
 *
 * Relies on globals already defined by app.js, loaded first:
 * escapeHTML, formatCurrency, state, addToCart, updateCartCount,
 * productCardHTML.
 */

const askOmni = {
  open: false,
  loading: false,
};

function askOmniEl(id) {
  return document.getElementById(id);
}

function openAskOmni() {
  askOmni.open = true;
  askOmniEl("ask-omni-drawer").classList.add("open");
  askOmniEl("ask-omni-drawer").setAttribute("aria-hidden", "false");
  askOmniEl("ask-omni-scrim").classList.add("open");
  askOmniEl("ask-omni-launcher").setAttribute("aria-expanded", "true");
  askOmniEl("ask-omni-input").focus();
}

function closeAskOmni() {
  askOmni.open = false;
  askOmniEl("ask-omni-drawer").classList.remove("open");
  askOmniEl("ask-omni-drawer").setAttribute("aria-hidden", "true");
  askOmniEl("ask-omni-scrim").classList.remove("open");
  askOmniEl("ask-omni-launcher").setAttribute("aria-expanded", "false");
}

askOmniEl("ask-omni-launcher").addEventListener("click", () => {
  askOmni.open ? closeAskOmni() : openAskOmni();
});
askOmniEl("ask-omni-close").addEventListener("click", closeAskOmni);
askOmniEl("ask-omni-scrim").addEventListener("click", closeAskOmni);

function askOmniProductCardsHTML(productIds) {
  const products = (productIds || [])
    .map((id) => state.products.find((p) => p.product_id === id))
    .filter(Boolean);
  if (!products.length) return "";
  return `<div class="ask-omni-product-grid">${products.map(productCardHTML).join("")}</div>`;
}

function renderAskOmniLoading() {
  const thread = askOmniEl("ask-omni-thread");
  const card = document.createElement("div");
  card.className = "ask-omni-bubble ask-omni-bubble-assistant ask-omni-loading";
  card.innerHTML = `<span class="dot"></span><span class="dot"></span><span class="dot"></span>`;
  thread.appendChild(card);
  thread.scrollTop = thread.scrollHeight;
  return card;
}

function renderAskOmniUserBubble(question) {
  const thread = askOmniEl("ask-omni-thread");
  const bubble = document.createElement("div");
  bubble.className = "ask-omni-bubble ask-omni-bubble-user";
  bubble.textContent = question;
  thread.appendChild(bubble);
  thread.scrollTop = thread.scrollHeight;
}

function applyAskOmniCartAction(cartAction) {
  if (!cartAction) return "";
  const product = state.products.find((p) => p.product_id === cartAction.product_id) || {
    product_id: cartAction.product_id,
    name: cartAction.product_name,
    selling_price: cartAction.unit_price,
    current_stock: cartAction.quantity,
  };
  addToCart(product, cartAction.quantity);
  return `<div class="ask-omni-cart-confirm">${escapeHTML(cartAction.product_name)} &times;${cartAction.quantity} added to your cart.</div>`;
}

function renderAskOmniAnswer(loadingCard, data) {
  const cartConfirmHtml = applyAskOmniCartAction(data.cart_action);
  const productsHtml = askOmniProductCardsHTML(data.suggested_product_ids);

  loadingCard.classList.remove("ask-omni-loading");
  loadingCard.innerHTML = `
    <p>${escapeHTML(data.answer)}</p>
    ${cartConfirmHtml}
    ${productsHtml}
  `;
  const thread = askOmniEl("ask-omni-thread");
  thread.scrollTop = thread.scrollHeight;
}

function renderAskOmniError(loadingCard) {
  loadingCard.classList.remove("ask-omni-loading");
  loadingCard.innerHTML = `<p>Sorry, I couldn't reach the shopping assistant. Please try again.</p>`;
}

async function submitAskOmniQuestion(question) {
  question = (question || "").trim();
  if (!question || askOmni.loading) return;

  const welcome = document.querySelector(".ask-omni-welcome");
  if (welcome) welcome.remove();

  renderAskOmniUserBubble(question);
  const loadingCard = renderAskOmniLoading();

  askOmni.loading = true;
  const sendBtn = document.querySelector("#ask-omni-form button");
  sendBtn.disabled = true;

  try {
    const response = await fetch("/api/storefront/assistant/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        cart: state.cart.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
      }),
    });
    if (!response.ok) throw new Error(`ask failed: ${response.status}`);
    const data = await response.json();
    renderAskOmniAnswer(loadingCard, data);
  } catch (err) {
    console.error(err);
    renderAskOmniError(loadingCard);
  } finally {
    askOmni.loading = false;
    sendBtn.disabled = false;
  }
}

askOmniEl("ask-omni-quick-actions").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-prompt]");
  if (btn) submitAskOmniQuestion(btn.dataset.prompt);
});

askOmniEl("ask-omni-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = askOmniEl("ask-omni-input");
  const question = input.value;
  input.value = "";
  submitAskOmniQuestion(question);
});
