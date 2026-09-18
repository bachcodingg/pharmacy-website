import { getProduct, listReviews, createReview, getToken, listOrders, addToCart, addToWishlist } from '../api.js';
import { escapeHtml, formatVnd, starRating, productThumbHtml } from '../shared.js';
import { t } from '../i18n.js';
import { navigate } from '../router.js';
import { refreshNavBadges } from '../nav.js';

export async function render(root, params) {
  const productId = params?.[0];
  if (!productId) {
    navigate('#/browse');
    return;
  }

  root.innerHTML = `<div class="loading">${t('common.loading')}</div>`;

  let product;
  try {
    product = await getProduct(productId);
  } catch (err) {
    root.innerHTML = `<div class="empty-state">${t('product.notFound')}</div>`;
    return;
  }
  const reviews = await listReviews(productId);

  root.innerHTML = `
    <a href="#/browse" class="back-link">${t('product.backToBrowse')}</a>
    <div class="product-detail">
      ${productThumbHtml(product.imageUrl, product.webName, 'product-thumb-hero')}
      <h1>${escapeHtml(product.webName)}</h1>
      <div class="product-detail-meta">
        <span class="sku-tag">${t('product.sku', { sku: escapeHtml(product.sku) })}</span>
        ${product.brand ? `<span class="catalog-brand">${escapeHtml(product.brand)}${product.brand_is_estimated ? ` ${t('product.brandEstimated')}` : ''}</span>` : ''}
        ${product.category ? `<span class="product-category">${escapeHtml(product.category)}</span>` : ''}
        ${product.prescription ? `<span class="rx-tag">${t('product.rxRequired')}</span>` : ''}
      </div>

      <div class="product-detail-rating">${starRating(product.rating_avg)} <span class="rating-count">${t('product.reviewCount', { n: product.rating_count })}</span></div>

      <div class="product-detail-price">
        ${product.price !== null ? formatVnd(product.price, product.price_unit) : t('common.priceUnavailable')}
        ${product.price_is_estimated ? `<span class="estimate-tag">${t('product.estimatedPrice')}</span>` : ''}
      </div>
      <div class="product-detail-stock">${product.stock > 0 ? t('common.inStock', { n: product.stock }) : t('common.outOfStock')} ${product.stock_is_estimated ? `<span class="estimate-tag">${t('common.estimated')}</span>` : ''}</div>

      <div class="product-detail-actions">
        <input type="number" id="add-qty" min="1" max="${Math.max(product.stock, 1)}" value="1" aria-label="${t('cart.qty', { n: '' })}" ${product.stock > 0 ? '' : 'disabled'} />
        <button type="button" id="add-to-cart-btn" ${product.stock > 0 ? '' : 'disabled'}>${product.stock > 0 ? t('product.addToCart') : t('common.outOfStock')}</button>
        <button type="button" id="add-to-wishlist-btn" class="secondary-btn">${t('product.saveToWishlist')}</button>
      </div>
      <div id="cart-action-note" class="form-note" role="status" aria-live="polite"></div>

      ${product.shortDescription ? `<p class="product-detail-desc">${escapeHtml(product.shortDescription)}</p>` : ''}

      ${product.ingredients?.length ? `
        <h3>${t('product.ingredients')}</h3>
        <ul class="ingredient-list">
          ${product.ingredients.map((i) => `<li>${escapeHtml(i.name)}${i.dose ? ` <span class="ingredient-dose">${escapeHtml(i.dose)}</span>` : ''}</li>`).join('')}
        </ul>` : ''}

      <h3>${t('product.reviews')}</h3>
      <div id="review-list" class="review-list"></div>
      <div id="review-form-slot"></div>
    </div>
  `;

  const reviewList = root.querySelector('#review-list');
  reviewList.innerHTML = reviews.length
    ? reviews.map((r) => `
      <div class="review">
        <div class="review-head">${starRating(r.rating)}<span class="review-author">${escapeHtml(r.user_name)}</span>${r.verified_purchase ? `<span class="estimate-tag">${t('product.verifiedPurchase')}</span>` : ''}</div>
        ${r.comment ? `<p class="review-comment">${escapeHtml(r.comment)}</p>` : ''}
      </div>`).join('')
    : `<div class="empty-state">${t('product.noReviews')}</div>`;

  const addToCartBtn = root.querySelector('#add-to-cart-btn');
  const addToWishlistBtn = root.querySelector('#add-to-wishlist-btn');
  const cartNote = root.querySelector('#cart-action-note');

  addToCartBtn.addEventListener('click', async () => {
    if (!getToken()) {
      navigate('#/account');
      return;
    }
    const qty = Math.max(1, parseInt(root.querySelector('#add-qty').value, 10) || 1);
    await addToCart(product.id, qty);
    refreshNavBadges();
    cartNote.textContent = t('product.addedToCart');
  });

  addToWishlistBtn.addEventListener('click', async () => {
    if (!getToken()) {
      navigate('#/account');
      return;
    }
    await addToWishlist(product.id);
    refreshNavBadges();
    cartNote.textContent = t('product.savedToWishlist');
  });

  const formSlot = root.querySelector('#review-form-slot');
  if (!getToken()) {
    formSlot.innerHTML = `<p class="hint-text">${t('product.signInToReview')}</p>`;
    return;
  }

  // Reviews are restricted to buyers, so say that here instead of offering a
  // form whose only possible outcome is a 403. The server is still the
  // authority - if this lookup fails we show the form and let it answer.
  let hasOrdered = true;
  try {
    const orders = await listOrders();
    hasOrdered = orders.some(
      (order) => order.status !== 'cancelled'
        && order.items.some((item) => item.product_id === product.id),
    );
  } catch (err) {
    hasOrdered = true;
  }
  if (!hasOrdered) {
    formSlot.innerHTML = `<p class="hint-text">${t('product.buyersOnly')}</p>`;
    return;
  }

  formSlot.innerHTML = `
    <form id="review-form" class="review-form">
      <label>${t('product.yourRating')}
        <select name="rating" required>
          ${[5, 4, 3, 2, 1].map((n) => `<option value="${n}">${t(`product.rating.${n}`)}</option>`).join('')}
        </select>
      </label>
      <label>${t('product.comment')}
        <textarea name="comment" rows="3"></textarea>
      </label>
      <div id="review-form-error" class="form-error" role="alert"></div>
      <button type="submit">${t('product.submitReview')}</button>
    </form>
  `;

  formSlot.querySelector('#review-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = new FormData(event.target);
    const errorEl = formSlot.querySelector('#review-form-error');
    errorEl.textContent = '';
    try {
      await createReview(productId, parseInt(formData.get('rating'), 10), formData.get('comment') || null);
      render(root, params);
    } catch (err) {
      errorEl.textContent = err.message;
    }
  });
}
