/**
 * Main app controller for Dremio Lakehouse Monitor.
 */

const App = {
  _currentPanel: 'dashboard',
  _refreshInterval: null,

  async init() {
    // Tab navigation
    document.querySelectorAll('.nav-tab').forEach(tab => {
      tab.addEventListener('click', () => this.switchPanel(tab.dataset.panel));
    });

    // Modal close
    document.getElementById('modal-close').addEventListener('click', () => this.closeModal());
    document.getElementById('modal-overlay').addEventListener('click', (e) => {
      if (e.target === e.currentTarget) this.closeModal();
    });

    // WebSocket
    WS.on('connection', (data) => {
      const dot = document.getElementById('connection-dot');
      const label = document.getElementById('connection-label');
      if (data.connected) {
        dot.className = 'status-dot connected';
        label.textContent = 'WebSocket Connected';
      } else {
        dot.className = 'status-dot connecting';
        label.textContent = 'Reconnecting...';
      }
    });
    WS.connect();

    // Check connection
    const status = await this.api('/api/status').catch(() => null);
    if (!status || !status.connected) {
      this.showSetup();
    } else {
      this.hideSetup();
      this.updateConnectionStatus(true);
    }

    // Init panels
    Dashboard.init();
    Queries.init();
    Reflections.init();
    Alerts.init();
    this.initSettings();

    // Periodic refresh
    this._refreshInterval = setInterval(() => {
      if (this._currentPanel === 'dashboard') Dashboard.refresh();
      document.getElementById('last-updated').textContent =
        'Updated ' + new Date().toLocaleTimeString();
    }, 10000);
  },

  _setupMode: false,

  switchPanel(name) {
    if (this._setupMode) return; // Don't switch tabs during setup
    this._currentPanel = name;
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    const panel = document.getElementById('panel-' + name);
    if (panel) panel.classList.add('active');
    const tab = document.querySelector(`.nav-tab[data-panel="${name}"]`);
    if (tab) tab.classList.add('active');

    // Refresh panel data
    if (name === 'dashboard') Dashboard.refresh();
    else if (name === 'queries') Queries.refresh();
    else if (name === 'reflections') Reflections.refresh();
    else if (name === 'alerts') Alerts.refresh();
  },

  showSetup() {
    this._setupMode = true;
    document.getElementById('setup-screen').style.display = 'block';
    document.getElementById('nav-tabs').style.display = 'none';
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    const form = document.getElementById('setup-form');
    form.innerHTML = this._connectionFormHTML('setup');
    form.querySelector('#setup-connect-btn').addEventListener('click', () => this.saveConnection(form, 'setup'));
  },

  hideSetup() {
    this._setupMode = false;
    document.getElementById('setup-screen').style.display = 'none';
    document.getElementById('nav-tabs').style.display = 'flex';
    this.switchPanel(this._currentPanel || 'dashboard');
  },

  updateConnectionStatus(connected) {
    const dot = document.getElementById('connection-dot');
    const label = document.getElementById('connection-label');
    if (connected) {
      dot.className = 'status-dot connected';
      label.textContent = 'Connected';
    } else {
      dot.className = 'status-dot error';
      label.textContent = 'Disconnected';
    }
  },

  initSettings() {
    const connForm = document.getElementById('connection-form');
    if (connForm) {
      connForm.innerHTML = this._connectionFormHTML('settings');
      connForm.querySelector('#settings-connect-btn').addEventListener('click', () => this.saveConnection(connForm, 'settings'));
      // Load existing profile
      this.api('/api/connections').then(profiles => {
        if (profiles && profiles.length) {
          const p = profiles[0];
          const f = connForm;
          if (f.querySelector('#settings-name')) f.querySelector('#settings-name').value = p.name || '';
          if (f.querySelector('#settings-host')) f.querySelector('#settings-host').value = p.host || '';
          if (f.querySelector('#settings-port')) f.querySelector('#settings-port').value = p.port || 9047;
          if (f.querySelector('#settings-user')) f.querySelector('#settings-user').value = p.username || '';
          if (f.querySelector('#settings-project-id')) f.querySelector('#settings-project-id').value = p.cloud_project_id || '';
          if (f.querySelector('#settings-auth')) f.querySelector('#settings-auth').value = p.auth_type || 'password';
          // Toggle cloud fields LAST so it correctly shows/hides PAT vs password
          if (f.querySelector('#settings-cloud')) {
            f.querySelector('#settings-cloud').checked = !!p.is_cloud;
            this._toggleCloudFields('settings', !!p.is_cloud);
          }
        }
      });
    }

    const notifForm = document.getElementById('notification-form');
    if (notifForm) {
      notifForm.innerHTML = `
        <div class="form-group">
          <label class="form-label">Webhook URL (Slack/Teams/Discord)</label>
          <input class="form-input" id="notif-webhook-url" placeholder="https://hooks.slack.com/...">
        </div>
        <div class="form-group">
          <label><input type="checkbox" id="notif-webhook-enabled"> Enable webhook notifications</label>
        </div>
        <button class="btn btn-secondary btn-sm" id="save-webhook-btn" style="margin-bottom:20px">Save Webhook</button>
        <button class="btn btn-secondary btn-sm" id="test-webhook-btn" style="margin-left:8px;margin-bottom:20px">Test</button>
        <hr style="border-color:var(--border);margin:16px 0">
        <div class="form-group">
          <label class="form-label">SMTP Host</label>
          <input class="form-input" id="notif-smtp-host" placeholder="smtp.gmail.com">
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">SMTP Port</label>
            <input class="form-input" id="notif-smtp-port" type="number" value="587">
          </div>
          <div class="form-group">
            <label class="form-label">Username</label>
            <input class="form-input" id="notif-smtp-user" placeholder="user@example.com">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Password</label>
            <input class="form-input" id="notif-smtp-pass" type="password">
          </div>
          <div class="form-group">
            <label class="form-label">To Address</label>
            <input class="form-input" id="notif-smtp-to" placeholder="alerts@example.com">
          </div>
        </div>
        <div class="form-group">
          <label><input type="checkbox" id="notif-email-enabled"> Enable email notifications</label>
        </div>
        <button class="btn btn-secondary btn-sm" id="save-email-btn">Save Email</button>
        <button class="btn btn-secondary btn-sm" id="test-email-btn" style="margin-left:8px">Test</button>
      `;
      notifForm.querySelector('#save-webhook-btn').addEventListener('click', () => this.saveNotification('webhook'));
      notifForm.querySelector('#test-webhook-btn').addEventListener('click', () => this.testNotification('webhook'));
      notifForm.querySelector('#save-email-btn').addEventListener('click', () => this.saveNotification('email'));
      notifForm.querySelector('#test-email-btn').addEventListener('click', () => this.testNotification('email'));
    }
  },

  _connectionFormHTML(prefix = 'conn') {
    const p = prefix;
    return `
      <div class="form-group">
        <label class="form-label">Profile Name</label>
        <input class="form-input" id="${p}-name" value="default" placeholder="default">
      </div>
      <div class="form-group">
        <label><input type="checkbox" id="${p}-cloud" onchange="App._toggleCloudFields('${p}', this.checked)"> Dremio Cloud</label>
      </div>
      <div id="${p}-cloud-fields" style="display:none">
        <div class="form-group">
          <label class="form-label">Project ID</label>
          <input class="form-input" id="${p}-project-id" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx">
        </div>
      </div>
      <div id="${p}-self-managed-fields">
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Host</label>
            <input class="form-input" id="${p}-host" value="localhost" placeholder="localhost">
          </div>
          <div class="form-group">
            <label class="form-label">Port</label>
            <input class="form-input" id="${p}-port" type="number" value="9047">
          </div>
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">Auth Type</label>
        <select class="form-select" id="${p}-auth" data-prefix="${p}">
          <option value="password">Username / Password</option>
          <option value="pat">Personal Access Token (PAT)</option>
        </select>
      </div>
      <div id="${p}-password-fields">
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Username</label>
            <input class="form-input" id="${p}-user" placeholder="admin">
          </div>
          <div class="form-group">
            <label class="form-label">Password</label>
            <input class="form-input" id="${p}-pass" type="password">
          </div>
        </div>
      </div>
      <div id="${p}-pat-fields" style="display:none">
        <div class="form-group">
          <label class="form-label">PAT Token</label>
          <input class="form-input" id="${p}-pat" type="password" placeholder="Enter PAT">
        </div>
      </div>
      <div class="form-group" style="margin-top:16px">
        <button class="btn btn-primary" id="${p}-connect-btn">Connect</button>
        <button class="btn btn-secondary" style="margin-left:8px" onclick="App.testConnection('${p}')">Test</button>
      </div>
      <div id="${p}-status" style="margin-top:8px;font-size:0.85rem"></div>
    `;
  },

  async saveConnection(container, prefix = 'conn') {
    const profile = this._getProfileFromForm(prefix);
    const statusEl = document.getElementById(prefix + '-status');
    statusEl.innerHTML = '<span style="color:var(--yellow)">Connecting...</span>';
    try {
      const result = await this.api('/api/connection', 'POST', profile);
      if (result.success) {
        statusEl.innerHTML = '<span style="color:var(--green)">✅ Connected!</span>';
        this.hideSetup();
        this.updateConnectionStatus(true);
        Dashboard.refresh();
      } else {
        statusEl.innerHTML = `<span style="color:var(--red)">❌ ${this.escapeHtml(result.message)}</span>`;
      }
    } catch (e) {
      statusEl.innerHTML = `<span style="color:var(--red)">❌ ${this.escapeHtml(String(e))}</span>`;
    }
  },

  async testConnection(prefix = 'conn') {
    const profile = this._getProfileFromForm(prefix);
    const statusEl = document.getElementById(prefix + '-status');
    statusEl.innerHTML = '<span style="color:var(--yellow)">Testing...</span>';
    try {
      const result = await this.api('/api/connection/test', 'POST', profile);
      statusEl.innerHTML = result.success
        ? '<span style="color:var(--green)">✅ Connection successful!</span>'
        : `<span style="color:var(--red)">❌ ${this.escapeHtml(result.message)}</span>`;
    } catch (e) {
      statusEl.innerHTML = `<span style="color:var(--red)">❌ ${this.escapeHtml(String(e))}</span>`;
    }
  },

  _getProfileFromForm(prefix = 'conn') {
    const p = prefix;
    return {
      name: (document.getElementById(p + '-name') || {}).value || 'default',
      host: (document.getElementById(p + '-host') || {}).value || 'localhost',
      port: parseInt((document.getElementById(p + '-port') || {}).value) || 9047,
      auth_type: (document.getElementById(p + '-auth') || {}).value || 'password',
      username: (document.getElementById(p + '-user') || {}).value || '',
      password: (document.getElementById(p + '-pass') || {}).value || '',
      pat_token: (document.getElementById(p + '-pat') || {}).value || '',
      is_cloud: (document.getElementById(p + '-cloud') || {}).checked || false,
      cloud_project_id: (document.getElementById(p + '-project-id') || {}).value || '',
      is_default: true,
    };
  },

  _toggleCloudFields(prefix, isCloud) {
    const cloudFields = document.getElementById(prefix + '-cloud-fields');
    const selfManagedFields = document.getElementById(prefix + '-self-managed-fields');
    const authSelect = document.getElementById(prefix + '-auth');
    if (cloudFields) cloudFields.style.display = isCloud ? 'block' : 'none';
    if (selfManagedFields) selfManagedFields.style.display = isCloud ? 'none' : 'block';
    // Auto-switch to PAT when Cloud is selected, back to password when unchecked
    if (authSelect) {
      authSelect.value = isCloud ? 'pat' : 'password';
    }
    // Directly toggle the password/PAT fields
    const pwFields = document.getElementById(prefix + '-password-fields');
    const patFields = document.getElementById(prefix + '-pat-fields');
    if (isCloud) {
      if (pwFields) pwFields.style.display = 'none';
      if (patFields) patFields.style.display = 'block';
    } else {
      if (pwFields) pwFields.style.display = 'block';
      if (patFields) patFields.style.display = 'none';
    }
  },

  async saveNotification(channel) {
    let config, enabled;
    if (channel === 'webhook') {
      config = { url: document.getElementById('notif-webhook-url').value };
      enabled = document.getElementById('notif-webhook-enabled').checked;
    } else {
      config = {
        smtp_host: document.getElementById('notif-smtp-host').value,
        port: parseInt(document.getElementById('notif-smtp-port').value) || 587,
        username: document.getElementById('notif-smtp-user').value,
        password: document.getElementById('notif-smtp-pass').value,
        to_addr: document.getElementById('notif-smtp-to').value,
        from_addr: document.getElementById('notif-smtp-user').value,
      };
      enabled = document.getElementById('notif-email-enabled').checked;
    }
    await this.api('/api/notifications', 'POST', { channel, config, enabled });
    alert('Saved!');
  },

  async testNotification(channel) {
    const result = await this.api('/api/notifications/test', 'POST', { channel });
    alert(result.success ? 'Test sent!' : 'Failed: ' + result.message);
  },

  // ── Modal ─────────────────────────────────────────────────────

  showModal(title, bodyHTML, buttons = []) {
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-body').innerHTML = bodyHTML;
    const footer = document.getElementById('modal-footer');
    footer.innerHTML = '';
    buttons.forEach(b => {
      const btn = document.createElement('button');
      btn.className = b.class || 'btn btn-secondary';
      btn.textContent = b.text;
      btn.addEventListener('click', b.action);
      footer.appendChild(btn);
    });
    document.getElementById('modal-overlay').classList.add('active');
  },

  closeModal() {
    document.getElementById('modal-overlay').classList.remove('active');
  },

  // ── Utilities ─────────────────────────────────────────────────

  async api(path, method = 'GET', body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const resp = await fetch(path, opts);
    return resp.json();
  },

  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  },

  formatDuration(timestamp) {
    if (!timestamp) return '—';
    try {
      const start = new Date(timestamp).getTime();
      const diff = Date.now() - start;
      if (isNaN(diff) || diff < 0) return '—';
      const sec = Math.floor(diff / 1000);
      if (sec < 60) return sec + 's';
      const min = Math.floor(sec / 60);
      const remSec = sec % 60;
      if (min < 60) return min + 'm ' + remSec + 's';
      const hr = Math.floor(min / 60);
      return hr + 'h ' + (min % 60) + 'm';
    } catch { return '—'; }
  },

  formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  },

  timeAgo(epochSeconds) {
    if (!epochSeconds) return '';
    const diff = Math.floor(Date.now() / 1000 - epochSeconds);
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return Math.floor(diff / 86400) + 'd ago';
  }
};

// Auth type toggle (works for any prefixed form)
document.addEventListener('change', (e) => {
  const el = e.target;
  if (el.tagName === 'SELECT' && el.dataset.prefix) {
    const p = el.dataset.prefix;
    const isPat = el.value === 'pat';
    const pwFields = document.getElementById(p + '-password-fields');
    const patFields = document.getElementById(p + '-pat-fields');
    if (pwFields) pwFields.style.display = isPat ? 'none' : 'block';
    if (patFields) patFields.style.display = isPat ? 'block' : 'none';
  }
});

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
