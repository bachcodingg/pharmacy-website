import './style.css';
import { search, suggest } from './api.js';

const PRESETS = [
  { label: 'etrogen', hint: 'typo → auto-correct' },
  { label: 'amoxycillin', hint: 'phonetic spelling' },
  { label: 'paracetamol 500mg', hint: 'dose is protected' },
  { label: 'vitamind', hint: 'ambiguous → did you mean' },
  { label: 'qqzzxx', hint: 'no results' },
];

const ICONS = {
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
  help: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/><circle cx="12" cy="12" r="9"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  pill: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.5 20.5 3.5 13.5a5 5 0 0 1 7-7l7 7a5 5 0 0 1-7 7Z"/><line x1="8.5" y1="8.5" x2="15.5" y2="15.5"/></svg>',
};

const app = document.getElementById('app');
app.innerHTML = `
  <div class="page">
    <header class="topbar">
      <div class="brand"><span class="brand-mark">${ICONS.pill}</span>Pharmacy Search</div>
      <p class="tagline">Typo-tolerant product search — precision over recall, always.</p>
    </header>

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
  </div>
`;

document.getElementById('presets').innerHTML = PRESETS.map(
  (p) => `<button type="button" class="preset" data-q="${p.label}"><span class="preset-label">${p.label}</span><span class="preset-hint">${p.hint}</span></button>`
).join('');

const queryInput = document.getElementById('query');
const notice = document.getElementById('notice');
const results = document.getElementById('results');
const autocomplete = document.getElementById('autocomplete');
const debug = document.getElementById('debug');
const spinner = document.getElementById('spinner');
const searchCard = document.querySelector('.search-card');

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

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
      (p) => `<li class="product-card">
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
    if (requestId !== currentRequest) return; // a newer request already landed
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

document.addEventListener('click', (event) => {
  if (!searchCard.contains(event.target)) {
    autocomplete.hidden = true;
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
});
