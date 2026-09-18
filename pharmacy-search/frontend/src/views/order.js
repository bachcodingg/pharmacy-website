import { getOrder, getToken } from '../api.js';
import { escapeHtml, formatVnd, productThumbHtml } from '../shared.js';
import { t } from '../i18n.js';
import { navigate } from '../router.js';

// Server statuses are the keys; an unknown one falls back to the raw value so
// a new status added on the backend shows up rather than disappearing.
const STATUSES = ['placed', 'pending_payment', 'awaiting_prescription', 'shipped', 'delivered', 'cancelled'];
const RX_STATUSES = ['pending_review', 'approved', 'rejected'];

const statusLabel = (status) =>
  (STATUSES.includes(status) ? t(`order.status.${status}`) : status);

export async function render(root, params) {
  if (!getToken()) {
    root.innerHTML = `<div class="empty-state">${t('common.signInTo.order')}</div>`;
    return;
  }
  const orderId = params?.[0];
  if (!orderId) {
    navigate('#/account');
    return;
  }

  root.innerHTML = `<div class="loading">${t('common.loading')}</div>`;
  let order;
  try {
    order = await getOrder(orderId);
  } catch (err) {
    root.innerHTML = `<div class="empty-state">${t('order.notFound')}</div>`;
    return;
  }

  root.innerHTML = `
    <a href="#/account" class="back-link">${t('order.backToAccount')}</a>
    <div class="product-detail">
      <h1>${t('order.title', { id: order.id })}</h1>
      <div class="product-detail-meta">
        <span class="status-pill status-corrected">${escapeHtml(statusLabel(order.status))}</span>
        <span class="hint-text">${t('order.shippingAndPayment', {
          shipping: escapeHtml(order.shipping_method),
          payment: escapeHtml(order.payment_method.toUpperCase()),
        })}</span>
      </div>

      ${order.requires_prescription && RX_STATUSES.includes(order.prescription_status)
        ? `<div class="notice notice-dym"><span class="notice-body">
             <div class="notice-title">${t('order.prescriptionTitle', { status: t(`order.rxStatus.${order.prescription_status}`) })}</div>
             ${escapeHtml(t(`order.rx.${order.prescription_status}`))}
             ${order.prescription_reference ? `<div class="hint-text">${t('order.reference', { ref: escapeHtml(order.prescription_reference) })}</div>` : ''}
           </span></div>`
        : ''}

      <h3>${t('order.items')}</h3>
      <div class="cart-items">
        ${order.items
          .map(
            (item) => `
          <div class="cart-line">
            ${productThumbHtml(item.imageUrl, item.webName)}
            <a href="#/product/${item.product_id}" class="cart-line-name">${escapeHtml(item.webName)}</a>
            <div class="cart-line-price">${formatVnd(item.unit_price)} ${t('order.each')} ${item.price_was_estimated ? `<span class="estimate-tag">${t('order.wasEstimated')}</span>` : ''}</div>
            <div class="cart-line-controls">
              <span class="cart-line-qty">${t('cart.qty', { n: item.quantity })}</span>
              <span class="cart-line-total">${formatVnd(item.line_total)}</span>
            </div>
          </div>`
          )
          .join('')}
      </div>

      <div class="order-totals">
        <div class="summary-row"><span>${t('cart.subtotal')}</span><span>${formatVnd(order.subtotal)}</span></div>
        ${order.discount_code ? `<div class="summary-row summary-discount"><span>${t('cart.discount', { code: escapeHtml(order.discount_code) })}</span><span>−${formatVnd(order.discount_amount)}</span></div>` : ''}
        <div class="summary-row"><span>${t('checkout.shippingFee')}</span><span>${order.shipping_fee > 0 ? formatVnd(order.shipping_fee) : t('common.free')}</span></div>
        <div class="summary-row summary-total"><span>${t('cart.total')}</span><span>${formatVnd(order.total)}</span></div>
      </div>
    </div>
  `;
}
