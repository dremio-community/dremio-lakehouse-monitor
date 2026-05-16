/**
 * Canvas-based charting for Dremio Lakehouse Monitor.
 * Lightweight sparklines, gauges, and line charts.
 */

const Charts = {
  /** Draw a health ring gauge (0-100). */
  healthRing(canvasId, score, opts = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const size = opts.size || 100;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = size + 'px';
    canvas.style.height = size + 'px';
    ctx.scale(dpr, dpr);

    const cx = size / 2, cy = size / 2, r = size / 2 - 8;
    const lineWidth = 8;
    const startAngle = -Math.PI / 2;
    const endAngle = startAngle + (2 * Math.PI * (score / 100));

    // Background ring
    ctx.clearRect(0, 0, size, size);
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, 2 * Math.PI);
    ctx.strokeStyle = '#30363d';
    ctx.lineWidth = lineWidth;
    ctx.stroke();

    // Score ring
    const color = score >= 80 ? '#3fb950' : score >= 50 ? '#d29922' : '#f85149';
    ctx.beginPath();
    ctx.arc(cx, cy, r, startAngle, endAngle);
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.lineCap = 'round';
    ctx.stroke();

    // Center text
    ctx.fillStyle = color;
    ctx.font = `bold ${size * 0.28}px Inter, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(score + '%', cx, cy);
  },

  /** Draw a sparkline from an array of values. */
  sparkline(canvasId, data, opts = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !data || data.length < 2) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const w = opts.width || canvas.clientWidth || 260;
    const h = opts.height || 40;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const pad = 2;
    const min = Math.min(...data);
    const max = Math.max(...data) || 1;
    const range = max - min || 1;

    const points = data.map((v, i) => ({
      x: pad + (i / (data.length - 1)) * (w - pad * 2),
      y: h - pad - ((v - min) / range) * (h - pad * 2)
    }));

    // Gradient fill
    const gradient = ctx.createLinearGradient(0, 0, 0, h);
    const color = opts.color || '#58a6ff';
    gradient.addColorStop(0, color + '33');
    gradient.addColorStop(1, color + '00');

    ctx.beginPath();
    ctx.moveTo(points[0].x, h);
    points.forEach(p => ctx.lineTo(p.x, p.y));
    ctx.lineTo(points[points.length - 1].x, h);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Line
    ctx.beginPath();
    points.forEach((p, i) => i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y));
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // End dot
    const last = points[points.length - 1];
    ctx.beginPath();
    ctx.arc(last.x, last.y, 3, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
  },

  /** Draw a memory gauge bar (horizontal). */
  memoryBar(container, label, current, max) {
    const pct = max > 0 ? Math.round((current / max) * 100) : 0;
    const cls = pct > 90 ? 'critical' : pct > 75 ? 'warn' : '';
    const curMB = Math.round(current / (1024 * 1024));
    const maxMB = Math.round(max / (1024 * 1024));

    return `
      <div class="memory-node">
        <span class="memory-node-name">${label}</span>
        <div class="memory-bar-track">
          <div class="memory-bar-fill ${cls}" style="width:${pct}%"></div>
          <span class="memory-bar-label">${pct}% (${curMB}/${maxMB} MB)</span>
        </div>
      </div>`;
  },

  /** Draw a donut chart with labeled segments. */
  donutChart(canvasId, segments, opts = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const size = opts.size || 120;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = size + 'px';
    canvas.style.height = size + 'px';
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, size, size);

    const cx = size / 2, cy = size / 2, r = size / 2 - 10;
    const lineWidth = 14;
    const total = segments.reduce((s, seg) => s + seg.value, 0);
    if (total === 0) {
      // Empty ring
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, 2 * Math.PI);
      ctx.strokeStyle = '#30363d';
      ctx.lineWidth = lineWidth;
      ctx.stroke();
      ctx.fillStyle = '#484f58';
      ctx.font = `500 ${size * 0.14}px Inter, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('No data', cx, cy);
      return;
    }

    let startAngle = -Math.PI / 2;
    // Background ring
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, 2 * Math.PI);
    ctx.strokeStyle = '#30363d';
    ctx.lineWidth = lineWidth;
    ctx.stroke();

    // Segment arcs
    segments.forEach(seg => {
      if (seg.value <= 0) return;
      const sliceAngle = (seg.value / total) * 2 * Math.PI;
      ctx.beginPath();
      ctx.arc(cx, cy, r, startAngle, startAngle + sliceAngle);
      ctx.strokeStyle = seg.color;
      ctx.lineWidth = lineWidth;
      ctx.lineCap = 'butt';
      ctx.stroke();
      startAngle += sliceAngle;
    });

    // Center text
    ctx.fillStyle = '#e6edf3';
    ctx.font = `bold ${size * 0.22}px Inter, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(total.toString(), cx, cy - 6);
    ctx.fillStyle = '#8b949e';
    ctx.font = `400 ${size * 0.1}px Inter, sans-serif`;
    ctx.fillText('queries', cx, cy + 12);
  },

  /** Draw a horizontal bar chart (e.g., top users). */
  horizontalBarChart(containerId, items, opts = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!items || !items.length) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-text">No data available</div></div>';
      return;
    }
    const maxVal = Math.max(...items.map(i => i.value)) || 1;
    const barColor = opts.color || '#58a6ff';
    const barBg = opts.bgColor || 'rgba(88,166,255,0.1)';

    container.innerHTML = items.map(item => {
      const pct = Math.round((item.value / maxVal) * 100);
      const sublabel = item.sublabel || '';
      return `
        <div class="hbar-item">
          <div class="hbar-label">
            <span class="hbar-name">${App.escapeHtml(item.label)}</span>
            <span class="hbar-value">${item.value}</span>
          </div>
          <div class="hbar-track" style="background:${barBg}">
            <div class="hbar-fill" style="width:${pct}%;background:${barColor}"></div>
          </div>
          ${sublabel ? `<div class="hbar-sublabel">${sublabel}</div>` : ''}
        </div>`;
    }).join('');
  },

  /** Draw a histogram bar chart on canvas. */
  histogramChart(canvasId, buckets, counts, opts = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const w = opts.width || canvas.clientWidth || 500;
    const h = opts.height || 180;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const padLeft = 40, padRight = 10, padTop = 10, padBottom = 40;
    const chartW = w - padLeft - padRight;
    const chartH = h - padTop - padBottom;
    const maxVal = Math.max(...counts, 1);
    const barWidth = (chartW / counts.length) - 6;
    const gap = 6;

    const colors = ['#3fb950', '#58a6ff', '#bc8cff', '#d29922', '#f0883e', '#f85149'];

    // Y-axis gridlines
    ctx.strokeStyle = '#21262d';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padTop + (chartH * i / 4);
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(w - padRight, y);
      ctx.stroke();

      ctx.fillStyle = '#484f58';
      ctx.font = '10px Inter, sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      const label = Math.round(maxVal * (4 - i) / 4);
      ctx.fillText(label.toString(), padLeft - 6, y);
    }

    // Bars
    counts.forEach((count, i) => {
      const x = padLeft + i * (barWidth + gap) + gap / 2;
      const barH = (count / maxVal) * chartH;
      const y = padTop + chartH - barH;
      const color = colors[i % colors.length];

      // Bar with rounded top
      const radius = Math.min(4, barWidth / 2);
      ctx.beginPath();
      ctx.moveTo(x, y + radius);
      ctx.arcTo(x, y, x + radius, y, radius);
      ctx.arcTo(x + barWidth, y, x + barWidth, y + radius, radius);
      ctx.lineTo(x + barWidth, padTop + chartH);
      ctx.lineTo(x, padTop + chartH);
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();

      // Bar glow
      ctx.shadowColor = color;
      ctx.shadowBlur = 6;
      ctx.fill();
      ctx.shadowBlur = 0;

      // Count label on top
      if (count > 0) {
        ctx.fillStyle = '#e6edf3';
        ctx.font = 'bold 11px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(count.toString(), x + barWidth / 2, y - 3);
      }

      // X-axis label
      ctx.fillStyle = '#8b949e';
      ctx.font = '10px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(buckets[i] || '', x + barWidth / 2, padTop + chartH + 6);
    });
  },

  /** Draw a horizontal stacked bar chart (e.g., query lifecycle). */
  stackedBarChart(containerId, segments, opts = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const total = segments.reduce((s, seg) => s + Math.max(0, seg.value), 0);
    if (total <= 0) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-text">No data</div></div>';
      return;
    }
    container.innerHTML = `
      <div class="stacked-bar-wrapper">
        <div class="stacked-bar">
          ${segments.map(seg => {
            const pct = Math.max(0, (seg.value / total) * 100);
            if (pct < 0.5) return '';
            return `<div class="stacked-segment" style="width:${pct}%;background:${seg.color}" title="${seg.label}: ${seg.displayValue || Math.round(seg.value)}"></div>`;
          }).join('')}
        </div>
        <div class="stacked-legend">
          ${segments.filter(s => s.value > 0).map(seg => `
            <div class="stacked-legend-item">
              <span class="legend-dot" style="background:${seg.color}"></span>
              <span class="stacked-legend-label">${seg.label}</span>
              <span class="stacked-legend-value">${seg.displayValue || Math.round(seg.value) + 'ms'}</span>
            </div>
          `).join('')}
        </div>
      </div>`;
  },

  /** Draw a multi-series line chart on canvas. */
  lineChart(canvasId, datasets, opts = {}) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const w = opts.width || canvas.clientWidth || 400;
    const h = opts.height || 120;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const padLeft = 45, padRight = 10, padTop = 10, padBottom = 25;
    const chartW = w - padLeft - padRight;
    const chartH = h - padTop - padBottom;

    // Find global min/max across all datasets
    let allVals = [];
    datasets.forEach(ds => allVals.push(...ds.data));
    if (allVals.length === 0) return;
    let minVal = opts.minY !== undefined ? opts.minY : Math.min(...allVals);
    let maxVal = opts.maxY !== undefined ? opts.maxY : Math.max(...allVals);
    if (maxVal === minVal) maxVal = minVal + 1;

    // Y-axis gridlines
    ctx.strokeStyle = '#21262d';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 3; i++) {
      const y = padTop + (chartH * i / 3);
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(w - padRight, y);
      ctx.stroke();

      ctx.fillStyle = '#484f58';
      ctx.font = '10px Inter, sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      const label = Math.round(maxVal - (maxVal - minVal) * i / 3);
      ctx.fillText(opts.formatY ? opts.formatY(label) : label.toString(), padLeft - 6, y);
    }

    // Draw each dataset
    datasets.forEach(ds => {
      if (!ds.data || ds.data.length < 2) return;
      const points = ds.data.map((v, i) => ({
        x: padLeft + (i / (ds.data.length - 1)) * chartW,
        y: padTop + chartH - ((v - minVal) / (maxVal - minVal)) * chartH
      }));

      // Fill area
      const gradient = ctx.createLinearGradient(0, padTop, 0, padTop + chartH);
      gradient.addColorStop(0, (ds.color || '#58a6ff') + '22');
      gradient.addColorStop(1, (ds.color || '#58a6ff') + '00');
      ctx.beginPath();
      ctx.moveTo(points[0].x, padTop + chartH);
      points.forEach(p => ctx.lineTo(p.x, p.y));
      ctx.lineTo(points[points.length - 1].x, padTop + chartH);
      ctx.closePath();
      ctx.fillStyle = gradient;
      ctx.fill();

      // Line
      ctx.beginPath();
      points.forEach((p, i) => i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y));
      ctx.strokeStyle = ds.color || '#58a6ff';
      ctx.lineWidth = 2;
      ctx.stroke();

      // End dot
      const last = points[points.length - 1];
      ctx.beginPath();
      ctx.arc(last.x, last.y, 3, 0, 2 * Math.PI);
      ctx.fillStyle = ds.color || '#58a6ff';
      ctx.fill();
    });

    // X-axis time labels
    if (opts.labels && opts.labels.length > 0) {
      ctx.fillStyle = '#484f58';
      ctx.font = '9px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      const step = Math.max(1, Math.floor(opts.labels.length / 5));
      for (let i = 0; i < opts.labels.length; i += step) {
        const x = padLeft + (i / (opts.labels.length - 1)) * chartW;
        ctx.fillText(opts.labels[i], x, padTop + chartH + 6);
      }
    }
  },

  /** Draw gauge bars for per-node memory pressure. */
  gaugeBar(containerId, items) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!items || !items.length) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-text">No nodes</div></div>';
      return;
    }
    container.innerHTML = items.map(item => {
      const pressure = item.pressure || 0;
      const statusClass = pressure > 90 ? 'critical' : pressure > 75 ? 'warn' : '';
      const statusLabel = pressure > 90 ? '🔴' : pressure > 75 ? '🟡' : '🟢';
      return `
        <div class="gauge-bar-item">
          <div class="gauge-bar-header">
            <span class="gauge-bar-name">${statusLabel} ${App.escapeHtml(item.label)}</span>
            <span class="gauge-bar-value ${statusClass ? 'text-' + statusClass : ''}">${pressure}%</span>
          </div>
          <div class="gauge-bar-track">
            <div class="gauge-bar-fill ${statusClass}" style="width:${Math.min(100, pressure)}%"></div>
          </div>
          <div class="gauge-bar-detail">
            Heap: ${item.heapPct || 0}% · Direct: ${item.directPct || 0}%
          </div>
        </div>`;
    }).join('');
  }
};
