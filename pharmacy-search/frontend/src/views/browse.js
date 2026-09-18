import { listProducts, getFacets, addToCart, getToken } from '../api.js';
import { escapeHtml, formatVnd, starRating, productThumbHtml } from '../shared.js';
import { t } from '../i18n.js';
import { navigate } from '../router.js';
import { refreshNavBadges } from '../nav.js';

// Values are the API's category slugs and never change with the locale; only
// the label does. In English the Vietnamese name is kept in parentheses,
// because it is what is printed on the box the customer is holding.
const CATEGORIES = [
  { value: '', key: 'browse.allCategories' },
  { value: 'thuoc', key: 'browse.cat.thuoc' },
  { value: 'thuc-pham-chuc-nang', key: 'browse.cat.supplements' },
  { value: 'duoc-my-pham', key: 'browse.cat.cosmeceuticals' },
  { value: 'cham-soc-ca-nhan', key: 'browse.cat.personalCare' },
  { value: 'trang-thiet-bi-y-te', key: 'browse.cat.devices' },
];

const SORT_OPTIONS = ['name', 'price_asc', 'price_desc', 'newest', 'top_rated', 'best_selling'];

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
          <label class="filter-label" for="f-category">${t('browse.category')}</label>
          <select id="f-category">
            ${CATEGORIES.map((c) => `<option value="${c.value}">${escapeHtml(t(c.key))}</option>`).join('')}
          </select>
        </div>
        <div class="filter-group">
          <label class="filter-label" for="f-brand">${t('browse.brand')}</label>
          <select id="f-brand"><option value="">${t('browse.allBrands')}</option></select>
        </div>
        <div class="filter-group">
          <label class="filter-label" for="f-min-price">${t('browse.priceRange')}</label>
          <div class="filter-range">
            <input id="f-min-price" type="number" min="0" placeholder="${t('browse.min')}" aria-label="${t('browse.min')}" />
            <span>–</span>
            <input id="f-max-price" type="number" min="0" placeholder="${t('browse.max')}" aria-label="${t('browse.max')}" />
          </div>
        </div>
        <div class="filter-group">
          <label class="filter-label" for="f-min-rating">${t('browse.minRating')}</label>
          <select id="f-min-rating">
            <option value="">${t('browse.anyRating')}</option>
            ${[4, 3, 2, 1].map((n) => `<option value="${n}">${t('browse.ratingAndUp', { n })}</option>`).join('')}
          </select>
        </div>
        <div class="filter-group">
          <label class="checkbox-label"><input id="f-in-stock" type="checkbox" /> ${t('browse.inStockOnly')}</label>
        </div>
        <button type="button" id="f-clear" class="secondary-btn">${t('browse.clearFilters')}</button>
      </aside>

      <div class="browse-main">
        <div class="browse-toolbar">
          <input id="browse-q" type="search" placeholder="${t('browse.filterByName')}" aria-label="${t('browse.filterByName')}" />
          <select id="browse-sort" aria-label="${t('browse.sort.name')}">
            ${SORT_OPTIONS.map((s) => `<option value="${s}">${escapeHtml(t(`browse.sort.${s}`))}</option>`).join('')}
          </select>
        </div>
        <div id="browse-notice" role="status" aria-live="polite"></div>
        <div id="browse-grid" class="product-grid" aria-busy="false"></div>
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
    brandSelect.innerHTML = `<option value="">${t('browse.allBrands')}</option>` +
      facets.brands.map((b) => `<option value="${escapeHtml(b)}">${escapeHtml(b)}</option>`).join('');
    if (facets.brands.includes(currentBrand)) brandSelect.value = currentBrand;
  }

  async function load() {
    grid.setAttribute('aria-busy', 'true');
    grid.innerHTML = `<div class="loading">${t('common.loading')}</div>`;
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
    grid.setAttribute('aria-busy', 'false');
  }

  function renderNotice(data) {
    if (!data.corrected_to) {
      browseNotice.innerHTML = '';
      return;
    }
    browseNotice.innerHTML = `<div class="browse-correction">${t('search.showingResultsFor')} <strong>${escapeHtml(
      data.corrected_to
    )}</strong></div>`;
  }

  function renderGrid(data) {
    if (!data.items.length) {
      grid.innerHTML = `<div class="empty-state">${t('browse.empty')}</div>`;
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
            ${p.prescription ? `<span class="rx-tag">${t('common.rxShort')}</span>` : ''}
          </div>
          <div class="catalog-card-rating">${starRating(p.rating_avg)}</div>
          <div class="catalog-card-price">
            ${p.price !== null ? formatVnd(p.price, p.price_unit) : t('common.priceUnavailable')}
            ${p.price_is_estimated ? `<span class="estimate-tag">${t('common.estimated')}</span>` : ''}
          </div>
          <div class="catalog-card-stock">${p.stock > 0 ? t('common.inStock', { n: p.stock }) : t('common.outOfStock')}</div>
        </a>
        <button type="button" class="quick-add-btn" data-quick-add="${p.id}" ${p.stock > 0 ? '' : 'disabled'}>
          ${p.stock > 0 ? t('browse.quickAdd') : t('common.outOfStock')}
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
        btn.textContent = t('browse.quickAdded');
        await addToCart(parseInt(btn.dataset.quickAdd, 10), 1);
        refreshNavBadges();
        setTimeout(() => {
          btn.disabled = false;
          btn.textContent = t('browse.quickAdd');
        }, 1200);
      });
    });
  }

  function renderPager(data) {
    const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
    pager.innerHTML = `
      <button type="button" id="prev-page" ${data.page <= 1 ? 'disabled' : ''}>${t('browse.prev')}</button>
      <span class="pager-status">${t('browse.pagerStatus', { page: data.page, total: totalPages, count: data.total })}</span>
      <button type="button" id="next-page" ${data.page >= totalPages ? 'disabled' : ''}>${t('browse.next')}</button>
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
