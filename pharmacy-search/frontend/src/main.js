import './style.css';
import { ICONS } from './shared.js';
import { renderNav, updateNavAuthState } from './nav.js';
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

const app = document.getElementById('app');
app.innerHTML = `
  <div class="page">
    <header class="topbar">
      <div class="topbar-row">
        <div class="brand"><span class="brand-mark">${ICONS.pill}</span>Pharmacy Search</div>
        ${renderNav()}
      </div>
      <p class="tagline">Typo-tolerant product search — precision over recall, always.</p>
    </header>
    <main id="view-root"></main>
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

updateNavAuthState();
startRouter();
