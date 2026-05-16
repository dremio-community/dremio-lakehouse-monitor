/**
 * Query explorer panel for Dremio Lakehouse Monitor.
 */

const Queries = {
  _filter: 'active',

  init() {
    document.querySelectorAll('#query-filters .filter-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#query-filters .filter-chip').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this._filter = btn.dataset.filter;
        this.refresh();
      });
    });
    WS.on('active_jobs', () => { if (this._filter === 'active') this.refresh(); });
    WS.on('recent_jobs', () => { if (this._filter !== 'active') this.refresh(); });
  },

  async refresh() {
    const tbody = document.getElementById('queries-body');
    try {
      let jobs;
      if (this._filter === 'active') {
        jobs = await App.api('/api/jobs/active');
      } else {
        jobs = await App.api('/api/jobs/recent');
        if (this._filter === 'failed') {
          jobs = (jobs || []).filter(j => j.status === 'FAILED');
        }
      }
      this.render(tbody, jobs || []);
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-state"><div class="empty-state-text">Failed to load queries</div></td></tr>';
    }
  },

  render(tbody, jobs) {
    if (!jobs.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-state"><div class="empty-state-text">No queries found</div></td></tr>';
      return;
    }
    tbody.innerHTML = jobs.map(j => {
      const dur = App.formatDuration(j.submitted_ts || j.attempt_started_ts);
      const statusClass = (j.status || '').toLowerCase();
      const accel = j.accelerated ? '⚡ Yes' : '—';
      const rows = j.rows_scanned ? parseInt(j.rows_scanned).toLocaleString() : '—';
      const jobId = (j.job_id || '').substring(0, 8);
      return `<tr>
        <td><code style="color:var(--accent)">${jobId}</code></td>
        <td>${j.user || '—'}</td>
        <td class="query-text" title="${App.escapeHtml(j.query || '')}">${App.escapeHtml((j.query || '').substring(0, 120))}</td>
        <td>${dur}</td>
        <td>${rows}</td>
        <td><span class="badge-status ${statusClass}">${j.status || '—'}</span></td>
        <td>${accel}</td>
      </tr>`;
    }).join('');
  }
};
