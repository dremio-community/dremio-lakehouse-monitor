/**
 * Dashboard panel for Dremio Lakehouse Monitor.
 */

const Dashboard = {
  _queryHistory: [],
  _queueHistory: [],
  _layout: null,  // Widget visibility preferences

  // Widget definitions for the toggle menu
  WIDGETS: {
    cluster_health: 'Cluster Health',
    active_queries: 'Active Queries',
    query_rate: 'Query Rate',
    acceleration_rate: 'Acceleration Rate',
    scan_efficiency: 'Scan Efficiency',
    query_types: 'Query Types',
    sources_memory: 'Sources & Memory',
    query_lifecycle: 'Query Lifecycle',
    slow_queries: 'Slow Queries',
    recent_alerts: 'Recent Alerts',
    success_rate: 'Success Rate',
    reflection_savings: 'Reflection Savings',
    queue_wait: 'Queue Wait',
    top_users: 'Top Users',
    top_datasets: 'Top Datasets',
    duration_distribution: 'Duration Distribution',
    error_patterns: 'Error Patterns',
    reflection_efficiency: 'Reflection Utilization',
    engine_health: '⚡ Engine Health',
    engine_trends: '📈 Engine Trends',
    reflection_health: '🔍 Reflection Health',
    dead_accelerations: '🪦 Dead Accelerations',
    iceberg_health: '❄️ Iceberg Table Health',
    c3_hit_rates: '💿 C3 Hit Rates',
    wlm_queue_metrics: '🚦 WLM Queue Metrics',
    spill_to_disk: '💾 Spill to Disk',
    catalog_sync_health: '🔄 Catalog Sync Health',
    iceberg_maintenance: '🧹 Iceberg Maintenance',
    autoscaling_events: '📈 Auto-Scaling Events',
  },

  async init() {
    // Load saved layout
    try {
      this._layout = await App.api('/api/dashboard-layout');
    } catch { this._layout = null; }

    this._initWidgetToggle();
    this._applyLayout();
    this.refresh();

    // Refresh on WebSocket events
    WS.on('active_jobs', () => this.refresh());
    WS.on('sources', () => this.refresh());
    WS.on('memory', () => this.refresh());
    WS.on('job_counts', () => this.refresh());
    WS.on('server_status', () => this.refresh());
    WS.on('top_users', () => this.refresh());
    WS.on('top_datasets', () => this.refresh());
    WS.on('duration_distribution', () => this.refresh());
    WS.on('success_breakdown', () => this.refresh());
    WS.on('query_lifecycle', () => this.refresh());
    WS.on('error_patterns', () => this.refresh());
    WS.on('query_types', () => this.refresh());
    WS.on('scan_efficiency', () => this.refresh());
    WS.on('reflection_efficiency', () => this.refresh());
    WS.on('engine_health', () => this.refresh());
    WS.on('reflection_health', () => this.refresh());
    WS.on('iceberg_health', () => this.refresh());
    WS.on('c3_hit_rates', () => this.refresh());
    WS.on('wlm_queue_metrics', () => this.refresh());
    WS.on('spill_to_disk', () => this.refresh());
    WS.on('catalog_sync_health', () => this.refresh());
    WS.on('iceberg_maintenance', () => this.refresh());
    WS.on('autoscaling_events', () => this.refresh());

    // Init watched tables UI
    this._initWatchedTables();
  },

  // ── Widget Toggle System ──────────────────────────────

  _initWidgetToggle() {
    const btn = document.getElementById('toggle-widgets-btn');
    const dropdown = document.getElementById('widget-toggle-dropdown');
    if (!btn || !dropdown) return;

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (!dropdown.contains(e.target) && e.target !== btn) {
        dropdown.style.display = 'none';
      }
    });

    // Build toggle list
    this._renderToggleList();

    // All on/off buttons
    document.getElementById('toggle-all-btn')?.addEventListener('click', () => {
      Object.keys(this.WIDGETS).forEach(k => this._layout[k] = true);
      this._saveLayout();
    });
    document.getElementById('toggle-none-btn')?.addEventListener('click', () => {
      Object.keys(this.WIDGETS).forEach(k => this._layout[k] = false);
      this._saveLayout();
    });
  },

  _renderToggleList() {
    const list = document.getElementById('widget-toggle-list');
    if (!list) return;
    const layout = this._layout || {};

    list.innerHTML = Object.entries(this.WIDGETS).map(([key, label]) => {
      const checked = layout[key] !== false ? 'checked' : '';
      return `<label class="widget-toggle-item">
        <input type="checkbox" data-widget-key="${key}" ${checked}>
        <span>${label}</span>
      </label>`;
    }).join('');

    // Wire up change events
    list.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', () => {
        this._layout[cb.dataset.widgetKey] = cb.checked;
        this._saveLayout();
      });
    });
  },

  _applyLayout() {
    const layout = this._layout || {};
    document.querySelectorAll('[data-widget]').forEach(el => {
      const widgets = el.dataset.widget.split(',');
      // Show if ANY of the listed widgets are visible
      const visible = widgets.some(w => layout[w.trim()] !== false);
      el.style.display = visible ? '' : 'none';
    });
  },

  async _saveLayout() {
    this._applyLayout();
    this._renderToggleList();
    try {
      await App.api('/api/dashboard-layout', 'POST', this._layout);
    } catch (e) {
      console.warn('Failed to save layout:', e);
    }
  },

  // ── Data Refresh ──────────────────────────────────────

  async refresh() {
    try {
      const data = await App.api('/api/status');
      this.render(data);
    } catch (e) {
      console.warn('Dashboard refresh failed:', e);
    }
  },

  render(data) {
    if (!data) return;
    const L = this._layout || {};

    // Health ring
    if (L.cluster_health !== false) {
      Charts.healthRing('health-ring', data.health_score || 0);
      const healthLabel = document.getElementById('health-label');
      if (data.health_issues && data.health_issues.length > 0) {
        healthLabel.textContent = data.health_issues[0];
        healthLabel.style.color = data.health_score >= 80 ? 'var(--green)' : data.health_score >= 50 ? 'var(--yellow)' : 'var(--red)';
      } else {
        healthLabel.textContent = 'All Systems Healthy';
        healthLabel.style.color = 'var(--green)';
      }
    }

    // Active queries
    if (L.active_queries !== false) {
      const aqEl = document.getElementById('active-queries-count');
      const count = data.active_query_count || 0;
      aqEl.textContent = count;
      aqEl.className = 'metric-value' + (count > 20 ? ' red' : count > 10 ? ' yellow' : '');
      document.getElementById('queued-label').textContent = `${data.queued_count || 0} queued`;
      this._queryHistory.push(count);
      if (this._queryHistory.length > 30) this._queryHistory.shift();
      Charts.sparkline('sparkline-queries', this._queryHistory, { color: '#58a6ff' });
    }

    // Query rate
    if (L.query_rate !== false) {
      const jc = data.job_counts || {};
      const total = parseInt(jc.total) || 0;
      document.getElementById('query-rate').textContent = total;
      document.getElementById('query-rate-subtitle').textContent =
        `${parseInt(jc.completed) || 0} completed · ${parseInt(jc.failed) || 0} failed`;
    }

    // Acceleration rate
    if (L.acceleration_rate !== false) {
      const jc = data.job_counts || {};
      const total = parseInt(jc.total) || 0;
      const accelCount = parseInt(jc.accelerated) || 0;
      const accelPct = total > 0 ? Math.round((accelCount / total) * 100) : 0;
      document.getElementById('accel-rate').textContent = accelPct + '%';
      document.getElementById('accel-subtitle').textContent =
        `${accelCount} of ${total} queries accelerated`;
    }

    // Sources & Memory
    if (L.sources_memory !== false) {
      this.renderSources(data);
      this.renderMemory(data);
    }

    // Slow queries
    if (L.slow_queries !== false) this.renderSlowQueries();

    // New monitors
    if (L.success_rate !== false) this.renderSuccessDonut(data.success_breakdown || {});
    if (L.reflection_savings !== false) this.renderReflectionSavings(data.success_breakdown || {});
    if (L.queue_wait !== false) this.renderQueueWait(data.queued_count || 0);
    if (L.top_users !== false) this.renderTopUsers(data.top_users || []);
    if (L.top_datasets !== false) this.renderTopDatasets(data.top_datasets || []);
    if (L.duration_distribution !== false) this.renderDurationDistribution(data.duration_distribution || {});
    if (L.query_lifecycle !== false) this.renderQueryLifecycle(data.query_lifecycle || {});
    if (L.error_patterns !== false) this.renderErrorPatterns(data.error_patterns || []);
    if (L.query_types !== false) this.renderQueryTypes(data.query_types || []);
    if (L.scan_efficiency !== false) this.renderScanEfficiency(data.scan_efficiency || {});
    if (L.reflection_efficiency !== false) this.renderReflectionEfficiency(data.reflection_efficiency || []);

    // Enhanced monitors
    if (L.engine_health !== false) this.renderEngineHealth(data.engine_health || {});
    if (L.engine_trends !== false) this.renderEngineTrends();
    if (L.reflection_health !== false) this.renderReflectionHealthWidget(data.reflection_health || {});
    if (L.dead_accelerations !== false) this.renderDeadAccelerations(data.reflection_health || {});
    if (L.iceberg_health !== false) this.renderIcebergHealth(data.iceberg_health || []);
    if (L.c3_hit_rates !== false) this.renderC3HitRates(data.c3_hit_rates || {});
    if (L.wlm_queue_metrics !== false) this.renderWLMQueueMetrics(data.wlm_queue_metrics || []);
    if (L.spill_to_disk !== false) this.renderSpillToDisk(data.spill_to_disk || []);
    if (L.catalog_sync_health !== false) this.renderCatalogSyncHealth(data.catalog_sync_health || []);
    if (L.iceberg_maintenance !== false) this.renderIcebergMaintenance(data.iceberg_maintenance || []);
    if (L.autoscaling_events !== false) this.renderAutoscalingEvents(data.autoscaling_events || []);
  },

  // ── Existing Renderers ────────────────────────────────

  renderSources(data) {
    const grid = document.getElementById('source-grid');
    App.api('/api/sources').then(s => this._renderSourceTiles(grid, s));
  },

  _renderSourceTiles(grid, sources) {
    if (!sources || !sources.length) {
      grid.innerHTML = '<div class="empty-state"><div class="empty-state-text">No sources configured</div></div>';
      return;
    }
    grid.innerHTML = sources.map(s => {
      const status = (s.state?.status || s.status?.health || 'unknown').toLowerCase();
      const dotClass = status === 'good' || status === 'healthy' ? 'good' : status === 'bad' ? 'bad' : 'warn';
      const label = status === 'good' || status === 'healthy' ? '✅' : '⚠️';
      return `<div class="source-tile"><span class="dot ${dotClass}"></span>${s.name || 'Unknown'} ${label}</div>`;
    }).join('');
  },

  renderMemory(data) {
    const container = document.getElementById('memory-nodes');
    const nodes = data.memory_nodes || [];
    if (!nodes.length) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-text">No memory data available</div></div>';
      return;
    }
    container.innerHTML = nodes.map(n => {
      const cur = parseInt(n.heap_current) || 0;
      const max = parseInt(n.heap_max) || 1;
      const host = (n.hostname || 'unknown').split('.')[0];
      return Charts.memoryBar(container, host, cur, max);
    }).join('');
  },

  async renderSlowQueries() {
    try {
      const jobs = await App.api('/api/jobs/active');
      const tbody = document.getElementById('slow-queries-body');
      if (!jobs || !jobs.length) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty-state"><div class="empty-state-text">No active queries</div></td></tr>';
        return;
      }
      const sorted = jobs.sort((a, b) => {
        return new Date(a.submitted_ts || 0).getTime() - new Date(b.submitted_ts || 0).getTime();
      }).slice(0, 5);
      tbody.innerHTML = sorted.map(j => {
        const dur = App.formatDuration(j.submitted_ts);
        const statusClass = (j.status || '').toLowerCase();
        return `<tr>
          <td>${j.user || '—'}</td>
          <td class="query-text" title="${App.escapeHtml(j.query || '')}">${App.escapeHtml((j.query || '').substring(0, 100))}</td>
          <td><span class="duration-bar"><span>${dur}</span></span></td>
          <td><span class="badge-status ${statusClass}">${j.status || '—'}</span></td>
        </tr>`;
      }).join('');
    } catch (e) {
      console.warn('Failed to load slow queries:', e);
    }
  },

  // ── New Monitor Renderers ─────────────────────────────

  renderSuccessDonut(breakdown) {
    const completed = parseInt(breakdown.completed) || 0;
    const failed = parseInt(breakdown.failed) || 0;
    const cancelled = parseInt(breakdown.cancelled) || 0;

    Charts.donutChart('success-donut', [
      { label: 'Completed', value: completed, color: '#3fb950' },
      { label: 'Failed', value: failed, color: '#f85149' },
      { label: 'Cancelled', value: cancelled, color: '#d29922' },
    ], { size: 120 });

    const legend = document.getElementById('success-legend');
    if (legend) {
      legend.innerHTML = `
        <div class="legend-item"><span class="legend-dot" style="background:var(--green)"></span>Completed: ${completed}</div>
        <div class="legend-item"><span class="legend-dot" style="background:var(--red)"></span>Failed: ${failed}</div>
        <div class="legend-item"><span class="legend-dot" style="background:var(--yellow)"></span>Cancelled: ${cancelled}</div>
      `;
    }
  },

  renderReflectionSavings(breakdown) {
    const avgAccel = parseFloat(breakdown.avg_accel_ms) || 0;
    const avgNonAccel = parseFloat(breakdown.avg_non_accel_ms) || 0;
    document.getElementById('avg-accel-time').textContent = this._formatMs(avgAccel);
    document.getElementById('avg-non-accel-time').textContent = this._formatMs(avgNonAccel);
    const speedupEl = document.getElementById('speedup-factor');
    if (avgAccel > 0 && avgNonAccel > 0) {
      const speedup = (avgNonAccel / avgAccel).toFixed(1);
      speedupEl.textContent = speedup + 'x faster';
      speedupEl.className = 'savings-value ' + (parseFloat(speedup) >= 2 ? 'green' : 'accent');
    } else {
      speedupEl.textContent = '—';
    }
  },

  renderQueueWait(queuedCount) {
    document.getElementById('queue-wait-count').textContent = queuedCount;
    this._queueHistory.push(queuedCount);
    if (this._queueHistory.length > 30) this._queueHistory.shift();
    Charts.sparkline('sparkline-queue', this._queueHistory, { color: '#d29922' });
  },

  renderTopUsers(users) {
    if (!users || !users.length) {
      Charts.horizontalBarChart('top-users-chart', []);
      return;
    }
    const items = users.map(u => {
      const failPct = u.query_count > 0 ? Math.round((parseInt(u.failed_count || 0) / parseInt(u.query_count)) * 100) : 0;
      return {
        label: u.username || 'unknown',
        value: parseInt(u.query_count) || 0,
        sublabel: `Avg: ${this._formatMs(parseFloat(u.avg_duration_ms) || 0)} · Failed: ${failPct}% · Accel: ${u.accelerated_count || 0}`,
      };
    });
    Charts.horizontalBarChart('top-users-chart', items, { color: '#58a6ff' });
  },

  renderTopDatasets(datasets) {
    const tbody = document.getElementById('top-datasets-body');
    if (!datasets || !datasets.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty-state"><div class="empty-state-text">No data yet</div></td></tr>';
      return;
    }
    tbody.innerHTML = datasets.map(d => {
      const count = parseInt(d.query_count) || 0;
      const accelCount = parseInt(d.accelerated_count) || 0;
      const accelPct = count > 0 ? Math.round((accelCount / count) * 100) : 0;
      const dataset = (d.dataset || '').replace(/^\[|\]$/g, '');
      const shortName = dataset.length > 40 ? '...' + dataset.slice(-37) : dataset;
      return `<tr>
        <td class="query-text" title="${App.escapeHtml(dataset)}">${App.escapeHtml(shortName)}</td>
        <td>${count}</td>
        <td>${this._formatMs(parseFloat(d.avg_duration_ms) || 0)}</td>
        <td><span class="badge-status ${accelPct > 50 ? 'active' : accelPct > 0 ? 'enqueued' : 'disabled'}">${accelPct}%</span></td>
      </tr>`;
    }).join('');
  },

  renderDurationDistribution(dist) {
    const buckets = ['<1s', '1-5s', '5-30s', '30s-2m', '2-10m', '>10m'];
    const counts = [
      parseInt(dist.under_1s) || 0, parseInt(dist.s1_to_5s) || 0,
      parseInt(dist.s5_to_30s) || 0, parseInt(dist.s30_to_2m) || 0,
      parseInt(dist.m2_to_10m) || 0, parseInt(dist.over_10m) || 0,
    ];
    Charts.histogramChart('duration-histogram', buckets, counts);
  },

  // ── New Phase 2 Renderers ─────────────────────────────

  renderQueryLifecycle(lifecycle) {
    const fms = (v) => this._formatMs(Math.max(0, parseFloat(v) || 0));
    // Filter out negative or impossibly large values (> 1 hour avg = bad timestamp data)
    const clamp = (v) => {
      const n = parseFloat(v) || 0;
      return (n > 0 && n < 3600000) ? n : 0;
    };
    const stages = [
      { label: 'Metadata', value: clamp(lifecycle.avg_metadata_ms), color: '#39d2c0', displayValue: fms(clamp(lifecycle.avg_metadata_ms)) },
      { label: 'Planning', value: clamp(lifecycle.avg_planning_ms), color: '#58a6ff', displayValue: fms(clamp(lifecycle.avg_planning_ms)) },
      { label: 'Queued', value: clamp(lifecycle.avg_queue_ms), color: '#d29922', displayValue: fms(clamp(lifecycle.avg_queue_ms)) },
      { label: 'Engine Start', value: clamp(lifecycle.avg_engine_start_ms), color: '#bc8cff', displayValue: fms(clamp(lifecycle.avg_engine_start_ms)) },
      { label: 'Execution', value: clamp(lifecycle.avg_execution_ms), color: '#3fb950', displayValue: fms(clamp(lifecycle.avg_execution_ms)) },
    ];
    Charts.stackedBarChart('lifecycle-chart', stages);
  },

  renderErrorPatterns(errors) {
    const tbody = document.getElementById('error-patterns-body');
    if (!errors || !errors.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty-state"><div class="empty-state-text">No errors — nice! 🎉</div></td></tr>';
      return;
    }
    tbody.innerHTML = errors.map(e => {
      const msg = (e.error_pattern || '').substring(0, 120);
      const count = parseInt(e.occurrence_count) || 0;
      const lastSeen = e.last_seen ? new Date(e.last_seen).toLocaleString() : '—';
      return `<tr>
        <td class="query-text" title="${App.escapeHtml(e.error_pattern || '')}">${App.escapeHtml(msg)}</td>
        <td><span class="badge-status failed">${count}</span></td>
        <td>${lastSeen}</td>
      </tr>`;
    }).join('');
  },

  renderQueryTypes(types) {
    if (!types || !types.length) {
      Charts.donutChart('query-types-donut', [], { size: 120 });
      return;
    }
    const colors = ['#58a6ff', '#3fb950', '#bc8cff', '#d29922', '#f0883e', '#f85149', '#39d2c0', '#8b949e'];
    const segments = types.map((t, i) => ({
      label: t.query_type || 'Unknown',
      value: parseInt(t.query_count) || 0,
      color: colors[i % colors.length],
    }));
    Charts.donutChart('query-types-donut', segments, { size: 120 });

    const legend = document.getElementById('query-types-legend');
    if (legend) {
      legend.innerHTML = segments.slice(0, 5).map((s, i) =>
        `<div class="legend-item"><span class="legend-dot" style="background:${s.color}"></span>${s.label}: ${s.value}</div>`
      ).join('');
    }
  },

  renderScanEfficiency(scan) {
    const scanned = parseInt(scan.total_bytes_scanned) || 0;
    const returned = parseInt(scan.total_bytes_returned) || 0;

    document.getElementById('scan-bytes-scanned').textContent = App.formatBytes(scanned);
    document.getElementById('scan-bytes-returned').textContent = App.formatBytes(returned);

    const filterEl = document.getElementById('scan-filter-pct');
    if (scanned > 0 && scanned >= returned) {
      const filterPct = Math.round((1 - returned / scanned) * 100);
      filterEl.textContent = filterPct + '% filtered';
      filterEl.className = 'savings-value ' + (filterPct > 80 ? 'green' : filterPct > 50 ? 'accent' : '');
    } else if (returned > scanned && scanned > 0) {
      filterEl.textContent = 'Expanding';
      filterEl.className = 'savings-value accent';
    } else {
      filterEl.textContent = '—';
    }
  },

  renderReflectionEfficiency(reflections) {
    const tbody = document.getElementById('reflection-eff-body');
    if (!reflections || !reflections.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-state"><div class="empty-state-text">No reflections configured</div></td></tr>';
      return;
    }
    tbody.innerHTML = reflections.map(r => {
      const statusClass = (r.status || '').toLowerCase() === 'active' ? 'active' : 'disabled';
      return `<tr>
        <td title="${App.escapeHtml(r.reflection_name || '')}">${App.escapeHtml((r.reflection_name || '').substring(0, 30))}</td>
        <td><span class="badge-status ${r.type === 'RAW' ? 'running' : 'enqueued'}">${r.type || '—'}</span></td>
        <td>${r.considered_count || 0}</td>
        <td>${r.matched_count || 0}</td>
        <td>${r.accelerated_count || 0}</td>
        <td>${App.formatBytes(parseInt(r.current_footprint_bytes) || 0)}</td>
        <td><span class="badge-status ${statusClass}">${r.status || '—'}</span></td>
      </tr>`;
    }).join('');
  },

  // ── Advanced Observability Renderers ────────────────────────

  renderC3HitRates(data) {
    const el = document.getElementById('c3-hit-rate');
    const sub = document.getElementById('c3-subtitle');
    if (!el) return;
    const hit = parseInt(data.hit_bytes) || 0;
    const miss = parseInt(data.miss_bytes) || 0;
    if (hit === 0 && miss === 0) {
      el.textContent = '—';
      sub.textContent = 'No data available';
      return;
    }
    const hitPct = Math.round((hit / (hit + miss)) * 100);
    el.textContent = hitPct + '%';
    sub.textContent = `${App.formatBytes(hit)} hit / ${App.formatBytes(miss)} miss`;
  },

  renderWLMQueueMetrics(queues) {
    const tbody = document.getElementById('wlm-body');
    if (!tbody) return;
    if (!queues || !queues.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty-state"><div class="empty-state-text">No active queues</div></td></tr>';
      return;
    }
    tbody.innerHTML = queues.map(q => `<tr>
      <td>${App.escapeHtml(q.queue_name)}</td>
      <td>${q.job_count}</td>
      <td>${this._formatMs(parseFloat(q.avg_wait_ms) || 0)}</td>
      <td><span class="${parseInt(q.rejected_count) > 0 ? 'badge-status failed' : ''}">${q.rejected_count || 0}</span></td>
    </tr>`).join('');
  },

  renderSpillToDisk(spills) {
    const tbody = document.getElementById('spill-body');
    if (!tbody) return;
    if (!spills || !spills.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty-state"><div class="empty-state-text">No spilled queries</div></td></tr>';
      return;
    }
    tbody.innerHTML = spills.map(s => `<tr>
      <td>${App.escapeHtml(s.user || '—')}</td>
      <td>${this._formatMs(parseFloat(s.duration_ms) || 0)}</td>
      <td><span class="badge-status failed">${App.formatBytes(s.spilled_bytes || 0)}</span></td>
    </tr>`).join('');
  },

  renderCatalogSyncHealth(catalogs) {
    const tbody = document.getElementById('catalog-sync-body');
    if (!tbody) return;
    if (!catalogs || !catalogs.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty-state"><div class="empty-state-text">No external catalogs</div></td></tr>';
      return;
    }
    tbody.innerHTML = catalogs.map(c => `<tr>
      <td>${App.escapeHtml(c.name || '—')}</td>
      <td><span class="badge-status ${(c.status||'').toLowerCase()==='good'?'active':(c.status||'').toLowerCase()==='bad'?'failed':'enqueued'}">${c.status || '—'}</span></td>
      <td>${this._formatMs(parseFloat(c.last_sync_duration_ms) || 0)}</td>
    </tr>`).join('');
  },

  renderIcebergMaintenance(jobs) {
    const tbody = document.getElementById('iceberg-maintenance-body');
    if (!tbody) return;
    if (!jobs || !jobs.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty-state"><div class="empty-state-text">No recent jobs</div></td></tr>';
      return;
    }
    tbody.innerHTML = jobs.map(j => `<tr>
      <td>${App.escapeHtml(j.query_type || '—')}</td>
      <td><span class="badge-status ${(j.status||'').toLowerCase()}">${j.status || '—'}</span></td>
      <td>${this._formatMs(parseFloat(j.duration_ms) || 0)}</td>
    </tr>`).join('');
  },

  renderAutoscalingEvents(events) {
    const tbody = document.getElementById('autoscaling-body');
    if (!tbody) return;
    if (!events || !events.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty-state"><div class="empty-state-text">No events or using Software</div></td></tr>';
      return;
    }
    // Very simplified, assuming events structure for Cloud
    tbody.innerHTML = events.slice(0,10).map(e => `<tr>
      <td>${App.escapeHtml(e.engineName || e.id || '—')}</td>
      <td>${App.escapeHtml(e.state || e.status || '—')}</td>
      <td>${new Date(e.createdAt || e.updatedAt || Date.now()).toLocaleString()}</td>
    </tr>`).join('');
  },

  _formatMs(ms) {
    if (!ms || ms === 0) return '—';
    if (ms < 1000) return Math.round(ms) + 'ms';
    if (ms < 60000) return (ms / 1000).toFixed(1) + 's';
    if (ms < 3600000) return (ms / 60000).toFixed(1) + 'm';
    return (ms / 3600000).toFixed(1) + 'h';
  },

  // ── Engine Health ─────────────────────────────────────────

  renderEngineHealth(engine) {
    if (!engine || !engine.health_score && engine.health_score !== 0) return;

    Charts.healthRing('engine-health-ring', engine.health_score || 0);

    const label = document.getElementById('engine-health-label');
    if (engine.health_issues && engine.health_issues.length > 0) {
      label.textContent = engine.health_issues[0];
      label.style.color = engine.health_score >= 80 ? 'var(--green)'
        : engine.health_score >= 50 ? 'var(--yellow)' : 'var(--red)';
    } else {
      label.textContent = 'All Nodes Healthy';
      label.style.color = 'var(--green)';
    }

    document.getElementById('engine-node-count').textContent =
      `${engine.node_count || 0} node(s) · ${engine.overall_pressure || 0}% avg pressure`;

    // Render per-node pressure gauges
    const nodes = engine.nodes || [];
    Charts.gaugeBar('engine-pressure-gauges', nodes.map(n => ({
      label: n.hostname,
      pressure: n.pressure_index,
      heapPct: n.heap_pct,
      directPct: n.direct_pct,
    })));
  },

  async renderEngineTrends() {
    try {
      const snapshots = await App.api('/api/engine-history?hours=4');
      if (!snapshots || snapshots.length < 2) return;

      const pressureData = snapshots.map(s => s.overall_pressure || 0);
      const nodeData = snapshots.map(s => s.node_count || 0);
      const labels = snapshots.map(s => {
        const d = new Date(s.timestamp * 1000);
        return d.getHours().toString().padStart(2, '0') + ':' +
               d.getMinutes().toString().padStart(2, '0');
      });

      Charts.lineChart('engine-trend-chart', [
        { label: 'Memory Pressure %', data: pressureData, color: '#f0883e' },
      ], {
        labels,
        minY: 0,
        maxY: 100,
        formatY: v => v + '%',
      });
    } catch (e) {
      console.warn('Failed to load engine trends:', e);
    }
  },

  // ── Reflection Health ─────────────────────────────────────

  renderReflectionHealthWidget(rh) {
    if (!rh || rh.health_score === undefined) return;

    Charts.healthRing('reflection-health-ring', rh.health_score || 0);

    const label = document.getElementById('reflection-health-label');
    if (rh.health_issues && rh.health_issues.length > 0) {
      label.textContent = rh.health_issues[0];
      label.style.color = rh.health_score >= 80 ? 'var(--green)'
        : rh.health_score >= 50 ? 'var(--yellow)' : 'var(--red)';
    } else {
      label.textContent = 'All Reflections Healthy';
      label.style.color = 'var(--green)';
    }

    // Stats line
    const statsEl = document.getElementById('reflection-health-stats');
    statsEl.innerHTML = [
      `<span style="color:var(--green)">${rh.active_count || 0} active</span>`,
      `<span style="color:var(--red)">${rh.failed_count || 0} failed</span>`,
      `<span style="color:var(--text-muted)">${rh.disabled_count || 0} disabled</span>`,
    ].join(' · ');

    // Issues list
    const issuesEl = document.getElementById('reflection-health-issues');
    const issues = [];

    if (rh.health_issues && rh.health_issues.length > 0) {
      rh.health_issues.forEach(issue => {
        issues.push(`<div class="alert-item warning">
          <span class="alert-icon">⚠️</span>
          <div class="alert-content"><div class="alert-message">${App.escapeHtml(issue)}</div></div>
        </div>`);
      });
    }

    // Failure patterns
    if (rh.failure_patterns && rh.failure_patterns.length > 0) {
      rh.failure_patterns.forEach(fp => {
        issues.push(`<div class="alert-item critical">
          <span class="alert-icon">🔴</span>
          <div class="alert-content">
            <div class="alert-message">${fp.count} failure(s): ${App.escapeHtml(fp.message.substring(0, 100))}</div>
            <div class="alert-time">Affected: ${fp.reflections.slice(0, 3).join(', ')}${fp.reflections.length > 3 ? '...' : ''}</div>
          </div>
        </div>`);
      });
    }

    // Refresh stats
    if (rh.avg_refresh_ms > 0) {
      issues.push(`<div class="alert-item info">
        <span class="alert-icon">⏱️</span>
        <div class="alert-content">
          <div class="alert-message">Avg refresh: ${this._formatMs(rh.avg_refresh_ms)} · Max: ${this._formatMs(rh.max_refresh_ms)}</div>
          <div class="alert-time">Total footprint: ${App.formatBytes(rh.total_footprint_bytes || 0)}${rh.wasted_footprint_bytes ? ' · Wasted: ' + App.formatBytes(rh.wasted_footprint_bytes) : ''}</div>
        </div>
      </div>`);
    }

    if (issues.length === 0) {
      issuesEl.innerHTML = '<div class="empty-state"><div class="empty-state-text">No issues — reflections look great! 🎉</div></div>';
    } else {
      issuesEl.innerHTML = `<div class="alert-timeline">${issues.join('')}</div>`;
    }
  },

  renderDeadAccelerations(rh) {
    const tbody = document.getElementById('dead-accel-body');
    if (!tbody) return;
    const deadAccels = rh.dead_accelerations || [];
    if (!deadAccels.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-state"><div class="empty-state-text">No dead accelerations — great! 🎉</div></td></tr>';
      return;
    }
    tbody.innerHTML = deadAccels.map(d => {
      const dataset = (d.dataset || '').replace(/^\[|\]$/g, '');
      const shortDataset = dataset.length > 35 ? '...' + dataset.slice(-32) : dataset;
      return `<tr class="dead-accel-row">
        <td>${App.escapeHtml(d.name || '')}</td>
        <td><span class="badge-status ${d.type === 'RAW' ? 'running' : 'enqueued'}">${d.type || '—'}</span></td>
        <td class="query-text" title="${App.escapeHtml(dataset)}">${App.escapeHtml(shortDataset)}</td>
        <td><span class="badge-status failed">${App.formatBytes(d.footprint_bytes || 0)}</span></td>
        <td>${d.considered || 0}</td>
      </tr>`;
    }).join('');
  },

  // ── Iceberg Health ────────────────────────────────────────

  renderIcebergHealth(tables) {
    const container = document.getElementById('iceberg-health-container');
    if (!container) return;
    if (!tables || !tables.length) {
      container.innerHTML = `<div class="empty-state">
        <div class="empty-state-icon">🧊</div>
        <div class="empty-state-text">No tables being watched</div>
        <div style="margin-top:8px;font-size:0.85rem;color:var(--text-muted)">Add Iceberg tables in Settings → Watched Tables</div>
      </div>`;
      return;
    }

    container.innerHTML = `<div class="iceberg-grid">${tables.map(t => {
      if (t.error) {
        return `<div class="iceberg-card iceberg-error">
          <div class="iceberg-card-header">
            <span class="iceberg-card-name">${App.escapeHtml(t.label || t.table)}</span>
            <span class="badge-status failed">Error</span>
          </div>
          <div class="iceberg-card-detail">${App.escapeHtml(t.error)}</div>
        </div>`;
      }

      const smallRatio = t.small_file_ratio || 0;
      const sfClass = smallRatio > 60 ? 'critical' : smallRatio > 40 ? 'warn' : 'healthy';
      const sfLabel = smallRatio > 60 ? '🔴' : smallRatio > 40 ? '🟡' : '🟢';

      return `<div class="iceberg-card">
        <div class="iceberg-card-header">
          <span class="iceberg-card-name">${App.escapeHtml(t.label || t.table)}</span>
          <span class="badge-status ${sfClass === 'critical' ? 'failed' : sfClass === 'warn' ? 'enqueued' : 'active'}">${sfLabel} ${smallRatio}% small files</span>
        </div>
        <div class="iceberg-stats">
          <div class="iceberg-stat">
            <div class="iceberg-stat-value">${t.snapshot_count || 0}</div>
            <div class="iceberg-stat-label">Snapshots</div>
          </div>
          <div class="iceberg-stat">
            <div class="iceberg-stat-value">${t.total_files || 0}</div>
            <div class="iceberg-stat-label">Files</div>
          </div>
          <div class="iceberg-stat">
            <div class="iceberg-stat-value">${App.formatBytes(t.total_size_bytes || 0)}</div>
            <div class="iceberg-stat-label">Total Size</div>
          </div>
          <div class="iceberg-stat">
            <div class="iceberg-stat-value">${App.formatBytes(t.avg_file_size || 0)}</div>
            <div class="iceberg-stat-label">Avg File</div>
          </div>
          <div class="iceberg-stat">
            <div class="iceberg-stat-value">${t.small_files || 0}</div>
            <div class="iceberg-stat-label">Small Files</div>
          </div>
          <div class="iceberg-stat">
            <div class="iceberg-stat-value">${t.delete_files || 0}</div>
            <div class="iceberg-stat-label">Delete Files</div>
          </div>
        </div>
        ${t.latest_snapshot_ts ? `<div class="iceberg-card-detail">Latest snapshot: ${new Date(t.latest_snapshot_ts).toLocaleString()}</div>` : ''}
      </div>`;
    }).join('')}</div>`;
  },

  // ── Watched Tables Settings ───────────────────────────────

  _initWatchedTables() {
    const addBtn = document.getElementById('add-watched-table-btn');
    if (!addBtn) return;

    addBtn.addEventListener('click', async () => {
      console.log("Add table clicked!");
      const select = document.getElementById('watched-table-path');
      const path = select.value.trim();
      console.log("Selected path:", path);
      if (!path) {
        console.warn("No path selected");
        return;
      }

      try {
        console.log("Sending POST to /api/watched-tables");
        await App.api('/api/watched-tables', 'POST', { table_path: path });
        // Optionally unselect
        select.value = '';
        console.log("Reloading watched tables");
        this._loadWatchedTables();
      } catch (e) {
        console.error('Failed to add watched table:', e);
      }
    });

    this._loadWatchedTables();
    this._loadAvailableTables();
  },

  async _loadAvailableTables() {
    try {
      const select = document.getElementById('watched-table-path');
      const tablesBySchema = await App.api('/api/available-tables');
      if (tablesBySchema.error) {
        select.innerHTML = `<option value="">Error loading tables</option>`;
        return;
      }
      
      let html = '<option value="">Select a table to watch...</option>';
      for (const [schema, tables] of Object.entries(tablesBySchema)) {
        if (!tables || tables.length === 0) continue;
        html += `<optgroup label="${App.escapeHtml(schema || 'Default')}">`;
        tables.forEach(t => {
          // Replace double quotes with &quot; so they don't break the HTML attribute
          const safePath = (t.path || '').replace(/"/g, '&quot;');
          html += `<option value="${safePath}">${App.escapeHtml(t.name)}</option>`;
        });
        html += `</optgroup>`;
      }
      select.innerHTML = html;
    } catch (e) {
      console.warn('Failed to load available tables:', e);
      document.getElementById('watched-table-path').innerHTML = `<option value="">Failed to load tables</option>`;
    }
  },

  async _loadWatchedTables() {
    try {
      const tables = await App.api('/api/watched-tables');
      const list = document.getElementById('watched-tables-list');
      if (!list) return;

      if (!tables || !tables.length) {
        list.innerHTML = '<div style="color:var(--text-muted);font-size:0.85rem">No tables configured yet.</div>';
        return;
      }

      list.innerHTML = tables.map(t => `
        <div class="watched-table-item">
          <span class="watched-table-path">${App.escapeHtml(t.table_path)}</span>
          <button class="btn btn-danger btn-sm" onclick="Dashboard._removeWatchedTable(${t.id})">Remove</button>
        </div>
      `).join('');
    } catch (e) {
      console.warn('Failed to load watched tables:', e);
    }
  },

  async _removeWatchedTable(id) {
    try {
      await App.api(`/api/watched-tables/${id}`, 'DELETE');
      this._loadWatchedTables();
    } catch (e) {
      console.warn('Failed to remove watched table:', e);
    }
  }
};
