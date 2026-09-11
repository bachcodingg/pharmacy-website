import { getCart, listAddresses, getCheckoutOptions, placeOrder, getToken } from '../api.js';
import { escapeHtml, formatVnd } from '../shared.js';
import { navigate } from '../router.js';
import { refreshNavBadges } from '../nav.js';

export async function render(root) {
  if (!getToken()) {
    root.innerHTML = `<div class="empty-state">Please <a href="#/account">sign in</a> to check out.</div>`;
    return;
  }

  root.innerHTML = `<div class="loading">Loading…</div>`;
  const [cart, addresses, options] = await Promise.all([getCart(), listAddresses(), getCheckoutOptions()]);

  if (!cart.items.length) {
    root.innerHTML = `<div class="empty-state">Your cart is empty — <a href="#/browse">browse the catalog</a> first.</div>`;
    return;
  }
  if (!addresses.length) {
    root.innerHTML = `<div class="empty-state">Add a shipping address in your <a href="#/account">account</a> before checking out.</div>`;
    return;
  }

  const state = {
    addressId: addresses.find((a) => a.is_default)?.id ?? addresses[0].id,
    shippingMethod: Object.keys(options.shipping_methods)[0],
    paymentMethod: 'cod',
    prescriptionReference: '',
  };

  // Prescription-only items do not block the cart, but they do hold the
  // order: it is created in 'awaiting_prescription' and a pharmacist has to
  // review it before anything ships.
  const rxSection = cart.requires_prescription
    ? `
        <section class="checkout-section checkout-rx">
          <h2>Prescription required</h2>
          <p class="hint-text">
            These items are prescription-only (thuốc kê đơn):
            <strong>${cart.prescription_items.map(escapeHtml).join(', ')}</strong>.
            Enter the reference number from your prescription. A pharmacist reviews
            every order containing them before it ships — your order will be placed
            and held until that review is done.
          </p>
          <label>Prescription reference
            <input type="text" id="rx-reference" maxlength="200" placeholder="e.g. clinic document number" required />
          </label>
        </section>`
    : '';

  root.innerHTML = `
    <h1 class="page-title">Checkout</h1>
    <div class="checkout-layout">
      <div class="checkout-form">
        <section class="checkout-section">
          <h2>Shipping address</h2>
          <div class="radio-list">
            ${addresses
              .map(
                (a) => `
              <label class="radio-option">
                <input type="radio" name="address" value="${a.id}" ${a.id === state.addressId ? 'checked' : ''} />
                <span><strong>${escapeHtml(a.label)}</strong> — ${escapeHtml(a.recipient_name)}, ${escapeHtml(a.phone)}<br/>
                <span class="hint-text">${escapeHtml(a.line1)}, ${escapeHtml(a.city)}</span></span>
              </label>`
              )
              .join('')}
          </div>
        </section>

        <section class="checkout-section">
          <h2>Shipping method</h2>
          <div class="radio-list">
            ${Object.entries(options.shipping_methods)
              .map(
                ([key, m]) => `
              <label class="radio-option">
                <input type="radio" name="shipping" value="${key}" ${key === state.shippingMethod ? 'checked' : ''} />
                <span>${escapeHtml(m.label)} — ${m.fee > 0 ? formatVnd(m.fee) : 'Free'}</span>
              </label>`
              )
              .join('')}
          </div>
        </section>

        ${rxSection}

        <section class="checkout-section">
          <h2>Payment method</h2>
          <div class="radio-list">
            ${Object.entries(options.payment_methods)
              .map(
                ([key, m]) => `
              <label class="radio-option">
                <input type="radio" name="payment" value="${key}" ${key === state.paymentMethod ? 'checked' : ''} />
                <span>${escapeHtml(m.label)} ${!m.available ? '<span class="estimate-tag">not connected — demo only</span>' : ''}</span>
              </label>`
              )
              .join('')}
          </div>
          <p class="hint-text">Cash on delivery is the only payment method that actually completes an order right now. The others show what the flow would look like, but nothing is charged — there's no VNPay/Momo integration behind them.</p>
        </section>
      </div>

      <aside class="cart-summary">
        <h2>Order summary</h2>
        <div id="checkout-lines"></div>
        <div class="summary-row"><span>Subtotal</span><span>${formatVnd(cart.subtotal) || '0₫'}</span></div>
        ${cart.discount_code ? `<div class="summary-row summary-discount"><span>Discount (${escapeHtml(cart.discount_code)})</span><span>−${formatVnd(cart.discount_amount)}</span></div>` : ''}
        <div class="summary-row" id="shipping-fee-row"></div>
        <div class="summary-row summary-total" id="grand-total-row"></div>
        <div id="place-order-error" class="form-error"></div>
        <button type="button" id="place-order-btn">${cart.requires_prescription ? 'Place order for review' : 'Place order'}</button>
      </aside>
    </div>
  `;

  root.querySelector('#checkout-lines').innerHTML = cart.items
    .map((item) => `<div class="summary-row"><span>${escapeHtml(item.webName)} × ${item.quantity}</span><span>${formatVnd(item.line_total)}</span></div>`)
    .join('');

  function updateTotals() {
    const fee = options.shipping_methods[state.shippingMethod].fee;
    root.querySelector('#shipping-fee-row').innerHTML = `<span>Shipping</span><span>${fee > 0 ? formatVnd(fee) : 'Free'}</span>`;
    const total = cart.subtotal - cart.discount_amount + fee;
    root.querySelector('#grand-total-row').innerHTML = `<span>Total</span><span>${formatVnd(total)}</span>`;
  }
  updateTotals();

  root.querySelectorAll('input[name="address"]').forEach((r) => r.addEventListener('change', (e) => (state.addressId = parseInt(e.target.value, 10))));
  root.querySelectorAll('input[name="shipping"]').forEach((r) => r.addEventListener('change', (e) => { state.shippingMethod = e.target.value; updateTotals(); }));
  root.querySelectorAll('input[name="payment"]').forEach((r) => r.addEventListener('change', (e) => (state.paymentMethod = e.target.value)));
  root.querySelector('#rx-reference')?.addEventListener('input', (e) => (state.prescriptionReference = e.target.value.trim()));

  root.querySelector('#place-order-btn').addEventListener('click', async () => {
    const btn = root.querySelector('#place-order-btn');
    const errorEl = root.querySelector('#place-order-error');
    errorEl.textContent = '';
    btn.disabled = true;
    btn.textContent = 'Placing order…';
    try {
      const order = await placeOrder({
        addressId: state.addressId,
        shippingMethod: state.shippingMethod,
        paymentMethod: state.paymentMethod,
        prescriptionReference: state.prescriptionReference,
      });
      refreshNavBadges();
      navigate(`#/order/${order.id}`);
    } catch (err) {
      errorEl.textContent = err.message;
      btn.disabled = false;
      btn.textContent = 'Place order';
    }
  });
}
