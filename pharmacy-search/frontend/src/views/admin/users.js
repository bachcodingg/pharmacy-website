import { adminListUsers, adminSetUserAdmin, getMe } from '../../api.js';
import { escapeHtml } from '../../shared.js';

export async function render(root) {
  const me = await getMe();

  root.innerHTML = `<div id="users-table"><div class="loading">Loading…</div></div>`;
  const table = root.querySelector('#users-table');

  async function load() {
    const users = await adminListUsers();
    renderTable(users);
  }

  function renderTable(users) {
    table.innerHTML = `
      <table class="admin-product-table">
        <thead><tr><th>Name</th><th>Email</th><th>Orders</th><th>Admin</th><th></th></tr></thead>
        <tbody>
          ${users
            .map(
              (u) => `
            <tr>
              <td>${escapeHtml(u.name)}</td>
              <td>${escapeHtml(u.email)}</td>
              <td>${u.order_count}</td>
              <td>${u.is_admin ? 'Yes' : 'No'}</td>
              <td>
                ${u.id === me.id
                  ? '<span class="hint-text">You</span>'
                  : u.is_admin
                    ? `<button type="button" class="link-btn" data-demote="${u.id}">Remove admin</button>`
                    : `<button type="button" class="link-btn" data-promote="${u.id}">Make admin</button>`}
              </td>
            </tr>`
            )
            .join('')}
        </tbody>
      </table>
    `;

    table.querySelectorAll('[data-promote]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await adminSetUserAdmin(btn.dataset.promote, true);
        load();
      });
    });
    table.querySelectorAll('[data-demote]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await adminSetUserAdmin(btn.dataset.demote, false);
        load();
      });
    });
  }

  await load();
}
