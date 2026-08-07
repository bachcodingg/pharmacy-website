import {
  getMe, adminListProducts, adminCreateProduct, adminUpdateStock,
  adminDeactivateProduct, adminReactivateProduct, getToken,
} from '../api.js';
import { escapeHtml, formatVnd } from '../shared.js';

export async function render(root) {
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

  const state = { lowStockOnly: false, includeInactive: false };

  root.innerHTML = `
    <h1 class="page-title">Inventory</h1>
    <div class="admin-toolbar">
      <label class="checkbox-label"><input type="checkbox" id="a-low-stock" /> Low stock only (≤ 10)</label>
      <label class="checkbox-label"><input type="checkbox" id="a-include-inactive" /> Include deactivated</label>
    </div>

    <details class="debug-panel admin-add-panel">
      <summary>Add a new product</summary>
      <form id="add-product-form" class="auth-form">
        <label>Name <input type="text" name="webName" required /></label>
        <label>Category
          <select name="category">
            <option value="thuoc">Thuốc</option>
            <option value="thuc-pham-chuc-nang">Thực phẩm chức năng</option>
            <option value="duoc-my-pham">Dược mỹ phẩm</option>
            <option value="cham-soc-ca-nhan">Chăm sóc cá nhân</option>
            <option value="trang-thiet-bi-y-te">Trang thiết bị y tế</option>
          </select>
        </label>
        <label>Brand <input type="text" name="brand" /></label>
        <label>Price (₫) <input type="number" name="price" min="0" required /></label>
        <label>Stock <input type="number" name="stock" min="0" value="0" required /></label>
        <div id="add-product-error" class="form-error"></div>
        <button type="submit">Add product</button>
      </form>
    </details>

    <div id="admin-table"></div>
  `;

  const table = root.querySelector('#admin-table');

  async function load() {
    table.innerHTML = '<div class="loading">Loading…</div>';
    const products = await adminListProducts({
      lowStockThreshold: state.lowStockOnly ? 10 : undefined,
      includeInactive: state.includeInactive,
    });
    renderTable(products);
  }

  function renderTable(products) {
    if (!products.length) {
      table.innerHTML = '<div class="empty-state">No products match.</div>';
      return;
    }
    table.innerHTML = `
      <table class="admin-product-table">
        <thead><tr><th>Product</th><th>SKU</th><th>Price</th><th>Stock</th><th>Status</th><th></th></tr></thead>
        <tbody>
          ${products
            .map(
              (p) => `
            <tr class="${p.stock <= 10 ? 'low-stock-row' : ''} ${!p.is_active ? 'inactive-row' : ''}">
              <td>${escapeHtml(p.webName)}</td>
              <td><code>${escapeHtml(p.sku)}</code></td>
              <td>${formatVnd(p.price)}</td>
              <td><input type="number" class="stock-input" min="0" value="${p.stock}" data-product-id="${p.id}" /></td>
              <td>${p.is_active ? 'Active' : 'Deactivated'}</td>
              <td>${p.is_active
                ? `<button type="button" class="link-btn" data-deactivate="${p.id}">Deactivate</button>`
                : `<button type="button" class="link-btn" data-reactivate="${p.id}">Reactivate</button>`}
              </td>
            </tr>`
            )
            .join('')}
        </tbody>
      </table>
    `;

    table.querySelectorAll('.stock-input').forEach((input) => {
      input.addEventListener('change', async () => {
        await adminUpdateStock(input.dataset.productId, Math.max(0, parseInt(input.value, 10) || 0));
        load();
      });
    });
    table.querySelectorAll('[data-deactivate]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await adminDeactivateProduct(btn.dataset.deactivate);
        load();
      });
    });
    table.querySelectorAll('[data-reactivate]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await adminReactivateProduct(btn.dataset.reactivate);
        load();
      });
    });
  }

  root.querySelector('#a-low-stock').addEventListener('change', (e) => {
    state.lowStockOnly = e.target.checked;
    load();
  });
  root.querySelector('#a-include-inactive').addEventListener('change', (e) => {
    state.includeInactive = e.target.checked;
    load();
  });

  root.querySelector('#add-product-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(event.target);
    const errorEl = root.querySelector('#add-product-error');
    errorEl.textContent = '';
    try {
      await adminCreateProduct({
        webName: data.get('webName'),
        category: data.get('category'),
        brand: data.get('brand') || null,
        price: parseInt(data.get('price'), 10),
        stock: parseInt(data.get('stock'), 10),
      });
      event.target.reset();
      load();
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });

  await load();
}
