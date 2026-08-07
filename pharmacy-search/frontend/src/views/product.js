import { getProduct, listReviews, createReview, getToken, addToCart, addToWishlist } from '../api.js';
import { escapeHtml, formatVnd, starRating } from '../shared.js';
import { navigate } from '../router.js';
import { refreshNavBadges } from '../nav.js';

export async function render(root, params) {
  const productId = params?.[0];
  if (!productId) {
    navigate('#/browse');
    return;
  }

  root.innerHTML = `<div class="loading">Loading…</div>`;

  let product;
  try {
    product = await getProduct(productId);
  } catch (err) {
    root.innerHTML = `<div class="empty-state">Product not found.</div>`;
    return;
  }
  const reviews = await listReviews(productId);

  root.innerHTML = `
    <a href="#/browse" class="back-link">← Back to browse</a>
    <div class="product-detail">
      <h1>${escapeHtml(product.webName)}</h1>
      <div class="product-detail-meta">
        <span class="sku-tag">SKU ${escapeHtml(product.sku)}</span>
        ${product.brand ? `<span class="catalog-brand">${escapeHtml(product.brand)}${product.brand_is_estimated ? ' (estimated)' : ''}</span>` : ''}
        ${product.category ? `<span class="product-category">${escapeHtml(product.category)}</span>` : ''}
        ${product.prescription ? '<span class="rx-tag">Prescription required</span>' : ''}
      </div>

      <div class="product-detail-rating">${starRating(product.rating_avg)} <span class="rating-count">(${product.rating_count} review${product.rating_count === 1 ? '' : 's'})</span></div>

      <div class="product-detail-price">
        ${product.price !== null ? formatVnd(product.price, product.price_unit) : 'Price unavailable'}
        ${product.price_is_estimated ? '<span class="estimate-tag">estimated placeholder price</span>' : ''}
      </div>
      <div class="product-detail-stock">${product.stock > 0 ? `${product.stock} in stock` : 'Out of stock'} ${product.stock_is_estimated ? '<span class="estimate-tag">estimated</span>' : ''}</div>

      <div class="product-detail-actions">
        <input type="number" id="add-qty" min="1" max="${Math.max(product.stock, 1)}" value="1" ${product.stock > 0 ? '' : 'disabled'} />
        <button type="button" id="add-to-cart-btn" ${product.stock > 0 ? '' : 'disabled'}>${product.stock > 0 ? 'Add to cart' : 'Out of stock'}</button>
        <button type="button" id="add-to-wishlist-btn" class="secondary-btn">Save to wishlist</button>
      </div>
      <div id="cart-action-note" class="form-note"></div>

      ${product.shortDescription ? `<p class="product-detail-desc">${escapeHtml(product.shortDescription)}</p>` : ''}

      ${product.ingredients?.length ? `
        <h3>Ingredients</h3>
        <ul class="ingredient-list">
          ${product.ingredients.map((i) => `<li>${escapeHtml(i.name)}${i.dose ? ` <span class="ingredient-dose">${escapeHtml(i.dose)}</span>` : ''}</li>`).join('')}
        </ul>` : ''}

      <h3>Reviews</h3>
      <div id="review-list" class="review-list"></div>
      <div id="review-form-slot"></div>
    </div>
  `;

  const reviewList = root.querySelector('#review-list');
  reviewList.innerHTML = reviews.length
    ? reviews.map((r) => `
      <div class="review">
        <div class="review-head">${starRating(r.rating)}<span class="review-author">${escapeHtml(r.user_name)}</span></div>
        ${r.comment ? `<p class="review-comment">${escapeHtml(r.comment)}</p>` : ''}
      </div>`).join('')
    : '<div class="empty-state">No reviews yet.</div>';

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
    cartNote.textContent = 'Added to cart.';
  });

  addToWishlistBtn.addEventListener('click', async () => {
    if (!getToken()) {
      navigate('#/account');
      return;
    }
    await addToWishlist(product.id);
    refreshNavBadges();
    cartNote.textContent = 'Saved to wishlist.';
  });

  const formSlot = root.querySelector('#review-form-slot');
  if (!getToken()) {
    formSlot.innerHTML = `<p class="hint-text"><a href="#/account">Sign in</a> to write a review.</p>`;
    return;
  }

  formSlot.innerHTML = `
    <form id="review-form" class="review-form">
      <label>Your rating
        <select name="rating" required>
          <option value="5">5 — Excellent</option>
          <option value="4">4 — Good</option>
          <option value="3">3 — Okay</option>
          <option value="2">2 — Poor</option>
          <option value="1">1 — Bad</option>
        </select>
      </label>
      <label>Comment (optional)
        <textarea name="comment" rows="3"></textarea>
      </label>
      <div id="review-form-error" class="form-error"></div>
      <button type="submit">Submit review</button>
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
