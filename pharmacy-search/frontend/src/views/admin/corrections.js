import { adminListCorrections, adminApproveCorrection, adminRejectCorrection } from '../../api.js';
import { escapeHtml } from '../../shared.js';

export async function render(root) {
  root.innerHTML = `
    <p class="hint-text">
      Pharmacist approval gate for learned typo pairs. Nothing here reaches the live
      search index until it's approved and <code>build/build_nearmiss.py</code> is re-run.
    </p>
    <div id="corrections-list"></div>
  `;

  const list = root.querySelector('#corrections-list');

  async function load() {
    list.innerHTML = '<div class="loading">Loading…</div>';
    const candidates = await adminListCorrections();
    renderList(candidates);
  }

  function renderList(candidates) {
    const pending = candidates.filter((c) => c.status === 'pending' && c.meets_threshold);
    const decided = candidates.filter((c) => c.status !== 'pending' || !c.meets_threshold);

    if (!candidates.length) {
      list.innerHTML = '<div class="empty-state">No candidate pairs yet.</div>';
      return;
    }

    list.innerHTML = `
      <h3>Awaiting review (${pending.length})</h3>
      ${
        pending.length
          ? `<table class="admin-product-table">
              <thead><tr><th>From</th><th>To</th><th>Occurrences</th><th>Sessions</th><th></th></tr></thead>
              <tbody>
                ${pending
                  .map(
                    (c) => `
                  <tr>
                    <td>${escapeHtml(c.from_query)}</td>
                    <td>${escapeHtml(c.to_query)}</td>
                    <td>${c.occurrences}</td>
                    <td>${c.distinct_sessions}</td>
                    <td>
                      <button type="button" class="link-btn" data-approve="${escapeHtml(c.from_query)}|${escapeHtml(c.to_query)}">Approve</button>
                      <button type="button" class="link-btn" data-reject="${escapeHtml(c.from_query)}|${escapeHtml(c.to_query)}">Reject</button>
                    </td>
                  </tr>`
                  )
                  .join('')}
              </tbody>
            </table>`
          : '<div class="empty-state">Nothing awaiting review.</div>'
      }

      ${
        decided.length
          ? `<h3>Other candidates</h3>
            <table class="admin-product-table">
              <thead><tr><th>From</th><th>To</th><th>Occurrences</th><th>Sessions</th><th>Status</th></tr></thead>
              <tbody>
                ${decided
                  .map(
                    (c) => `
                  <tr class="${c.status !== 'pending' ? 'inactive-row' : ''}">
                    <td>${escapeHtml(c.from_query)}</td>
                    <td>${escapeHtml(c.to_query)}</td>
                    <td>${c.occurrences}</td>
                    <td>${c.distinct_sessions}</td>
                    <td>${escapeHtml(c.status)}${!c.meets_threshold && c.status === 'pending' ? ' (below threshold)' : ''}</td>
                  </tr>`
                  )
                  .join('')}
              </tbody>
            </table>`
          : ''
      }
    `;

    list.querySelectorAll('[data-approve]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const [fromQuery, toQuery] = btn.dataset.approve.split('|');
        await adminApproveCorrection(fromQuery, toQuery);
        load();
      });
    });
    list.querySelectorAll('[data-reject]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const [fromQuery, toQuery] = btn.dataset.reject.split('|');
        await adminRejectCorrection(fromQuery, toQuery);
        load();
      });
    });
  }

  await load();
}
