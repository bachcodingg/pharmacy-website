import { getToken, getMe, getCart, getWishlist } from './api.js';
import { ICONS } from './shared.js';

export function renderNav() {
  return `
    <nav class="main-nav">
      <a href="#/search" data-route="search">Search</a>
      <a href="#/browse" data-route="browse">Browse</a>
      <a href="#/wishlist" data-route="wishlist">Wishlist<span class="nav-badge" id="nav-wishlist-badge" hidden>0</span></a>
      <a href="#/cart" data-route="cart">Cart<span class="nav-badge" id="nav-cart-badge" hidden>0</span></a>
      <a href="#/account" data-route="account" id="nav-account">${ICONS.user}<span id="nav-account-label">Sign in</span></a>
    </nav>
  `;
}

export async function updateNavAuthState() {
  const label = document.getElementById('nav-account-label');
  if (!label) return;
  if (!getToken()) {
    label.textContent = 'Sign in';
    setBadge('nav-cart-badge', 0);
    setBadge('nav-wishlist-badge', 0);
    return;
  }
  try {
    const user = await getMe();
    label.textContent = user.name;
    await refreshNavBadges();
  } catch (err) {
    label.textContent = 'Sign in';
  }
}

export async function refreshNavBadges() {
  if (!getToken()) return;
  try {
    const [cart, wishlist] = await Promise.all([getCart(), getWishlist()]);
    setBadge('nav-cart-badge', cart.items.reduce((sum, item) => sum + item.quantity, 0));
    setBadge('nav-wishlist-badge', wishlist.length);
  } catch (err) {
    // not signed in or a transient error - leave badges as-is
  }
}

function setBadge(id, count) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = String(count);
  el.hidden = count === 0;
}
