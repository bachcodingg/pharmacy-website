import { getWishlist, removeFromWishlist, moveWishlistItemToCart, getToken } from '../api.js';
import { escapeHtml, formatVnd } from '../shared.js';
import { refreshNavBadges } from '../nav.js';

export async function render(root) {
  if (!getToken()) {
    root.innerHTML = `<div class="empty-state">Please <a href="#/account">sign in</a> to view your wishlist.</div>`;
    return;
  }

  root.innerHTML = `<div class="loading">Loading…</div>`;
  const items = await getWishlist();
  renderList(root, items);
}

function renderList(root, items) {
  root.innerHTML = `
    <h1 class="page-title">Your wishlist</h1>
    <div id="wishlist-items"></div>
  `;
  const container = root.querySelector('#wishlist-items');

  if (!items.length) {
    container.innerHTML = `<div class="empty-state">Nothing saved yet — browse the <a href="#/browse">catalog</a> and save something for later.</div>`;
    return;
  }

  container.innerHTML = `<div class="product-grid">${items
    .map(
      (item) => `
    <div class="catalog-card wishlist-card">
      <a href="#/product/${item.product_id}" class="catalog-card-name">${escapeHtml(item.webName)}</a>
      <div class="catalog-card-price">
        ${item.price !== null ? formatVnd(item.price, item.price_unit) : 'Price unavailable'}
        ${item.price_is_estimated ? '<span class="estimate-tag">estimated</span>' : ''}
      </div>
      <div class="catalog-card-stock">${item.stock > 0 ? `${item.stock} in stock` : 'Out of stock'}</div>
      <div class="wishlist-actions">
        <button type="button" class="secondary-btn" data-move="${item.product_id}" ${item.stock > 0 ? '' : 'disabled'}>Move to cart</button>
        <button type="button" class="link-btn" data-remove="${item.product_id}">Remove</button>
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
