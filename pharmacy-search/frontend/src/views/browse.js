import { listProducts, getFacets, addToCart, getToken } from '../api.js';
import { escapeHtml, formatVnd, starRating, productThumbHtml } from '../shared.js';
import { navigate } from '../router.js';
import { refreshNavBadges } from '../nav.js';

const CATEGORIES = [
  { value: '', label: 'All categories' },
  { value: 'thuoc', label: 'Thuốc (medicine)' },
  { value: 'thuc-pham-chuc-nang', label: 'Thực phẩm chức năng (supplements)' },
  { value: 'duoc-my-pham', label: 'Dược mỹ phẩm (cosmeceuticals)' },
  { value: 'cham-soc-ca-nhan', label: 'Chăm sóc cá nhân (personal care)' },
  { value: 'trang-thiet-bi-y-te', label: 'Trang thiết bị y tế (medical devices)' },
];

const SORT_OPTIONS = [
  { value: 'name', label: 'Alphabetical' },
  { value: 'price_asc', label: 'Price: low to high' },
  { value: 'price_desc', label: 'Price: high to low' },
  { value: 'newest', label: 'Newest' },
  { value: 'top_rated', label: 'Top rated' },
  { value: 'best_selling', label: 'Best selling' },
];

export async function render(root, params) {
  const state = {
    q: '',
    category: '',
    brand: '',
    minPrice: '',
    maxPrice: '',
    minRating: '',
    inStock: false,
    sort: 'name',
    page: parseInt(params?.[0], 10) || 1,
  };

  root.innerHTML = `
    <div class="browse-layout">
      <aside class="filter-panel">
        <div class="filter-group">
          <label class="filter-label">Category</label>
          <select id="f-category">
            ${CATEGORIES.map((c) => `<option value="${c.value}">${escapeHtml(c.label)}</option>`).join('')}
          </select>
        </div>
        <div class="filter-group">
          <label class="filter-label">Brand</label>
          <select id="f-brand"><option value="">All brands</option></select>
        </div>
        <div class="filter-group">
          <label class="filter-label">Price range (₫)</label>
          <div class="filter-range">
            <input id="f-min-price" type="number" min="0" placeholder="Min" />
            <span>–</span>
            <input id="f-max-price" type="number" min="0" placeholder="Max" />
          </div>
        </div>
        <div class="filter-group">
          <label class="filter-label">Minimum rating</label>
          <select id="f-min-rating">
            <option value="">Any rating</option>
            <option value="4">4★ &amp; up</option>
            <option value="3">3★ &amp; up</option>
            <option value="2">2★ &amp; up</option>
            <option value="1">1★ &amp; up</option>
          </select>
        </div>
        <div class="filter-group">
          <label class="checkbox-label"><input id="f-in-stock" type="checkbox" /> In stock only</label>
        </div>
        <button type="button" id="f-clear" class="secondary-btn">Clear filters</button>
      </aside>

      <div class="browse-main">
        <div class="browse-toolbar">
          <input id="browse-q" type="search" placeholder="Filter by name…" />
          <select id="browse-sort">
            ${SORT_OPTIONS.map((s) => `<option value="${s.value}">${escapeHtml(s.label)}</option>`).join('')}
          </select>
        </div>
        <div id="browse-notice"></div>
        <div id="browse-grid" class="product-grid"></div>
        <div id="browse-pager" class="pager"></div>
      </div>
    </div>
  `;

  const grid = root.querySelector('#browse-grid');
  const browseNotice = root.querySelector('#browse-notice');
  const pager = root.querySelector('#browse-pager');
  const qInput = root.querySelector('#browse-q');
  const sortSelect = root.querySelector('#browse-sort');
  const categorySelect = root.querySelector('#f-category');
  const brandSelect = root.querySelector('#f-brand');
  const minPriceInput = root.querySelector('#f-min-price');
  const maxPriceInput = root.querySelector('#f-max-price');
  const minRatingSelect = root.querySelector('#f-min-rating');
  const inStockCheckbox = root.querySelector('#f-in-stock');

  async function loadFacets() {
    const facets = await getFacets({ q: state.q, category: state.category });
    const currentBrand = brandSelect.value;
    brandSelect.innerHTML = '<option value="">All brands</option>' +
      facets.brands.map((b) => `<option value="${escapeHtml(b)}">${escapeHtml(b)}</option>`).join('');
    if (facets.brands.includes(currentBrand)) brandSelect.value = currentBrand;
  }

  async function load() {
    grid.innerHTML = '<div class="loading">Loading…</div>';
    const data = await listProducts({
      q: state.q,
      category: state.category,
      brand: state.brand,
      minPrice: state.minPrice,
      maxPrice: state.maxPrice,
      minRating: state.minRating,
      inStock: state.inStock,
      sort: state.sort,
      page: state.page,
      pageSize: 20,
    });
    renderNotice(data);
    renderGrid(data);
    renderPager(data);
  }

  function renderNotice(data) {
    if (!data.corrected_to) {
      browseNotice.innerHTML = '';
      return;
    }
    browseNotice.innerHTML = `<div class="browse-correction">Showing results for <strong>${escapeHtml(
      data.corrected_to
    )}</strong></div>`;
  }

  function renderGrid(data) {
    if (!data.items.length) {
      grid.innerHTML = '<div class="empty-state">No products match this filter.</div>';
      return;
    }
    grid.innerHTML = data.items
      .map(
        (p) => `
      <div class="catalog-card">
        <a href="#/product/${p.id}" class="catalog-card-link">
          ${productThumbHtml(p.imageUrl, p.webName)}
          <div class="catalog-card-name">${escapeHtml(p.webName)}</div>
          <div class="catalog-card-meta">
            ${p.brand ? `<span class="catalog-brand">${escapeHtml(p.brand)}${p.brand_is_estimated ? ' *' : ''}</span>` : ''}
            ${p.category ? `<span class="product-category">${escapeHtml(p.category)}</span>` : ''}
            ${p.prescription ? '<span class="rx-tag">Rx</span>' : ''}
          </div>
          <div class="catalog-card-rating">${starRating(p.rating_avg)}</div>
          <div class="catalog-card-price">
            ${p.price !== null ? formatVnd(p.price, p.price_unit) : 'Price unavailable'}
            ${p.price_is_estimated ? '<span class="estimate-tag">estimated</span>' : ''}
          </div>
          <div class="catalog-card-stock">${p.stock > 0 ? `${p.stock} in stock` : 'Out of stock'}</div>
        </a>
        <button type="button" class="quick-add-btn" data-quick-add="${p.id}" ${p.stock > 0 ? '' : 'disabled'}>
          ${p.stock > 0 ? '+ Add to cart' : 'Out of stock'}
        </button>
      </div>`
      )
      .join('');

    grid.querySelectorAll('[data-quick-add]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        if (!getToken()) {
          navigate('#/account');
          return;
        }
        btn.disabled = true;
        btn.textContent = 'Added ✓';
        await addToCart(parseInt(btn.dataset.quickAdd, 10), 1);
        refreshNavBadges();
        setTimeout(() => {
          btn.disabled = false;
          btn.textContent = '+ Add to cart';
        }, 1200);
      });
    });
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
      loadFacets();
      load();
    }, 200);
  });

  sortSelect.addEventListener('change', () => {
    state.sort = sortSelect.value;
    state.page = 1;
    load();
  });

  categorySelect.addEventListener('change', () => {
    state.category = categorySelect.value;
    state.page = 1;
    loadFacets();
    load();
  });

  brandSelect.addEventListener('change', () => {
    state.brand = brandSelect.value;
    state.page = 1;
    load();
  });

  let priceDebounce;
  function onPriceChange() {
    clearTimeout(priceDebounce);
    priceDebounce = setTimeout(() => {
      state.minPrice = minPriceInput.value;
      state.maxPrice = maxPriceInput.value;
      state.page = 1;
      load();
    }, 300);
  }
  minPriceInput.addEventListener('input', onPriceChange);
  maxPriceInput.addEventListener('input', onPriceChange);

  minRatingSelect.addEventListener('change', () => {
    state.minRating = minRatingSelect.value;
    state.page = 1;
    load();
  });

  inStockCheckbox.addEventListener('change', () => {
    state.inStock = inStockCheckbox.checked;
    state.page = 1;
    load();
  });

  root.querySelector('#f-clear').addEventListener('click', () => {
    state.category = '';
    state.brand = '';
    state.minPrice = '';
    state.maxPrice = '';
    state.minRating = '';
    state.inStock = false;
    state.page = 1;
    categorySelect.value = '';
    brandSelect.value = '';
    minPriceInput.value = '';
    maxPriceInput.value = '';
    minRatingSelect.value = '';
    inStockCheckbox.checked = false;
    loadFacets();
    load();
  });

  await loadFacets();
  await load();
}
