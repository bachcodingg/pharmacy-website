import { getToken, getMe, getCart, getWishlist } from './api.js';
import { ICONS } from './shared.js';
import { t, getLocale, setLocale, LOCALES } from './i18n.js';
import { refreshCurrentRoute } from './router.js';

export function renderNav() {
  return `
    <nav class="main-nav" aria-label="${t('a11y.skipToContent')}">
      <a href="#/search" data-route="search">${t('nav.search')}</a>
      <a href="#/browse" data-route="browse">${t('nav.browse')}</a>
      <a href="#/wishlist" data-route="wishlist">${t('nav.wishlist')}<span class="nav-badge" id="nav-wishlist-badge" hidden>0</span></a>
      <a href="#/cart" data-route="cart">${t('nav.cart')}<span class="nav-badge" id="nav-cart-badge" hidden>0</span></a>
      <a href="#/admin" data-route="admin" id="nav-admin-link" hidden>${t('nav.admin')}</a>
      <a href="#/account" data-route="account" id="nav-account">${ICONS.user}<span id="nav-account-label">${t('nav.signIn')}</span></a>
      ${renderLocaleSwitch()}
    </nav>
  `;
}

/**
 * A two-option segmented control rather than a <select>: with exactly two
 * locales a dropdown costs two interactions to do what one tap should.
 */
function renderLocaleSwitch() {
  const current = getLocale();
  return `
    <div class="locale-switch" role="group" aria-label="${t('a11y.language')}">
      ${LOCALES.map((l) => `
        <button type="button" class="locale-btn${l.code === current ? ' active' : ''}"
                data-locale="${l.code}" lang="${l.code}"
                aria-pressed="${l.code === current}">${l.label}</button>`).join('')}
    </div>
  `;
}

export function bindLocaleSwitch(container) {
  container.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-locale]');
    if (!btn || btn.dataset.locale === getLocale()) return;
    setLocale(btn.dataset.locale);
    // The nav is part of the shell and not owned by the router, so it has to
    // be re-rendered by hand before the route redraws itself.
    const nav = container.querySelector('.main-nav');
    if (nav) nav.outerHTML = renderNav();
    const tagline = document.getElementById('tagline');
    if (tagline) tagline.textContent = t('brand.tagline');
    updateNavAuthState();
    refreshCurrentRoute();
  });
}

export async function updateNavAuthState() {
  const label = document.getElementById('nav-account-label');
  const adminLink = document.getElementById('nav-admin-link');
  if (!label) return;
  if (!getToken()) {
    label.textContent = t('nav.signIn');
    if (adminLink) adminLink.hidden = true;
    setBadge('nav-cart-badge', 0);
    setBadge('nav-wishlist-badge', 0);
    return;
  }
  try {
    const user = await getMe();
    label.textContent = user.name;
    if (adminLink) adminLink.hidden = !user.is_admin;
    await refreshNavBadges();
  } catch (err) {
    label.textContent = t('nav.signIn');
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
