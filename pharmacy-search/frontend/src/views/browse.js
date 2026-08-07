import { listProducts } from '../api.js';
import { escapeHtml, formatVnd, starRating } from '../shared.js';
import { navigate } from '../router.js';

const CATEGORIES = [
  { value: '', label: 'All categories' },
  { value: 'thuoc', label: 'Thuốc (medicine)' },
  { value: 'thuc-pham-chuc-nang', label: 'Thực phẩm chức năng (supplements)' },
  { value: 'duoc-my-pham', label: 'Dược mỹ phẩm (cosmeceuticals)' },
  { value: 'cham-soc-ca-nhan', label: 'Chăm sóc cá nhân (personal care)' },
  { value: 'trang-thiet-bi-y-te', label: 'Trang thiết bị y tế (medical devices)' },
];

export async function render(root, params) {
  const state = {
    q: '',
    category: '',
    page: parseInt(params?.[0], 10) || 1,
  };

  root.innerHTML = `
    <div class="browse-toolbar">
      <input id="browse-q" type="search" placeholder="Filter by name…" />
      <select id="browse-category">
        ${CATEGORIES.map((c) => `<option value="${c.value}">${escapeHtml(c.label)}</option>`).join('')}
      </select>
    </div>
    <div id="browse-grid" class="product-grid"></div>
    <div id="browse-pager" class="pager"></div>
  `;

  const grid = root.querySelector('#browse-grid');
  const pager = root.querySelector('#browse-pager');
  const qInput = root.querySelector('#browse-q');
  const categorySelect = root.querySelector('#browse-category');

  async function load() {
    grid.innerHTML = '<div class="loading">Loading…</div>';
    const data = await listProducts({ q: state.q, category: state.category, page: state.page, pageSize: 20 });
    renderGrid(data);
    renderPager(data);
  }

  function renderGrid(data) {
    if (!data.items.length) {
      grid.innerHTML = '<div class="empty-state">No products match this filter.</div>';
      return;
    }
    grid.innerHTML = data.items
      .map(
        (p) => `
      <a class="catalog-card" href="#/product/${p.id}">
        <div class="catalog-card-name">${escapeHtml(p.webName)}</div>
        <div class="catalog-card-meta">
          ${p.brand ? `<span class="catalog-brand">${escapeHtml(p.brand)}${p.brand_is_estimated ? ' *' : ''}</span>` : ''}
          ${p.category ? `<span class="product-category">${escapeHtml(p.category)}</span>` : ''}
        </div>
        <div class="catalog-card-rating">${starRating(p.rating_avg)}</div>
        <div class="catalog-card-price">
          ${p.price !== null ? formatVnd(p.price) : 'Price unavailable'}
          ${p.price_is_estimated ? '<span class="estimate-tag">estimated</span>' : ''}
        </div>
        <div class="catalog-card-stock">${p.stock > 0 ? `${p.stock} in stock` : 'Out of stock'}</div>
      </a>`
      )
      .join('');
  }

  function renderPager(data) {
    const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
    pager.innerHTML = `
      <button type="button" id="prev-page" ${data.page <= 1 ? 'disabled' : ''}>← Previous</button>
      <span class="pager-status">Page ${data.page} of ${totalPages} · ${data.total} products</span>
      <button type="button" id="next-page" ${data.page >= totalPages ? 'disabled' : ''}>Next →</button>
    `;
    pager.querySelector('#prev-page').addEventListener('click', () => {
      state.page -= 1;
      navigate(`#/browse/${state.page}`);
      load();
    });
    pager.querySelector('#next-page').addEventListener('click', () => {
      state.page += 1;
      navigate(`#/browse/${state.page}`);
      load();
    });
  }

  let debounce;
  qInput.addEventListener('input', () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.q = qInput.value.trim();
      state.page = 1;
      load();
    }, 200);
  });

  categorySelect.addEventListener('change', () => {
    state.category = categorySelect.value;
    state.page = 1;
    load();
  });

  await load();
}
