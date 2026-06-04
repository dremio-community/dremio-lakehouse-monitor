/**
 * Schema Drift Monitor — UI logic
 */

const SchemaDrift = (() => {
  let allDrifts = [];
  let currentTable = '';

  const DRIFT_LABELS = {
    column_added:        { label: 'Column Added',       cls: 'green'  },
    column_dropped:      { label: 'Column Dropped',     cls: 'red'    },
    type_changed:        { label: 'Type Changed',       cls: 'yellow' },
    nullability_changed: { label: 'Nullability Changed',cls: 'yellow' },
  };

  function fmtTime(ts) {
    if (!ts) return '—';
    const d = new Date(ts * 1000);
    return d.toLocaleString();
  }

  function fmtRelative(ts) {
    if (!ts) return '';
    const diff = Math.floor((Date.now() / 1000) - ts);
    if (diff < 60)   return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400)return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  }

  async function loadDrifts() {
    const url = currentTable
      ? `/api/schema/drifts?table=${encodeURIComponent(currentTable)}`
      : '/api/schema/drifts';
    try {
      const res = await fetch(url);
      allDrifts = await res.json();
    } catch (e) {
      allDrifts = [];
    }
    renderDrifts();
    updateBadge();
  }

  async function loadSchema(tablePath) {
    if (!tablePath) {
      document.getElementById('schema-columns-body').innerHTML =
        '<tr><td colspan="4" class="empty-state"><div class="empty-state-text">Select a table to view its schema</div></td></tr>';
      document.getElementById('schema-viewer-table-label').textContent = '';
      return;
    }
    try {
      const res = await fetch(`/api/schema/latest?table=${encodeURIComponent(tablePath)}`);
      const cols = await res.json();
      renderSchema(tablePath, cols);
    } catch (e) {
      document.getElementById('schema-columns-body').innerHTML =
        '<tr><td colspan="4" class="empty-state"><div class="empty-state-text">Failed to load schema</div></td></tr>';
    }
  }

  async function loadWatchedTables() {
    try {
      const res = await fetch('/api/watched-tables');
      const tables = await res.json();
      const sel = document.getElementById('schema-table-filter');
      const current = sel.value;
      sel.innerHTML = '<option value="">All watched tables</option>';
      tables.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.table_path;
        opt.textContent = t.label || t.table_path;
        sel.appendChild(opt);
      });
      if (current) sel.value = current;

      document.getElementById('schema-tables-count').textContent = tables.length;
    } catch (e) {}
  }

  function renderDrifts() {
    const tbody = document.getElementById('schema-drifts-body');
    const drifts = currentTable
      ? allDrifts.filter(d => d.table_path === currentTable)
      : allDrifts;

    // Summary counts
    const drops  = drifts.filter(d => d.drift_type === 'column_dropped').length;
    const types  = drifts.filter(d => d.drift_type === 'type_changed').length;
    const unacked = drifts.filter(d => !d.acknowledged).length;

    document.getElementById('schema-drifts-total').textContent = drifts.length;
    document.getElementById('schema-drops-count').textContent  = drops;
    document.getElementById('schema-types-count').textContent  = types;

    if (!drifts.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-state"><div class="empty-state-text">No drift events recorded yet — schemas look stable 🎉</div></td></tr>';
      return;
    }

    tbody.innerHTML = drifts.map(d => {
      const info   = DRIFT_LABELS[d.drift_type] || { label: d.drift_type, cls: '' };
      const acked  = d.acknowledged ? 'opacity:0.45' : '';
      const before = d.old_value ? `<code>${d.old_value}</code>` : '<span style="color:var(--text-muted)">—</span>';
      const after  = d.new_value ? `<code>${d.new_value}</code>` : '<span style="color:var(--text-muted)">—</span>';
      const ackBtn = d.acknowledged
        ? '<span style="color:var(--text-muted);font-size:0.75rem">✓ ack</span>'
        : `<button class="btn btn-sm btn-secondary" onclick="SchemaDrift.ack(${d.id})">Ack</button>`;
      const shortTable = (d.table_path || '').split('.').pop() || d.table_path;
      return `<tr style="${acked}">
        <td title="${fmtTime(d.detected_at)}">${fmtRelative(d.detected_at)}</td>
        <td title="${d.table_path}">${shortTable}</td>
        <td><span class="drift-badge drift-${info.cls}">${info.label}</span></td>
        <td><code>${d.column_name}</code></td>
        <td>${before}</td>
        <td>${after}</td>
        <td>${ackBtn}</td>
      </tr>`;
    }).join('');
  }

  function renderSchema(tablePath, cols) {
    const label = document.getElementById('schema-viewer-table-label');
    label.textContent = `— ${tablePath}`;

    const tbody = document.getElementById('schema-columns-body');
    if (!cols || !cols.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty-state"><div class="empty-state-text">No schema data captured yet</div></td></tr>';
      return;
    }

    // Highlight drifted columns
    const recentDrifts = allDrifts
      .filter(d => d.table_path === tablePath && !d.acknowledged)
      .reduce((acc, d) => { acc[d.column_name] = d.drift_type; return acc; }, {});

    tbody.innerHTML = cols.map((col, i) => {
      const driftType = recentDrifts[col.name];
      const rowStyle = driftType ? `background:var(--drift-${DRIFT_LABELS[driftType]?.cls || ''}-bg,rgba(255,193,7,0.08))` : '';
      const badge = driftType
        ? `<span class="drift-badge drift-${DRIFT_LABELS[driftType]?.cls}">${DRIFT_LABELS[driftType]?.label}</span>`
        : '';
      return `<tr style="${rowStyle}">
        <td style="color:var(--text-muted)">${i + 1}</td>
        <td><code>${col.name}</code> ${badge}</td>
        <td><code>${col.type || '—'}</code></td>
        <td>${col.nullable ? 'YES' : 'NO'}</td>
      </tr>`;
    }).join('');
  }

  function updateBadge() {
    const unacked = allDrifts.filter(d => !d.acknowledged).length;
    const badge = document.getElementById('schema-drift-badge');
    if (badge) {
      badge.textContent = unacked;
      badge.style.display = unacked > 0 ? 'inline-flex' : 'none';
    }
  }

  async function ack(driftId) {
    await fetch(`/api/schema/drifts/${driftId}`, { method: 'DELETE' });
    await loadDrifts();
    if (currentTable) renderSchema(currentTable,
      await fetch(`/api/schema/latest?table=${encodeURIComponent(currentTable)}`).then(r => r.json()));
  }

  function init() {
    WS.on('schema_drift', (data) => onDriftEvent(data));

    const filterSel = document.getElementById('schema-table-filter');
    filterSel?.addEventListener('change', () => {
      currentTable = filterSel.value;
      loadDrifts();
      if (currentTable) loadSchema(currentTable);
      else {
        document.getElementById('schema-columns-body').innerHTML =
          '<tr><td colspan="4" class="empty-state"><div class="empty-state-text">Select a table to view its schema</div></td></tr>';
        document.getElementById('schema-viewer-table-label').textContent = '';
      }
    });

    document.getElementById('schema-refresh-btn')?.addEventListener('click', () => {
      loadWatchedTables();
      loadDrifts();
      if (currentTable) loadSchema(currentTable);
    });
  }

  async function refresh() {
    await loadWatchedTables();
    await loadDrifts();
    if (currentTable) await loadSchema(currentTable);
  }

  // Called by websocket when schema_drift event arrives
  function onDriftEvent(drifts) {
    if (drifts && drifts.length) {
      loadDrifts();
    }
  }

  return { init, refresh, ack, onDriftEvent };
})();
