import './style.css';
import { ICONS } from './shared.js';
import { t, applyDocumentLang } from './i18n.js';
import { renderNav, updateNavAuthState, bindLocaleSwitch } from './nav.js';
import { registerRoute, startRouter } from './router.js';
import * as searchView from './views/search.js';
import * as browseView from './views/browse.js';
import * as productView from './views/product.js';
import * as accountView from './views/account.js';
import * as cartView from './views/cart.js';
import * as wishlistView from './views/wishlist.js';
import * as checkoutView from './views/checkout.js';
import * as orderView from './views/order.js';
import * as adminView from './views/admin.js';

// index.html ships lang="vi"; this reconciles it with what the visitor chose
// last time, before anything renders.
applyDocumentLang();

const app = document.getElementById('app');
app.innerHTML = `
  <a class="skip-link" href="#view-root">${t('a11y.skipToContent')}</a>
  <div class="page">
    <header class="topbar">
      <div class="topbar-row">
        <a class="brand" href="#/search"><span class="brand-mark">${ICONS.pill}</span>Pharmacy Search</a>
        ${renderNav()}
      </div>
      <p class="tagline" id="tagline">${t('brand.tagline')}</p>
    </header>
    <main id="view-root" tabindex="-1"></main>
  </div>
`;

registerRoute('search', searchView.render);
registerRoute('browse', browseView.render);
registerRoute('product', productView.render);
registerRoute('account', accountView.render);
registerRoute('cart', cartView.render);
registerRoute('wishlist', wishlistView.render);
registerRoute('checkout', checkoutView.render);
registerRoute('order', orderView.render);
registerRoute('admin', adminView.render);

bindLocaleSwitch(app);
updateNavAuthState();
startRouter();
