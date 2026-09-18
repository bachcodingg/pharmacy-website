import { search, suggest, logClick } from '../api.js';
import { ICONS, escapeHtml, formatVnd, productThumbHtml } from '../shared.js';
import { t } from '../i18n.js';

// The labels are literal queries and stay untranslated - they are what the
// user would type. Only the explanation of what each one demonstrates moves.
const PRESETS = [
  { label: 'etrogen', hint: 'search.preset.typo' },
  { label: 'amoxycillin', hint: 'search.preset.phonetic' },
  { label: 'paracetamol 500mg', hint: 'search.preset.dose' },
  { label: 'vitamind', hint: 'search.preset.ambiguous' },
  { label: 'qqzzxx', hint: 'search.preset.none' },
];

export function render(root) {
  root.innerHTML = `
    <div class="search-card">
      <div class="search-box">
        <span class="search-icon">${ICONS.search}</span>
        <input id="query" placeholder="${t('search.placeholder')}" aria-label="${t('search.placeholder')}" autocomplete="off" spellcheck="false" />
        <span class="spinner" id="spinner" hidden></span>
      </div>
      <div id="autocomplete" class="autocomplete-dropdown" hidden></div>
      <div class="presets" id="presets"></div>
    </div>

    <div id="notice" role="status" aria-live="polite"></div>
    <div id="results"></div>

    <details class="debug-panel">
      <summary>${t('search.debugTitle')}</summary>
      <div id="debug"></div>
    </details>
  `;

  root.querySelector('#presets').innerHTML = PRESETS.map(
    (p) => `<button type="button" class="preset" data-q="${p.label}"><span class="preset-label">${p.label}</span><span class="preset-hint">${t(p.hint)}</span></button>`
  ).join('');

  const queryInput = root.querySelector('#query');
  const notice = root.querySelector('#notice');
  const results = root.querySelector('#results');
  const autocomplete = root.querySelector('#autocomplete');
  const debug = root.querySelector('#debug');
  const spinner = root.querySelector('#spinner');
  const searchCard = root.querySelector('.search-card');

  function renderNotice(result) {
    const original = escapeHtml(result.query);

    if (result.decision === 'auto_correct') {
      notice.className = 'notice notice-auto';
      notice.innerHTML = `
        <span class="notice-icon">${ICONS.check}</span>
        <span class="notice-body">
          ${t('search.showingResultsFor')} <strong>${escapeHtml(result.suggestion)}</strong>
          <button type="button" class="link-btn" data-literal="${original}">${t('search.searchLiterally', { q: original })}</button>
        </span>
      `;
      return;
    }

    if (result.decision === 'did_you_mean') {
      notice.className = 'notice notice-dym';
      const buttons = (result.candidates || [])
        .map(
          (c) => `
          <button type="button" class="candidate" data-q="${escapeHtml(c.keyword)}">
            <span class="candidate-keyword">${escapeHtml(c.keyword)}</span>
            ${c.sample ? `<span class="candidate-sample">${escapeHtml(c.sample)}</span>` : ''}
          </button>`
        )
        .join('');
      notice.innerHTML = `
        <span class="notice-icon">${ICONS.help}</span>
        <span class="notice-body">
          <div class="notice-title">${t('search.didYouMean')}</div>
          <div class="candidate-list">${buttons}</div>
        </span>
      `;
      return;
    }

    if (result.decision === 'no_results') {
      notice.className = 'notice notice-none';
      notice.innerHTML = `
        <span class="notice-icon">${ICONS.x}</span>
        <span class="notice-body">${t('search.noResults', { q: original })}</span>
      `;
      return;
    }

    notice.className = 'notice notice-ok';
    notice.innerHTML = '';
  }

  function renderResults(result) {
    const products = result.products || [];
    if (!products.length) {
      results.innerHTML = '';
      return;
    }
    results.innerHTML = `<ul class="products">${products
      .map(
        // Results now come from the product table rather than a snapshot of
        // it, so each one has an id and a price and can be opened, instead of
        // being a dead end that only logged a click.
        (p) => `<li class="product-card">
          <a class="product-link" href="#/product/${p.id}" data-query="${escapeHtml(result.query)}" data-product="${escapeHtml(p.webName)}" data-product-id="${p.id}">
            ${productThumbHtml(p.imageUrl, p.webName)}
            <span class="product-name">${escapeHtml(p.webName)}</span>
            ${p.category ? `<span class="product-category">${escapeHtml(p.category)}</span>` : ''}
            <span class="product-price">${p.price != null ? formatVnd(p.price) : ''}${p.price_is_estimated ? ` <span class="estimate-tag">${t('common.estimated')}</span>` : ''}</span>
            ${p.prescription ? `<span class="rx-tag">${t('common.rxOnly')}</span>` : ''}
          </a>
        </li>`
      )
      .join('')}</ul>`;
  }

  function statusBadge(status) {
    return `<span class="status-pill status-${status}">${status}</span>`;
  }

  function renderDebug(result) {
    const rows = (result.tokens || [])
      .map((t) => {
        const candidates = (t.candidates || [])
          .map((c) => `<div class="debug-candidate">${escapeHtml(c.keyword)} <span class="debug-meta-inline">score=${c.score} · rule=${c.rule}</span></div>`)
          .join('');
        return `<tr><td><code>${escapeHtml(t.token)}</code></td><td>${statusBadge(t.status)}</td><td>${candidates || '—'}</td></tr>`;
      })
      .join('');
    debug.innerHTML = `
      <table>
        <thead><tr><th>${t('search.debug.token')}</th><th>${t('search.debug.status')}</th><th>${t('search.debug.candidates')}</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="debug-meta">${t('search.debug.summary', { decision: result.decision, latency: result.latency_ms })}</div>
    `;
  }

  let currentRequest = 0;

  async function runSearch(value) {
    autocomplete.hidden = true;
    if (!value) {
      notice.innerHTML = '';
      notice.className = 'notice';
      results.innerHTML = '';
      debug.innerHTML = '';
      return;
    }
    const requestId = ++currentRequest;
    spinner.hidden = false;
    try {
      const [result, suggestionResult] = await Promise.all([search(value), suggest(value)]);
      if (requestId !== currentRequest) return;
      renderNotice(result);
      renderResults(result);
      renderDebug(result);
      renderAutocomplete(suggestionResult.suggestions, value);
    } finally {
      if (requestId === currentRequest) spinner.hidden = true;
    }
  }

  function renderAutocomplete(suggestions, currentValue) {
    const items = (suggestions || []).filter((s) => s.keyword !== currentValue).slice(0, 6);
    if (!items.length) {
      autocomplete.hidden = true;
      autocomplete.innerHTML = '';
      return;
    }
    autocomplete.innerHTML = items
      .map((item) => `<button type="button" class="ac-item" data-q="${escapeHtml(item.keyword)}">${escapeHtml(item.keyword)}</button>`)
      .join('');
    autocomplete.hidden = false;
  }

  let timeout;
  queryInput.addEventListener('input', () => {
    clearTimeout(timeout);
    const value = queryInput.value.trim();
    timeout = setTimeout(() => runSearch(value), 150);
  });

  queryInput.addEventListener('focus', () => {
    if (autocomplete.innerHTML) autocomplete.hidden = false;
  });

  function onDocumentClick(event) {
    if (!searchCard.contains(event.target)) {
      autocomplete.hidden = true;
    }

    const productLink = event.target.closest('.product-link');
    if (productLink) {
      // Logged, then the href is allowed to navigate - the click log is what
      // feeds the learning loop, so it still has to fire.
      logClick(productLink.dataset.query, productLink.dataset.product);
      productLink.closest('.product-card')?.classList.add('product-card-clicked');
      return;
    }

    const target = event.target.closest('button');
    if (!target) return;

    if (target.classList.contains('preset') || target.classList.contains('candidate') || target.classList.contains('ac-item')) {
      const q = target.dataset.q;
      queryInput.value = q;
      runSearch(q);
      return;
    }

    if (target.dataset.literal) {
      search(target.dataset.literal, { literal: true }).then((result) => {
        renderNotice(result);
        renderResults(result);
        renderDebug(result);
      });
    }
  }
  document.addEventListener('click', onDocumentClick);

  return () => document.removeEventListener('click', onDocumentClick);
}
