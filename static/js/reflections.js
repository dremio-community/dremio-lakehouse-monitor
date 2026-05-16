/**
 * Reflections health panel for Dremio Lakehouse Monitor.
 */

const Reflections = {
  init() {
    WS.on('reflections', () => this.refresh());
  },

  async refresh() {
    try {
      const data = await App.api('/api/reflections');
      this.render(data || []);
    } catch (e) {
      console.warn('Reflections refresh failed:', e);
    }
  },

  render(reflections) {
    const grid = document.getElementById('reflection-grid');
    const summary = document.getElementById('reflection-summary');

    if (!reflections.length) {
      grid.innerHTML = '<div class="empty-state"><div class="empty-state-icon">💎</div><div class="empty-state-text">No reflections found</div></div>';
      summary.innerHTML = '';
      return;
    }

    const active = reflections.filter(r => r.status === 'ACTIVE').length;
    const failed = reflections.filter(r => r.status === 'FAILED').length;
    const other = reflections.length - active - failed;

    summary.innerHTML = `
      <span class="filter-chip active" style="cursor:default">Total: ${reflections.length}</span>
      <span class="filter-chip" style="cursor:default;border-color:var(--green);color:var(--green)">Active: ${active}</span>
      ${failed ? `<span class="filter-chip" style="cursor:default;border-color:var(--red);color:var(--red)">Failed: ${failed}</span>` : ''}
      ${other ? `<span class="filter-chip" style="cursor:default">Other: ${other}</span>` : ''}`;

    grid.innerHTML = reflections.map(r => {
      const statusClass = (r.status || '').toLowerCase();
      const footprint = r.current_footprint_bytes
        ? App.formatBytes(parseInt(r.current_footprint_bytes))
        : '—';
      const failures = parseInt(r.num_failures) || 0;
      const errorMsg = r.last_failure_message
        ? `<div style="margin-top:8px;padding:8px;background:var(--red-bg);border-radius:6px;font-size:0.8rem;color:var(--red)">${App.escapeHtml(r.last_failure_message.substring(0, 150))}</div>`
        : '';

      return `<div class="reflection-card">
        <div class="reflection-card-header">
          <span class="reflection-name">${App.escapeHtml(r.reflection_name || r.reflection_id || 'Unknown')}</span>
          <span class="badge-status ${statusClass}">${r.status || '—'}</span>
        </div>
        <div style="font-size:0.8rem;color:var(--text-secondary)">
          ${r.type || ''} · ${App.escapeHtml(r.dataset_name || '')}
        </div>
        <div class="reflection-stats">
          <div class="reflection-stat">
            <div class="reflection-stat-value">${parseInt(r.considered_count) || 0}</div>
            <div class="reflection-stat-label">Considered</div>
          </div>
          <div class="reflection-stat">
            <div class="reflection-stat-value">${parseInt(r.matched_count) || 0}</div>
            <div class="reflection-stat-label">Matched</div>
          </div>
          <div class="reflection-stat">
            <div class="reflection-stat-value">${parseInt(r.accelerated_count) || 0}</div>
            <div class="reflection-stat-label">Accelerated</div>
          </div>
        </div>
        <div style="margin-top:8px;font-size:0.8rem;color:var(--text-muted)">
          Footprint: ${footprint} ${failures ? `· ${failures} failure(s)` : ''}
        </div>
        ${errorMsg}
      </div>`;
    }).join('');
  }
};
