import { adminListOrders, adminUpdateOrderStatus, reviewPrescription } from '../../api.js';
import { escapeHtml, formatVnd } from '../../shared.js';

const STATUSES = ['placed', 'pending_payment', 'awaiting_prescription', 'shipped', 'delivered', 'cancelled'];

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

  function prescriptionCell(order) {
    if (!order.requires_prescription) return '<span class="hint-text">—</span>';
    if (order.prescription_status !== 'pending_review') {
      return `<span class="status-pill status-${escapeHtml(order.prescription_status)}">${escapeHtml(order.prescription_status)}</span>`;
    }
    // The gate itself: an Rx order cannot leave 'awaiting_prescription' by any
    // other route, so these two buttons are the only way it ships.
    return `
      <div class="rx-review">
        ${order.prescription_reference ? `<div class="hint-text">Ref: ${escapeHtml(order.prescription_reference)}</div>` : ''}
        <button type="button" class="link-btn" data-rx-approve="${order.id}">Approve</button>
        <button type="button" class="link-btn" data-rx-reject="${order.id}">Reject</button>
      </div>`;
  }

  function renderTable(orders) {
    if (!orders.length) {
      table.innerHTML = '<div class="empty-state">No orders match.</div>';
      return;
    }
    table.innerHTML = `
      <table class="admin-product-table">
        <thead><tr><th>Order</th><th>Customer</th><th>Items</th><th>Total</th><th>Status</th><th>Prescription</th></tr></thead>
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
              <td>${prescriptionCell(o)}</td>
            </tr>`
            )
            .join('')}
        </tbody>
      </table>
    `;

    table.querySelectorAll('.status-select').forEach((select) => {
      select.addEventListener('change', async () => {
        try {
          await adminUpdateOrderStatus(select.dataset.orderId, select.value);
        } catch (err) {
          // The lifecycle refuses illegal moves now (a held Rx order cannot
          // jump straight to shipped), so show why instead of failing silently.
          window.alert(err.message);
        }
        load();
      });
    });

    table.querySelectorAll('[data-rx-approve], [data-rx-reject]').forEach((button) => {
      button.addEventListener('click', async () => {
        const approve = button.hasAttribute('data-rx-approve');
        const orderId = button.getAttribute(approve ? 'data-rx-approve' : 'data-rx-reject');
        const note = window.prompt(
          approve ? 'Note for the approval record (optional):' : 'Reason for rejection (optional):'
        );
        if (note === null) return;
        try {
          await reviewPrescription(orderId, approve ? 'approve' : 'reject', note);
        } catch (err) {
          window.alert(err.message);
        }
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
