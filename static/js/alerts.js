/**
 * Alerts panel for Dremio Lakehouse Monitor.
 */

const Alerts = {
  init() {
    document.getElementById('add-rule-btn').addEventListener('click', () => this.showRuleModal());
    WS.on('alerts', (data) => this.onNewAlerts(data));
    this.refresh();
  },

  async refresh() {
    await Promise.all([this.loadRules(), this.loadHistory()]);
  },

  async loadRules() {
    try {
      const rules = await App.api('/api/alerts/rules');
      this.renderRules(rules || []);
    } catch (e) { console.warn('Failed to load rules:', e); }
  },

  async loadHistory() {
    try {
      const history = await App.api('/api/alerts/history');
      this.renderHistory(document.getElementById('alert-history'), history || []);
      this.renderHistory(document.getElementById('dashboard-alerts'), (history || []).slice(0, 5));
      // Update badge
      const unacked = (history || []).filter(a => !a.acknowledged).length;
      const badge = document.getElementById('alert-badge');
      if (unacked > 0) {
        badge.textContent = unacked;
        badge.style.display = 'inline';
      } else {
        badge.style.display = 'none';
      }
    } catch (e) { console.warn('Failed to load history:', e); }
  },

  renderRules(rules) {
    const container = document.getElementById('alert-rules-list');
    if (!rules.length) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🔔</div><div class="empty-state-text">No alert rules configured.<br>Click "+ Add Rule" to create one.</div></div>';
      return;
    }
    container.innerHTML = rules.map(r => {
      const icon = { query_duration: '⏱️', failed_jobs: '❌', reflection_failure: '💎',
                     memory_pressure: '🧠', source_down: '🔌', queue_depth: '📊' }[r.rule_type] || '🔔';
      return `<div class="card" style="margin-bottom:8px;padding:14px;display:flex;align-items:center;gap:16px">
        <span style="font-size:1.3rem">${icon}</span>
        <div style="flex:1">
          <div style="font-weight:600">${App.escapeHtml(r.name)}</div>
          <div style="font-size:0.8rem;color:var(--text-secondary)">${r.rule_type} · threshold: ${r.threshold_value}${r.threshold_unit ? ' ' + r.threshold_unit : ''} · cooldown: ${r.cooldown_minutes}m</div>
        </div>
        <span class="badge-status ${r.severity}">${r.severity}</span>
        <label class="toggle">
          <input type="checkbox" ${r.enabled ? 'checked' : ''} onchange="Alerts.toggleRule(${r.id}, this.checked)">
          <span class="toggle-slider"></span>
        </label>
        <button class="btn btn-danger btn-sm" onclick="Alerts.deleteRule(${r.id})">Delete</button>
      </div>`;
    }).join('');
  },

  renderHistory(container, history) {
    if (!container) return;
    if (!history.length) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-text">No alerts triggered</div></div>';
      return;
    }
    const severityIcon = { info: 'ℹ️', warning: '⚠️', critical: '🔴' };
    container.innerHTML = history.map(a => {
      const time = App.timeAgo(a.triggered_at);
      const ackBtn = a.acknowledged ? '' :
        `<button class="alert-ack-btn" onclick="Alerts.acknowledge(${a.id})">Acknowledge</button>`;
      return `<div class="alert-item ${a.severity}" ${a.acknowledged ? 'style="opacity:0.6"' : ''}>
        <span class="alert-icon">${severityIcon[a.severity] || '⚠️'}</span>
        <div class="alert-content">
          <div class="alert-message">${App.escapeHtml(a.message)}</div>
          <div class="alert-time">${time} · ${a.rule_type}</div>
        </div>
        ${ackBtn}
      </div>`;
    }).join('');
  },

  showRuleModal() {
    const types = [
      { value: 'query_duration', label: 'Query Duration (minutes)', unit: 'minutes', default: 5 },
      { value: 'failed_jobs', label: 'Failed Jobs Count', unit: 'count', default: 5 },
      { value: 'reflection_failure', label: 'Reflection Failures', unit: 'count', default: 1 },
      { value: 'memory_pressure', label: 'Memory Pressure (%)', unit: 'percent', default: 85 },
      { value: 'source_down', label: 'Source Down', unit: '', default: 1 },
      { value: 'queue_depth', label: 'Queue Depth', unit: 'count', default: 10 },
    ];
    App.showModal('Add Alert Rule', `
      <div class="form-group">
        <label class="form-label">Rule Name</label>
        <input class="form-input" id="rule-name" placeholder="e.g. Long running queries">
      </div>
      <div class="form-group">
        <label class="form-label">Rule Type</label>
        <select class="form-select" id="rule-type">
          ${types.map(t => `<option value="${t.value}">${t.label}</option>`).join('')}
        </select>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">Threshold</label>
          <input class="form-input" id="rule-threshold" type="number" value="5">
        </div>
        <div class="form-group">
          <label class="form-label">Severity</label>
          <select class="form-select" id="rule-severity">
            <option value="info">Info</option>
            <option value="warning" selected>Warning</option>
            <option value="critical">Critical</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">Cooldown (minutes)</label>
        <input class="form-input" id="rule-cooldown" type="number" value="15">
      </div>
      <div class="form-row">
        <div class="form-group"><label><input type="checkbox" id="rule-email"> Email notifications</label></div>
        <div class="form-group"><label><input type="checkbox" id="rule-webhook"> Webhook notifications</label></div>
      </div>
    `, [
      { text: 'Cancel', class: 'btn btn-secondary', action: () => App.closeModal() },
      { text: 'Create Rule', class: 'btn btn-primary', action: () => this.saveRule() },
    ]);
  },

  async saveRule() {
    const rule = {
      name: document.getElementById('rule-name').value || 'Unnamed Rule',
      rule_type: document.getElementById('rule-type').value,
      threshold_value: parseFloat(document.getElementById('rule-threshold').value) || 5,
      severity: document.getElementById('rule-severity').value,
      cooldown_minutes: parseInt(document.getElementById('rule-cooldown').value) || 15,
      notify_email: document.getElementById('rule-email').checked,
      notify_webhook: document.getElementById('rule-webhook').checked,
      enabled: true,
    };
    await App.api('/api/alerts/rules', 'POST', rule);
    App.closeModal();
    this.loadRules();
  },

  async toggleRule(id, enabled) {
    await App.api('/api/alerts/toggle', 'POST', { id, enabled });
  },

  async deleteRule(id) {
    if (confirm('Delete this alert rule?')) {
      await App.api(`/api/alerts/rules/${id}`, 'DELETE');
      this.loadRules();
    }
  },

  async acknowledge(id) {
    await App.api('/api/alerts/acknowledge', 'POST', { id });
    this.loadHistory();
  },

  onNewAlerts(alerts) {
    this.loadHistory();
  }
};
