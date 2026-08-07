import { getOrder, getToken } from '../api.js';
import { escapeHtml, formatVnd } from '../shared.js';
import { navigate } from '../router.js';

const STATUS_LABELS = {
  placed: 'Placed',
  pending_payment: 'Awaiting payment (demo)',
};

export async function render(root, params) {
  if (!getToken()) {
    root.innerHTML = `<div class="empty-state">Please <a href="#/account">sign in</a> to view this order.</div>`;
    return;
  }
  const orderId = params?.[0];
  if (!orderId) {
    navigate('#/account');
    return;
  }

  root.innerHTML = `<div class="loading">Loading…</div>`;
  let order;
  try {
    order = await getOrder(orderId);
  } catch (err) {
    root.innerHTML = `<div class="empty-state">Order not found.</div>`;
    return;
  }

  root.innerHTML = `
    <a href="#/account" class="back-link">← Back to account</a>
    <div class="product-detail">
      <h1>Order #${order.id}</h1>
      <div class="product-detail-meta">
        <span class="status-pill status-corrected">${escapeHtml(STATUS_LABELS[order.status] || order.status)}</span>
        <span class="hint-text">${escapeHtml(order.shipping_method)} shipping · ${escapeHtml(order.payment_method.toUpperCase())}</span>
      </div>

      <h3>Items</h3>
      <div class="cart-items">
        ${order.items
          .map(
            (item) => `
          <div class="cart-line">
            <a href="#/product/${item.product_id}" class="cart-line-name">${escapeHtml(item.webName)}</a>
            <div class="cart-line-price">${formatVnd(item.unit_price)} each ${item.price_was_estimated ? '<span class="estimate-tag">was estimated</span>' : ''}</div>
            <div class="cart-line-controls">
              <span class="cart-line-qty">Qty: ${item.quantity}</span>
              <span class="cart-line-total">${formatVnd(item.line_total)}</span>
            </div>
          </div>`
          )
          .join('')}
      </div>

      <div class="order-totals">
        <div class="summary-row"><span>Subtotal</span><span>${formatVnd(order.subtotal)}</span></div>
        ${order.discount_code ? `<div class="summary-row summary-discount"><span>Discount (${escapeHtml(order.discount_code)})</span><span>−${formatVnd(order.discount_amount)}</span></div>` : ''}
        <div class="summary-row"><span>Shipping</span><span>${order.shipping_fee > 0 ? formatVnd(order.shipping_fee) : 'Free'}</span></div>
        <div class="summary-row summary-total"><span>Total</span><span>${formatVnd(order.total)}</span></div>
      </div>
    </div>
  `;
}
