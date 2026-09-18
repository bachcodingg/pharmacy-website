import { getWishlist, removeFromWishlist, moveWishlistItemToCart, getToken } from '../api.js';
import { escapeHtml, formatVnd, productThumbHtml } from '../shared.js';
import { t } from '../i18n.js';
import { refreshNavBadges } from '../nav.js';

export async function render(root) {
  if (!getToken()) {
    root.innerHTML = `<div class="empty-state">${t('common.signInTo.wishlist')}</div>`;
    return;
  }

  root.innerHTML = `<div class="loading">${t('common.loading')}</div>`;
  const items = await getWishlist();
  renderList(root, items);
}

function renderList(root, items) {
  root.innerHTML = `
    <h1 class="page-title">${t('wishlist.title')}</h1>
    <div id="wishlist-items"></div>
  `;
  const container = root.querySelector('#wishlist-items');

  if (!items.length) {
    container.innerHTML = `<div class="empty-state">${t('wishlist.empty')}</div>`;
    return;
  }

  container.innerHTML = `<div class="product-grid">${items
    .map(
      (item) => `
    <div class="catalog-card wishlist-card">
      ${productThumbHtml(item.imageUrl, item.webName)}
      <a href="#/product/${item.product_id}" class="catalog-card-name">${escapeHtml(item.webName)}</a>
      <div class="catalog-card-price">
        ${item.price !== null ? formatVnd(item.price, item.price_unit) : t('common.priceUnavailable')}
        ${item.price_is_estimated ? `<span class="estimate-tag">${t('common.estimated')}</span>` : ''}
      </div>
      <div class="catalog-card-stock">${item.stock > 0 ? t('common.inStock', { n: item.stock }) : t('common.outOfStock')}</div>
      <div class="wishlist-actions">
        <button type="button" class="secondary-btn" data-move="${item.product_id}" ${item.stock > 0 ? '' : 'disabled'}>${t('common.moveToCart')}</button>
        <button type="button" class="link-btn" data-remove="${item.product_id}">${t('common.remove')}</button>
      </div>
    </div>`
    )
    .join('')}</div>`;

  container.querySelectorAll('[data-move]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const updated = await moveWishlistItemToCart(btn.dataset.move);
      refreshNavBadges();
      renderList(root, updated);
    });
  });

  container.querySelectorAll('[data-remove]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const updated = await removeFromWishlist(btn.dataset.remove);
      refreshNavBadges();
      renderList(root, updated);
    });
  });
}
