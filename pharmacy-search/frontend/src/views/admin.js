import { getMe, getToken } from '../api.js';
import * as dashboardView from './admin/dashboard.js';
import * as productsView from './admin/products.js';
import * as ordersView from './admin/orders.js';
import * as usersView from './admin/users.js';
import * as couponsView from './admin/coupons.js';
import * as correctionsView from './admin/corrections.js';

const TABS = [
  { key: '', label: 'Dashboard', view: dashboardView },
  { key: 'products', label: 'Products', view: productsView },
  { key: 'orders', label: 'Orders', view: ordersView },
  { key: 'users', label: 'Users', view: usersView },
  { key: 'coupons', label: 'Coupons', view: couponsView },
  { key: 'corrections', label: 'Corrections', view: correctionsView },
];

export async function render(root, params = []) {
  if (!getToken()) {
    root.innerHTML = `<div class="empty-state">Please <a href="#/account">sign in</a>.</div>`;
    return;
  }

  let me;
  try {
    me = await getMe();
  } catch (err) {
    root.innerHTML = `<div class="empty-state">Please <a href="#/account">sign in</a>.</div>`;
    return;
  }
  if (!me.is_admin) {
    root.innerHTML = `<div class="empty-state">This account doesn't have admin access.</div>`;
    return;
  }

  const activeKey = params[0] || '';
  const activeTab = TABS.find((t) => t.key === activeKey) || TABS[0];

  root.innerHTML = `
    <h1 class="page-title">Admin</h1>
    <nav class="admin-tabs">
      ${TABS.map(
        (t) => `<a href="#/admin${t.key ? '/' + t.key : ''}" class="admin-tab ${t === activeTab ? 'active' : ''}">${t.label}</a>`
      ).join('')}
    </nav>
    <div id="admin-tab-content"></div>
  `;

  await activeTab.view.render(root.querySelector('#admin-tab-content'));
}
