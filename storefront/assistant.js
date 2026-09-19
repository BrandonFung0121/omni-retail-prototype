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
  pendingImage: null, // { mediaType, base64, dataUrl } set once a valid photo is chosen, cleared after send
};

const ASK_OMNI_ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/jpg", "image/png", "image/webp"];
const ASK_OMNI_MAX_IMAGE_BYTES = 5 * 1024 * 1024; // 5MB, matches the server-side limit

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

function showAskOmniImageError(message) {
  const el = askOmniEl("ask-omni-image-error");
  el.textContent = message;
  el.hidden = false;
}

function clearAskOmniImageError() {
  askOmniEl("ask-omni-image-error").hidden = true;
}

function setAskOmniPendingImage(image) {
  askOmni.pendingImage = image;
  const preview = askOmniEl("ask-omni-image-preview");
  if (image) {
    askOmniEl("ask-omni-image-preview-img").src = image.dataUrl;
    preview.hidden = false;
  } else {
    preview.hidden = true;
  }
}

function readImageFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function handleAskOmniImageSelected(file) {
  clearAskOmniImageError();
  if (!file) return;

  if (!ASK_OMNI_ALLOWED_IMAGE_TYPES.includes(file.type)) {
    showAskOmniImageError("Please choose a JPG, PNG, or WebP photo.");
    return;
  }
  if (file.size > ASK_OMNI_MAX_IMAGE_BYTES) {
    showAskOmniImageError("That photo is too large -- please use one under 5MB.");
    return;
  }

  try {
    const dataUrl = await readImageFileAsDataUrl(file);
    const [prefix, base64] = dataUrl.split(",");
    const mediaType = /data:(.*);base64/.exec(prefix)?.[1] || file.type;
    setAskOmniPendingImage({ mediaType, base64, dataUrl });
  } catch (err) {
    console.error(err);
    showAskOmniImageError("Couldn't read that photo -- please try another.");
  }
}

askOmniEl("ask-omni-image-btn").addEventListener("click", () => {
  askOmniEl("ask-omni-image-input").click();
});
askOmniEl("ask-omni-image-input").addEventListener("change", (e) => {
  handleAskOmniImageSelected(e.target.files[0]);
});
askOmniEl("ask-omni-image-remove").addEventListener("click", () => {
  setAskOmniPendingImage(null);
  askOmniEl("ask-omni-image-input").value = "";
  clearAskOmniImageError();
});

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

function renderAskOmniUserBubble(question, imageDataUrl) {
  const thread = askOmniEl("ask-omni-thread");
  const bubble = document.createElement("div");
  bubble.className = "ask-omni-bubble ask-omni-bubble-user";
  const imgHtml = imageDataUrl ? `<img class="ask-omni-sent-image" src="${imageDataUrl}" alt="Photo you sent" />` : "";
  bubble.innerHTML = `${imgHtml}${question ? `<p>${escapeHTML(question)}</p>` : ""}`;
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
  const image = askOmni.pendingImage;
  if ((!question && !image) || askOmni.loading) return;

  const welcome = document.querySelector(".ask-omni-welcome");
  if (welcome) welcome.remove();

  renderAskOmniUserBubble(question || (image ? "What's this?" : ""), image?.dataUrl);
  const loadingCard = renderAskOmniLoading();

  askOmni.loading = true;
  const sendBtn = document.querySelector("#ask-omni-form button");
  sendBtn.disabled = true;
  setAskOmniPendingImage(null);
  askOmniEl("ask-omni-image-input").value = "";

  try {
    const response = await fetch("/api/storefront/assistant/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        cart: state.cart.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
        image: image ? { media_type: image.mediaType, data: image.base64 } : null,
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
