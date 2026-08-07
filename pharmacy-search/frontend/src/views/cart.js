import {
  getCart, updateCartQuantity, removeFromCart, saveForLater, moveCartItemToCart,
  applyDiscountCode, removeDiscountCode, getToken,
} from '../api.js';
import { escapeHtml, formatVnd } from '../shared.js';
import { refreshNavBadges } from '../nav.js';

export async function render(root) {
  if (!getToken()) {
    root.innerHTML = `<div class="empty-state">Please <a href="#/account">sign in</a> to view your cart.</div>`;
    return;
  }

  root.innerHTML = `<div class="loading">Loading…</div>`;
  const cart = await getCart();
  renderCart(root, cart);
}

function renderCart(root, cart) {
  root.innerHTML = `
    <h1 class="page-title">Your cart</h1>
    <div class="cart-layout">
      <div class="cart-items">
        <div id="cart-active"></div>
        <div id="cart-saved"></div>
      </div>
      <aside class="cart-summary">
        <h2>Order summary</h2>
        <div class="summary-row"><span>Subtotal</span><span>${formatVnd(cart.subtotal) || '0₫'}</span></div>
        <div id="discount-row"></div>
        <div class="summary-row summary-total"><span>Total</span><span>${formatVnd(cart.total) || '0₫'}</span></div>

        <form id="discount-form" class="discount-form">
          <input type="text" name="code" placeholder="Discount code" value="${cart.discount_code ? escapeHtml(cart.discount_code) : ''}" ${cart.discount_code ? 'disabled' : ''} />
          ${cart.discount_code
            ? `<button type="button" id="remove-discount" class="secondary-btn">Remove</button>`
            : `<button type="submit">Apply</button>`}
        </form>
        <div id="discount-error" class="form-error"></div>

        <button type="button" class="checkout-btn" disabled title="Checkout isn't built yet">Proceed to checkout</button>
        <p class="hint-text">Checkout isn't available yet — this button is a placeholder for what comes next.</p>
      </aside>
    </div>
  `;

  if (cart.discount_code) {
    root.querySelector('#discount-row').innerHTML = `
      <div class="summary-row summary-discount">
        <span>Discount (${escapeHtml(cart.discount_code)})</span>
        <span>−${formatVnd(cart.discount_amount) || '0₫'}</span>
      </div>`;
  }

  renderLines(root.querySelector('#cart-active'), cart.items, { emptyText: 'Your cart is empty.', showSaveForLater: true });
  renderLines(root.querySelector('#cart-saved'), cart.saved_for_later, {
    emptyText: '',
    title: cart.saved_for_later.length ? 'Saved for later' : '',
    showMoveToCart: true,
  });

  root.querySelectorAll('.qty-input').forEach((input) => {
    input.addEventListener('change', async () => {
      const quantity = Math.max(1, parseInt(input.value, 10) || 1);
      const updated = await updateCartQuantity(input.dataset.productId, quantity);
      refreshNavBadges();
      renderCart(root, updated);
    });
  });

  root.querySelectorAll('[data-remove]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const updated = await removeFromCart(btn.dataset.remove);
      refreshNavBadges();
      renderCart(root, updated);
    });
  });

  root.querySelectorAll('[data-save-for-later]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const updated = await saveForLater(btn.dataset.saveForLater);
      refreshNavBadges();
      renderCart(root, updated);
    });
  });

  root.querySelectorAll('[data-move-to-cart]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const updated = await moveCartItemToCart(btn.dataset.moveToCart);
      refreshNavBadges();
      renderCart(root, updated);
    });
  });

  const discountForm = root.querySelector('#discount-form');
  discountForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const code = new FormData(discountForm).get('code');
    const errorEl = root.querySelector('#discount-error');
    errorEl.textContent = '';
    try {
      const updated = await applyDiscountCode(code);
      renderCart(root, updated);
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });

  const removeDiscountBtn = root.querySelector('#remove-discount');
  if (removeDiscountBtn) {
    removeDiscountBtn.addEventListener('click', async () => {
      const updated = await removeDiscountCode();
      renderCart(root, updated);
    });
  }
}

function renderLines(container, lines, { emptyText, title, showSaveForLater, showMoveToCart }) {
  if (!lines.length) {
    container.innerHTML = emptyText ? `<div class="empty-state">${emptyText}</div>` : '';
    return;
  }
  container.innerHTML = `
    ${title ? `<h2 class="cart-section-title">${escapeHtml(title)}</h2>` : ''}
    ${lines
      .map(
        (item) => `
      <div class="cart-line">
        <a href="#/product/${item.product_id}" class="cart-line-name">${escapeHtml(item.webName)}</a>
        <div class="cart-line-price">
          ${formatVnd(item.price, item.price_unit)}
          ${item.price_is_estimated ? '<span class="estimate-tag">estimated</span>' : ''}
        </div>
        <div class="cart-line-controls">
          ${showSaveForLater
            ? `<input type="number" class="qty-input" min="1" max="${item.stock}" value="${item.quantity}" data-product-id="${item.product_id}" />`
            : `<span class="cart-line-qty">Qty: ${item.quantity}</span>`}
          <span class="cart-line-total">${formatVnd(item.line_total)}</span>
        </div>
        <div class="cart-line-actions">
          ${showSaveForLater ? `<button type="button" class="link-btn" data-save-for-later="${item.product_id}">Save for later</button>` : ''}
          ${showMoveToCart ? `<button type="button" class="link-btn" data-move-to-cart="${item.product_id}">Move to cart</button>` : ''}
          <button type="button" class="link-btn" data-remove="${item.product_id}">Remove</button>
        </div>
      </div>`
      )
      .join('')}
  `;
}
