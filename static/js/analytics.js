/**
 * Analytics panel: runs the aggregation pipelines and renders both the query and
 * its output, so a reviewer can see the pipeline that produced each number.
 */

const $ = (sel) => document.querySelector(sel);

export class Analytics {
  constructor(getRoomCode, toast) {
    this.getRoomCode = getRoomCode;
    this.toast = toast;
    this.catalogue = [];
    this.lastPipeline = null;
  }

  async init() {
    const res = await fetch('/api/analytics');
    this.catalogue = (await res.json()).pipelines;

    const select = $('#pipelineSelect');
    select.innerHTML = this.catalogue
      .map((p) => `<option value="${p.key}">${p.title}</option>`)
      .join('');
    select.addEventListener('change', () => this.renderMeta());

    $('#runPipelineBtn').addEventListener('click', () => this.run());
    $('#explainPipelineBtn').addEventListener('click', () => this.explain());
    $('#togglePipelineBtn').addEventListener('click', () => {
      const pre = $('#pipelineSource');
      pre.hidden = !pre.hidden;
      $('#togglePipelineBtn').textContent = pre.hidden ? 'Show pipeline' : 'Hide pipeline';
    });
    $('#benchBtn').addEventListener('click', () => this.benchmark());
    $('#statsBtn').addEventListener('click', () => this.stats());

    document.querySelectorAll('.ptab').forEach((tab) => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.ptab').forEach((t) => t.classList.toggle('active', t === tab));
        document.querySelectorAll('.panel-view').forEach((v) => {
          v.hidden = v.dataset.view !== tab.dataset.view;
        });
        if (tab.dataset.view === 'indexes') this.listIndexes();
      });
    });

    this.renderMeta();
  }

  current() {
    return this.catalogue.find((p) => p.key === $('#pipelineSelect').value);
  }

  renderMeta() {
    const p = this.current();
    if (!p) return;
    $('#pipelineMeta').innerHTML = `
      <div class="q">${escapeHtml(p.question)}</div>
      <div class="stages">
        <span class="stage">db.${p.collection}</span>
        ${p.stages.map((s) => `<span class="stage">${escapeHtml(s)}</span>`).join('')}
      </div>
      <div class="note">${escapeHtml(p.notes)}</div>`;
    $('#pipelineResult').innerHTML = '';
    $('#pipelineSource').hidden = true;
    $('#togglePipelineBtn').textContent = 'Show pipeline';
  }

  async run() {
    const p = this.current();
    const url = `/api/analytics/${p.key}?room=${encodeURIComponent(this.getRoomCode())}`;
    $('#pipelineResult').innerHTML = '<p class="muted">running…</p>';
    const res = await fetch(url);
    if (!res.ok) {
      $('#pipelineResult').innerHTML = `<p class="lose">${escapeHtml((await res.json()).detail)}</p>`;
      return;
    }
    const data = await res.json();
    $('#pipelineSource').textContent = JSON.stringify(data.pipeline, null, 2);

    const timing = `<div class="timing">${data.resultCount} rows in ${data.elapsedMs} ms</div>`;
    const body = p.chart === 'facet' ? renderFacet(data.results[0] || {}) : renderRows(data.results, p);
    $('#pipelineResult').innerHTML = timing + body;
  }

  async explain() {
    const p = this.current();
    const url = `/api/analytics/${p.key}/explain?room=${encodeURIComponent(this.getRoomCode())}`;
    const res = await fetch(url);
    const data = await res.json();
    const s = data.summary;
    $('#pipelineResult').innerHTML = `
      <h4>Query plan</h4>
      ${kv('Scan type', `<span class="${s.usedIndex ? 'win' : 'lose'}">${s.scanType}</span>`)}
      ${kv('Index used', s.indexName || '— none —')}
      ${kv('Key pattern', s.keyPattern ? JSON.stringify(s.keyPattern) : '—')}
      ${kv('Docs examined', fmt(s.totalDocsExamined))}
      ${kv('Keys examined', fmt(s.totalKeysExamined))}
      ${kv('Docs returned', fmt(s.nReturned))}
      ${kv('Server time', `${fmt(s.executionTimeMillis)} ms`)}`;
  }

  async benchmark() {
    const target = $('#benchResult');
    target.innerHTML = '<p class="muted">dropping indexes and timing… this takes a few seconds</p>';
    const res = await fetch(`/api/admin/benchmark?room=${encodeURIComponent(this.getRoomCode())}`, {
      method: 'POST',
    });
    if (!res.ok) { target.innerHTML = '<p class="lose">benchmark failed</p>'; return; }
    const data = await res.json();

    target.innerHTML = Object.entries(data.comparison).map(([name, c]) => `
      <h4>${escapeHtml(name.replace(/_/g, ' '))}</h4>
      <p class="hint">${escapeHtml(c.why)}</p>
      <table>
        <tr><th></th><th>no index</th><th>with index</th></tr>
        <tr><td>time</td><td class="lose">${c.withoutIndex.ms} ms</td><td class="win">${c.withIndex.ms} ms</td></tr>
        <tr><td>plan</td><td class="lose">${c.withoutIndex.scanType}</td><td class="win">${c.withIndex.scanType}</td></tr>
        <tr><td>docs examined</td><td class="lose">${fmt(c.withoutIndex.docsExamined)}</td><td class="win">${fmt(c.withIndex.docsExamined)}</td></tr>
        <tr><td>index</td><td>—</td><td>${escapeHtml(c.withIndex.indexName || '—')}</td></tr>
        <tr><td>speedup</td><td colspan="2" class="win">${c.speedup ? `${c.speedup}x` : 'n/a'}</td></tr>
      </table>`).join('');
  }

  async listIndexes() {
    const res = await fetch('/api/admin/indexes');
    const data = await res.json();
    $('#indexList').innerHTML = Object.entries(data).map(([coll, idx]) => `
      <h4>db.${escapeHtml(coll)}</h4>
      <table>
        <tr><th>name</th><th>key</th><th>unique</th></tr>
        ${idx.map((i) => `<tr>
          <td>${escapeHtml(i.name)}</td>
          <td>${escapeHtml(JSON.stringify(i.key))}</td>
          <td>${i.unique ? 'yes' : ''}</td></tr>`).join('')}
      </table>`).join('');
  }

  async stats() {
    const res = await fetch('/api/admin/stats');
    const data = await res.json();
    $('#statsResult').innerHTML = Object.entries(data).map(([coll, s]) => `
      <h4>db.${escapeHtml(coll)}</h4>
      ${kv('Documents', fmt(s.documents))}
      ${kv('Data size', `${fmt(s.dataSizeKB)} KB`)}
      ${kv('Storage size', `${fmt(s.storageSizeKB)} KB`)}
      ${kv('Index size', `${fmt(s.indexSizeKB)} KB`)}
      ${kv('Avg document', `${fmt(s.avgDocSizeBytes)} B`)}
      <table>
        <tr><th>index</th><th>KB</th></tr>
        ${Object.entries(s.indexSizes).map(([n, kb]) => `<tr><td>${escapeHtml(n)}</td><td>${fmt(kb)}</td></tr>`).join('')}
      </table>`).join('');
  }
}

