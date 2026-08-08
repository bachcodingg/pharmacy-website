import { adminListCoupons, adminCreateCoupon, adminSetCouponActive } from '../../api.js';
import { escapeHtml } from '../../shared.js';

export async function render(root) {
  root.innerHTML = `
    <details class="debug-panel admin-add-panel" open>
      <summary>Create a coupon</summary>
      <form id="add-coupon-form" class="auth-form">
        <label>Code <input type="text" name="code" required /></label>
        <label>Kind
          <select name="kind">
            <option value="percent">Percent off</option>
            <option value="fixed">Fixed amount off (₫)</option>
          </select>
        </label>
        <label>Value <input type="number" name="value" min="1" required /></label>
        <div id="add-coupon-error" class="form-error"></div>
        <button type="submit">Create coupon</button>
      </form>
    </details>

    <div id="coupons-table"></div>
  `;

  const table = root.querySelector('#coupons-table');

  async function load() {
    table.innerHTML = '<div class="loading">Loading…</div>';
    const coupons = await adminListCoupons();
    renderTable(coupons);
  }

  function renderTable(coupons) {
    if (!coupons.length) {
      table.innerHTML = '<div class="empty-state">No coupons yet.</div>';
      return;
    }
    table.innerHTML = `
      <table class="admin-product-table">
        <thead><tr><th>Code</th><th>Discount</th><th>Status</th><th></th></tr></thead>
        <tbody>
          ${coupons
            .map(
              (c) => `
            <tr class="${!c.active ? 'inactive-row' : ''}">
              <td><code>${escapeHtml(c.code)}</code></td>
              <td>${c.kind === 'percent' ? `${c.value}%` : `${c.value.toLocaleString('vi-VN')}₫`} off</td>
              <td>${c.active ? 'Active' : 'Deactivated'}</td>
              <td>${c.active
                ? `<button type="button" class="link-btn" data-deactivate="${c.code}">Deactivate</button>`
                : `<button type="button" class="link-btn" data-activate="${c.code}">Activate</button>`}
              </td>
            </tr>`
            )
            .join('')}
        </tbody>
      </table>
    `;

    table.querySelectorAll('[data-deactivate]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await adminSetCouponActive(btn.dataset.deactivate, false);
        load();
      });
    });
    table.querySelectorAll('[data-activate]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await adminSetCouponActive(btn.dataset.activate, true);
        load();
      });
    });
  }

  root.querySelector('#add-coupon-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(event.target);
    const errorEl = root.querySelector('#add-coupon-error');
    errorEl.textContent = '';
    try {
      await adminCreateCoupon({
        code: data.get('code'),
        kind: data.get('kind'),
        value: parseInt(data.get('value'), 10),
      });
      event.target.reset();
      load();
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });

  await load();
}
