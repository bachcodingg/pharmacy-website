import { getToken, getMe } from './api.js';
import { ICONS } from './shared.js';

export function renderNav() {
  return `
    <nav class="main-nav">
      <a href="#/search" data-route="search">Search</a>
      <a href="#/browse" data-route="browse">Browse</a>
      <a href="#/account" data-route="account" id="nav-account">${ICONS.user}<span id="nav-account-label">Sign in</span></a>
    </nav>
  `;
}

export async function updateNavAuthState() {
  const label = document.getElementById('nav-account-label');
  if (!label) return;
  if (!getToken()) {
    label.textContent = 'Sign in';
    return;
  }
  try {
    const user = await getMe();
    label.textContent = user.name;
  } catch (err) {
    label.textContent = 'Sign in';
  }
}