// ------------------------------------------------------------------ helpers
function renderRows(rows, spec) {
  if (!rows.length) return '<p class="muted">No documents matched. Draw something, or seed the room.</p>';
  const cols = Object.keys(rows[0]);

  let bars = '';
  if (spec.chart === 'bar' || spec.chart === 'line') {
    const metric = cols.find((c) => ['count', 'strokes', 'docs', 'totalKB'].includes(c));
    if (metric) {
      const max = Math.max(...rows.map((r) => Number(r[metric]) || 0)) || 1;
      const labelCol = cols.find((c) => typeof rows[0][c] === 'string') || cols[0];
      bars = `<table>${rows.map((r) => `
        <tr>
          <td>${escapeHtml(String(r[labelCol]))}</td>
          <td style="width:100%"><div class="bar" style="width:${(Number(r[metric]) / max) * 100}%"></div></td>
          <td>${fmt(r[metric])}</td>
        </tr>`).join('')}</table>`;
    }
  }

  const table = `<table>
    <tr>${cols.map((c) => `<th>${escapeHtml(c)}</th>`).join('')}</tr>
    ${rows.slice(0, 60).map((r) => `<tr>${cols.map((c) => `<td>${cell(c, r[c])}</td>`).join('')}</tr>`).join('')}
  </table>`;

  return bars + table;
}

function renderFacet(facets) {
  return Object.entries(facets).map(([name, rows]) => `
    <h4>${escapeHtml(name)}</h4>
    ${Array.isArray(rows) && rows.length
      ? renderRows(rows, { chart: 'table' })
      : '<p class="muted">empty</p>'}`).join('');
}

function cell(col, value) {
  if (col === 'color' && typeof value === 'string' && value.startsWith('#')) {
    return `<span class="swatch-inline" style="background:${escapeHtml(value)}"></span>${escapeHtml(value)}`;
  }
  if (Array.isArray(value)) return escapeHtml(value.join(', '));
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (typeof value === 'number') return fmt(value);
  return escapeHtml(String(value));
}

const kv = (k, v) => `<div class="kv"><span>${escapeHtml(k)}</span><span>${v}</span></div>`;
const fmt = (n) => (typeof n === 'number' ? n.toLocaleString() : n ?? '—');

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
