import { search, suggest, logClick } from '../api.js';
import { ICONS, escapeHtml, productThumbHtml } from '../shared.js';

const PRESETS = [
  { label: 'etrogen', hint: 'typo → auto-correct' },
  { label: 'amoxycillin', hint: 'phonetic spelling' },
  { label: 'paracetamol 500mg', hint: 'dose is protected' },
  { label: 'vitamind', hint: 'ambiguous → did you mean' },
  { label: 'qqzzxx', hint: 'no results' },
];

export function render(root) {
  root.innerHTML = `
    <div class="search-card">
      <div class="search-box">
        <span class="search-icon">${ICONS.search}</span>
        <input id="query" placeholder="Search a product or ingredient…" autocomplete="off" spellcheck="false" />
        <span class="spinner" id="spinner" hidden></span>
      </div>
      <div id="autocomplete" class="autocomplete-dropdown" hidden></div>
      <div class="presets" id="presets"></div>
    </div>

    <div id="notice"></div>
    <div id="results"></div>

    <details class="debug-panel">
      <summary>Debug details</summary>
      <div id="debug"></div>
    </details>
  `;

  root.querySelector('#presets').innerHTML = PRESETS.map(
    (p) => `<button type="button" class="preset" data-q="${p.label}"><span class="preset-label">${p.label}</span><span class="preset-hint">${p.hint}</span></button>`
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
          Showing results for <strong>${escapeHtml(result.suggestion)}</strong>
          <button type="button" class="link-btn" data-literal="${original}">search for "${original}" instead</button>
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
          <div class="notice-title">Did you mean one of these?</div>
          <div class="candidate-list">${buttons}</div>
        </span>
      `;
      return;
    }

    if (result.decision === 'no_results') {
      notice.className = 'notice notice-none';
      notice.innerHTML = `
        <span class="notice-icon">${ICONS.x}</span>
        <span class="notice-body">No results for <strong>${original}</strong> — this query was logged for review.</span>
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
        (p) => `<li class="product-card" data-query="${escapeHtml(result.query)}" data-product="${escapeHtml(p.webName)}" tabindex="0" role="button">
          ${productThumbHtml(p.imageUrl, p.webName)}
          <span class="product-name">${escapeHtml(p.webName)}</span>
          ${p.category ? `<span class="product-category">${escapeHtml(p.category)}</span>` : ''}
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
        <thead><tr><th>token</th><th>status</th><th>candidates</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="debug-meta">decision=<strong>${result.decision}</strong> · latency=${result.latency_ms}ms</div>
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

    const productCard = event.target.closest('.product-card');
    if (productCard) {
      logClick(productCard.dataset.query, productCard.dataset.product);
      productCard.classList.add('product-card-clicked');
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
