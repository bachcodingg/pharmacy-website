import {
  getCart, updateCartQuantity, removeFromCart, saveForLater, moveCartItemToCart,
  applyDiscountCode, removeDiscountCode, getToken,
} from '../api.js';
import { escapeHtml, formatVnd, productThumbHtml } from '../shared.js';
import { t } from '../i18n.js';
import { refreshNavBadges } from '../nav.js';
import { navigate } from '../router.js';

export async function render(root) {
  if (!getToken()) {
    root.innerHTML = `<div class="empty-state">${t('common.signInTo.cart')}</div>`;
    return;
  }

  root.innerHTML = `<div class="loading">${t('common.loading')}</div>`;
  const cart = await getCart();
  renderCart(root, cart);
}

function renderCart(root, cart) {
  root.innerHTML = `
    <h1 class="page-title">${t('cart.title')}</h1>
    <div class="cart-layout">
      <div class="cart-items">
        <div id="cart-active"></div>
        <div id="cart-saved"></div>
      </div>
      <aside class="cart-summary">
        <h2>${t('cart.summary')}</h2>
        <div class="summary-row"><span>${t('cart.subtotal')}</span><span>${formatVnd(cart.subtotal) || formatVnd(0)}</span></div>
        <div id="discount-row"></div>
        <div class="summary-row summary-total"><span>${t('cart.total')}</span><span>${formatVnd(cart.total) || formatVnd(0)}</span></div>

        <form id="discount-form" class="discount-form">
          <input type="text" name="code" placeholder="${t('cart.discountCode')}" aria-label="${t('cart.discountCode')}" value="${cart.discount_code ? escapeHtml(cart.discount_code) : ''}" ${cart.discount_code ? 'disabled' : ''} />
          ${cart.discount_code
            ? `<button type="button" id="remove-discount" class="secondary-btn">${t('common.remove')}</button>`
            : `<button type="submit">${t('common.apply')}</button>`}
        </form>
        <div id="discount-error" class="form-error" role="alert"></div>

        <button type="button" class="checkout-btn" id="checkout-btn" ${cart.items.length ? '' : 'disabled'}>${t('cart.checkout')}</button>
      </aside>
    </div>
  `;

  if (cart.discount_code) {
    root.querySelector('#discount-row').innerHTML = `
      <div class="summary-row summary-discount">
        <span>${t('cart.discount', { code: escapeHtml(cart.discount_code) })}</span>
        <span>−${formatVnd(cart.discount_amount) || formatVnd(0)}</span>
      </div>`;
  }

  renderLines(root.querySelector('#cart-active'), cart.items, { emptyText: t('cart.empty'), showSaveForLater: true });
  renderLines(root.querySelector('#cart-saved'), cart.saved_for_later, {
    emptyText: '',
    title: cart.saved_for_later.length ? t('cart.savedForLater') : '',
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

  root.querySelector('#checkout-btn').addEventListener('click', () => navigate('#/checkout'));
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
        ${productThumbHtml(item.imageUrl, item.webName)}
        <a href="#/product/${item.product_id}" class="cart-line-name">${escapeHtml(item.webName)}</a>
        ${item.prescription ? `<span class="rx-tag">${t('common.rxOnly')}</span>` : ''}
        <div class="cart-line-price">
          ${formatVnd(item.price, item.price_unit)}
          ${item.price_is_estimated ? `<span class="estimate-tag">${t('common.estimated')}</span>` : ''}
        </div>
        <div class="cart-line-controls">
          ${showSaveForLater
            ? `<input type="number" class="qty-input" min="1" max="${item.stock}" value="${item.quantity}" data-product-id="${item.product_id}" aria-label="${t('cart.qty', { n: '' })}" />`
            : `<span class="cart-line-qty">${t('cart.qty', { n: item.quantity })}</span>`}
          <span class="cart-line-total">${formatVnd(item.line_total)}</span>
        </div>
        <div class="cart-line-actions">
          ${showSaveForLater ? `<button type="button" class="link-btn" data-save-for-later="${item.product_id}">${t('cart.saveForLater')}</button>` : ''}
          ${showMoveToCart ? `<button type="button" class="link-btn" data-move-to-cart="${item.product_id}">${t('common.moveToCart')}</button>` : ''}
          <button type="button" class="link-btn" data-remove="${item.product_id}">${t('common.remove')}</button>
        </div>
      </div>`
      )
      .join('')}
  `;
}
