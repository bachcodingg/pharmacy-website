const routes = {};
let currentCleanup = null;

export function registerRoute(name, renderFn) {
  routes[name] = renderFn;
}

export function navigate(hash) {
  window.location.hash = hash;
}

function parseHash() {
  const raw = window.location.hash.replace(/^#\/?/, '') || 'search';
  const [name, ...rest] = raw.split('/');
  return { name: name || 'search', params: rest };
}

async function renderCurrentRoute() {
  const root = document.getElementById('view-root');
  const { name, params } = parseHash();
  const render = routes[name] || routes.search;

  if (currentCleanup) {
    currentCleanup();
    currentCleanup = null;
  }

  root.innerHTML = '';
  const result = await render(root, params);
  if (typeof result === 'function') currentCleanup = result;

  document.querySelectorAll('.main-nav a').forEach((a) => {
    const active = a.dataset.route === name;
    a.classList.toggle('active', active);
    // The class is a colour; aria-current is what a screen reader announces.
    if (active) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
}

export function startRouter() {
  window.addEventListener('hashchange', renderCurrentRoute);
  renderCurrentRoute();
}

export function refreshCurrentRoute() {
  renderCurrentRoute();
}
