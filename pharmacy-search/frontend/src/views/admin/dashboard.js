import { adminGetSummary, adminGetSalesByDay, adminGetTopProducts } from '../../api.js';
import { escapeHtml, formatVnd } from '../../shared.js';

export async function render(root) {
  root.innerHTML = `
    <div id="stat-tiles" class="stat-tile-grid"></div>
    <div class="admin-panel">
      <h3>Revenue, last 14 days</h3>
      <div id="sales-chart"></div>
    </div>
    <div class="admin-panel">
      <h3>Top products</h3>
      <div id="top-products"></div>
    </div>
  `;

  const [summary, sales, topProducts] = await Promise.all([
    adminGetSummary(),
    adminGetSalesByDay(14),
    adminGetTopProducts(10),
  ]);

  renderTiles(summary);
  renderChart(sales);
  renderTopProducts(topProducts);

  function renderTiles(s) {
    const tiles = [
      { label: 'Revenue', value: formatVnd(s.revenue) },
      { label: 'Orders', value: s.order_count },
      { label: 'Avg. order value', value: formatVnd(s.avg_order_value) },
      { label: 'Customers', value: s.customer_count },
      { label: 'Registered users', value: s.user_count },
      { label: 'Low stock products', value: s.low_stock_count, warn: s.low_stock_count > 0 },
      { label: 'Pending payment orders', value: s.pending_payment_count, warn: s.pending_payment_count > 0 },
      { label: 'Corrections awaiting review', value: s.pending_corrections_count, warn: s.pending_corrections_count > 0 },
    ];
    root.querySelector('#stat-tiles').innerHTML = tiles
      .map(
        (t) => `
      <div class="stat-tile ${t.warn ? 'stat-tile-warn' : ''}">
        <div class="stat-tile-value">${t.value}</div>
        <div class="stat-tile-label">${escapeHtml(t.label)}</div>
      </div>`
      )
      .join('');
  }

  function renderChart(days) {
    const container = root.querySelector('#sales-chart');
    if (!days.some((d) => d.revenue > 0)) {
      container.innerHTML = '<div class="empty-state">No revenue yet in this period.</div>';
      return;
    }

    const width = 640;
    const height = 200;
    const padding = { top: 8, right: 8, bottom: 24, left: 8 };
    const plotW = width - padding.left - padding.right;
    const plotH = height - padding.top - padding.bottom;
    const barGap = 4;
    const barW = plotW / days.length - barGap;
    const maxRevenue = Math.max(...days.map((d) => d.revenue), 1);

    const bars = days
      .map((d, i) => {
        const barH = Math.max((d.revenue / maxRevenue) * plotH, d.revenue > 0 ? 3 : 0);
        const x = padding.left + i * (barW + barGap);
        const y = padding.top + plotH - barH;
        const dateLabel = new Date(d.date + 'T00:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        return `<rect class="chart-bar" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${barH.toFixed(1)}" rx="4" ry="4"
          data-date="${escapeHtml(dateLabel)}" data-revenue="${escapeHtml(formatVnd(d.revenue))}"></rect>`;
      })
      .join('');

    const baselineY = padding.top + plotH;

    container.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" class="sales-chart-svg" preserveAspectRatio="none">
        <line x1="${padding.left}" y1="${baselineY}" x2="${width - padding.right}" y2="${baselineY}" class="chart-baseline" />
        ${bars}
      </svg>
      <div class="chart-tooltip" hidden></div>
    `;

    const tooltip = container.querySelector('.chart-tooltip');
    container.querySelectorAll('.chart-bar').forEach((bar) => {
      bar.addEventListener('mouseenter', () => {
        tooltip.textContent = `${bar.dataset.date}: ${bar.dataset.revenue}`;
        tooltip.hidden = false;
      });
      bar.addEventListener('mousemove', (e) => {
        const rect = container.getBoundingClientRect();
        tooltip.style.left = `${e.clientX - rect.left + 12}px`;
        tooltip.style.top = `${e.clientY - rect.top - 8}px`;
      });
      bar.addEventListener('mouseleave', () => {
        tooltip.hidden = true;
      });
    });
  }

  function renderTopProducts(products) {
    const container = root.querySelector('#top-products');
    if (!products.length) {
      container.innerHTML = '<div class="empty-state">No sales yet.</div>';
      return;
    }
    container.innerHTML = `
      <table class="admin-product-table">
        <thead><tr><th>Product</th><th>Units sold</th><th>Revenue</th></tr></thead>
        <tbody>
          ${products
            .map(
              (p) => `
            <tr>
              <td>${escapeHtml(p.webName)}</td>
              <td>${p.units_sold}</td>
              <td>${formatVnd(p.revenue)}</td>
            </tr>`
            )
            .join('')}
        </tbody>
      </table>
    `;
  }
}
