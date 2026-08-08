import { adminListOrders, adminUpdateOrderStatus } from '../../api.js';
import { escapeHtml, formatVnd } from '../../shared.js';

const STATUSES = ['placed', 'pending_payment', 'shipped', 'delivered', 'cancelled'];

export async function render(root) {
  const state = { status: '' };

  root.innerHTML = `
    <div class="admin-toolbar">
      <select id="status-filter">
        <option value="">All statuses</option>
        ${STATUSES.map((s) => `<option value="${s}">${escapeHtml(s)}</option>`).join('')}
      </select>
    </div>
    <div id="orders-table"></div>
  `;

  const table = root.querySelector('#orders-table');

  async function load() {
    table.innerHTML = '<div class="loading">Loading…</div>';
    const orders = await adminListOrders({ status: state.status });
    renderTable(orders);
  }

  function renderTable(orders) {
    if (!orders.length) {
      table.innerHTML = '<div class="empty-state">No orders match.</div>';
      return;
    }
    table.innerHTML = `
      <table class="admin-product-table">
        <thead><tr><th>Order</th><th>Customer</th><th>Items</th><th>Total</th><th>Status</th></tr></thead>
        <tbody>
          ${orders
            .map(
              (o) => `
            <tr>
              <td><a href="#/order/${o.id}">#${o.id}</a></td>
              <td>${escapeHtml(o.customer_name)}<br/><span class="hint-text">${escapeHtml(o.customer_email)}</span></td>
              <td>${o.items.length}</td>
              <td>${formatVnd(o.total)}</td>
              <td>
                <select class="status-select" data-order-id="${o.id}">
                  ${STATUSES.map((s) => `<option value="${s}" ${s === o.status ? 'selected' : ''}>${escapeHtml(s)}</option>`).join('')}
                </select>
              </td>
            </tr>`
            )
            .join('')}
        </tbody>
      </table>
    `;

    table.querySelectorAll('.status-select').forEach((select) => {
      select.addEventListener('change', async () => {
        await adminUpdateOrderStatus(select.dataset.orderId, select.value);
        load();
      });
    });
  }

  root.querySelector('#status-filter').addEventListener('change', (e) => {
    state.status = e.target.value;
    load();
  });

  await load();
}
