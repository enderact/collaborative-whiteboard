/**
 * Application wiring: lobby, tool state, pointer handling, and the socket
 * protocol.
 *
 * Drawing is optimistic. The local canvas updates the instant a pointer lifts,
 * and the server's `ack` only backfills the authoritative sequence number and
 * document id. Waiting for the round trip before showing ink would make the pen
 * feel broken on any connection with real latency.
 */

import { Analytics } from './analytics.js';
import { Board } from './board.js';
import { Net } from './net.js';

const $ = (sel) => document.querySelector(sel);

const PALETTE = ['#111827', '#dc2626', '#2563eb', '#059669', '#d97706',
                 '#7c3aed', '#db2777', '#0891b2', '#65a30d', '#94a3b8'];

const state = {
  userId: localStorage.getItem('wb_userId') || `u_${Math.random().toString(36).slice(2, 10)}`,
  userName: localStorage.getItem('wb_userName') || '',
  room: null,
  tool: 'pen',
  color: PALETTE[0],
  width: 3,
  maxSeq: 0,
  strokesSinceSnapshot: 0,
  snapshotInterval: 500,
  drawing: null,
};
localStorage.setItem('wb_userId', state.userId);

let board;
let net;
let analytics;

// =============================================================== lobby
async function initLobby() {
  $('#nameInput').value = state.userName;

  $('#createBtn').addEventListener('click', createRoom);
  $('#joinBtn').addEventListener('click', () => joinRoom($('#codeInput').value.trim().toUpperCase()));
  $('#codeInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('#joinBtn').click(); });
  $('#nameInput').addEventListener('input', (e) => {
    state.userName = e.target.value.trim();
    localStorage.setItem('wb_userName', state.userName);
  });

  // A room code in the URL hash makes a second browser window one paste away,
  // which is how the cross-instance demo is driven.
  const hash = location.hash.slice(1).toUpperCase();
  await loadRecent();
  if (hash) joinRoom(hash);

  // Pasting a different board link into the address bar changes only the hash,
  // which does not reload the page, so the room switch has to be handled here.
  window.addEventListener('hashchange', () => {
    const next = location.hash.slice(1).toUpperCase();
    if (next && next !== state.room?.code) {
      net?.close();
      location.reload();
    }
  });
}

async function loadRecent() {
  try {
    const rooms = await (await fetch('/api/rooms?limit=8')).json();
    $('#recentList').innerHTML = rooms.length
      ? rooms.map((r) => `<li data-code="${r.code}">
          <span><span class="rcode">${r.code}</span> &nbsp;${escapeHtml(r.name)}</span>
          <span class="rmeta">${r.strokeCount} strokes</span></li>`).join('')
      : '<li class="muted">No boards yet — create one.</li>';
    $('#recentList').querySelectorAll('li[data-code]').forEach((li) =>
      li.addEventListener('click', () => joinRoom(li.dataset.code)));
  } catch {
    $('#recentList').innerHTML = '<li class="muted">Could not reach the API.</li>';
  }
}

function requireName() {
  if (!state.userName) {
    state.userName = `Guest ${Math.floor(Math.random() * 900 + 100)}`;
    $('#nameInput').value = state.userName;
    localStorage.setItem('wb_userName', state.userName);
  }
  return state.userName;
}

async function createRoom() {
  requireName();
  const res = await fetch('/api/rooms', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: `${state.userName}'s board`, createdBy: state.userId }),
  });
  if (!res.ok) return lobbyError('Could not create a board.');
  joinRoom((await res.json()).code);
}

async function joinRoom(code) {
  if (!code || code.length < 4) return lobbyError('Enter a 6-character room code.');
  requireName();
  const res = await fetch(`/api/rooms/${code}`);
  if (!res.ok) return lobbyError(`No board with code ${code}.`);

  state.room = await res.json();
  location.hash = state.room.code;

  $('#lobby').hidden = true;
  $('#board').hidden = false;

  if (!board) initBoard();
  $('#roomCode').textContent = state.room.code;
  $('#roomName').value = state.room.name;
  board.background = state.room.background || '#ffffff';

  net.connect(state.room.code, state.userId, state.userName);
  if (!analytics) {
    analytics = new Analytics(() => state.room.code, toast);
    await analytics.init();
  }
}

function lobbyError(msg) {
  const el = $('#lobbyError');
  el.textContent = msg;
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 4000);
}

// =============================================================== board setup
function initBoard() {
  board = new Board($('#canvas'), $('#cursorLayer'));
  net = new Net({ onMessage: handleMessage, onStatus: setStatus });

  buildSwatches();
  wireTools();
  wirePointer();
  wireButtons();
  wireKeyboard();
}

function buildSwatches() {
  $('#swatches').innerHTML = PALETTE
    .map((c, i) => `<div class="swatch ${i === 0 ? 'active' : ''}" data-color="${c}" style="background:${c}"></div>`)
    .join('');
  $('#swatches').querySelectorAll('.swatch').forEach((sw) =>
    sw.addEventListener('click', () => {
      state.color = sw.dataset.color;
      $('#swatches').querySelectorAll('.swatch').forEach((s) => s.classList.toggle('active', s === sw));
    }));
}

function wireTools() {
  document.querySelectorAll('.tool').forEach((btn) =>
    btn.addEventListener('click', () => selectTool(btn.dataset.tool)));

  $('#widthRange').addEventListener('input', (e) => {
    state.width = Number(e.target.value);
    $('#widthValue').textContent = state.width;
  });
}

function selectTool(tool) {
  state.tool = tool;
  document.querySelectorAll('.tool').forEach((b) => b.classList.toggle('active', b.dataset.tool === tool));
}

function currentStyle() {
  return {
    color: state.color,
    width: state.width,
    opacity: 1,
    // An eraser is a normal stroke that cuts a hole, so replay works on any
    // background instead of depending on painting white over white.
    blend: state.tool === 'eraser' ? 'destination-out' : 'source-over',
  };
}

// =============================================================== pointer input
function wirePointer() {
  const canvas = $('#canvas');

  canvas.addEventListener('pointerdown', (e) => {
    // Capture keeps a stroke alive if the pointer leaves the canvas mid-drag, but
    // it throws for pointer ids the browser is not currently tracking.
    try { canvas.setPointerCapture(e.pointerId); } catch { /* not capturable */ }
    const at = board.toLogical(e);

    if (state.tool === 'text') {
      const text = prompt('Text to place on the board:');
      if (text) commitStroke({ tool: 'text', style: currentStyle(), points: [at], text,
                               font: `${Math.max(12, state.width * 5)}px Inter, sans-serif` });
      return;
    }

    state.drawing = { start: at, points: [{ ...at, p: e.pressure || 0.5 }], seg: 0 };
    paintLocalPreview();
  });

  canvas.addEventListener('pointermove', (e) => {
    const at = board.toLogical(e);
    net.sendEphemeral({ type: 'cursor', x: at.x, y: at.y });
    if (!state.drawing) return;

    if (state.tool === 'pen' || state.tool === 'eraser') {
      state.drawing.points.push({ x: at.x, y: at.y, p: e.pressure || 0.5 });
    } else {
      state.drawing.end = at;
    }
    paintLocalPreview();
    broadcastPreview();
  });

  const finish = (e) => {
    if (!state.drawing) return;
    const d = state.drawing;
    state.drawing = null;
    board.setPreview(state.userId, null);

    if (state.tool === 'pen' || state.tool === 'eraser') {
      if (d.points.length === 0) return;
      commitStroke({ tool: state.tool, style: currentStyle(),
                     points: d.points.map(round3) });
    } else {
      const end = d.end || board.toLogical(e);
      const g = { x: d.start.x, y: d.start.y, w: end.x - d.start.x, h: end.y - d.start.y };
      if (Math.abs(g.w) < 2 && Math.abs(g.h) < 2) return;  // ignore stray taps
      commitStroke({ tool: state.tool, style: currentStyle(), geometry: roundGeom(g) });
    }
    // Tell everyone the in-flight preview is over.
    net.send({ type: 'preview', tool: state.tool, style: currentStyle(), points: [] });
  };

  canvas.addEventListener('pointerup', finish);
  canvas.addEventListener('pointercancel', finish);
  canvas.addEventListener('pointerleave', (e) => {
    if (!state.drawing) net.sendEphemeral({ type: 'cursor', x: -1, y: -1 });
    else finish(e);
  });
}

function paintLocalPreview() {
  const d = state.drawing;
  if (!d) return;
  if (state.tool === 'pen' || state.tool === 'eraser') {
    board.setPreview(state.userId, { tool: state.tool, style: currentStyle(), points: d.points });
  } else if (d.end) {
    board.setPreview(state.userId, {
      tool: state.tool, style: currentStyle(),
      geometry: { x: d.start.x, y: d.start.y, w: d.end.x - d.start.x, h: d.end.y - d.start.y },
      points: [],
    });
  }
}

function broadcastPreview() {
  const d = state.drawing;
  if (!d) return;
  // Only the newest few points go out; peers already hold the earlier ones.
  const payload = (state.tool === 'pen' || state.tool === 'eraser')
    ? d.points.slice(-24).map(round3)
    : [d.start, d.end].filter(Boolean).map(round3);
  net.sendEphemeral({ type: 'preview', tool: state.tool, style: currentStyle(), points: payload, seg: d.seg });
}

function commitStroke(stroke) {
  const clientMsgId = `${state.userId}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  // Render first, confirm second.
  board.appendStroke({ ...stroke, id: `pending-${clientMsgId}`, active: true });
  net.send({ type: 'commit', stroke: { ...stroke, clientMsgId } });
  state.strokesSinceSnapshot += 1;
  maybeSnapshot();
}

const round3 = (p) => ({ x: +p.x.toFixed(2), y: +p.y.toFixed(2), p: +(p.p ?? 0.5).toFixed(2) });
const roundGeom = (g) => ({ x: +g.x.toFixed(2), y: +g.y.toFixed(2), w: +g.w.toFixed(2), h: +g.h.toFixed(2) });

// =============================================================== buttons
function wireButtons() {
  $('#undoBtn').addEventListener('click', () => net.send({ type: 'undo' }));
  $('#redoBtn').addEventListener('click', () => net.send({ type: 'redo' }));

  $('#clearBtn').addEventListener('click', () => {
    if (confirm('Permanently delete every stroke in this room?')) net.send({ type: 'clear' });
  });

  $('#analyticsBtn').addEventListener('click', () => { $('#panel').hidden = !$('#panel').hidden; });
  $('#panelClose').addEventListener('click', () => { $('#panel').hidden = true; });

  $('#roomCode').addEventListener('click', async () => {
    await navigator.clipboard.writeText(location.href);
    toast('Board link copied — open it in another window to test live sync.');
  });

  // PATCH /api/rooms/{code}: the UPDATE verb, driven from the title field.
  let renameTimer;
  $('#roomName').addEventListener('input', (e) => {
    clearTimeout(renameTimer);
    renameTimer = setTimeout(async () => {
      await fetch(`/api/rooms/${state.room.code}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: e.target.value }),
      });
      toast('Board renamed.');
    }, 600);
  });

  $('#snapshotBtn').addEventListener('click', () => saveSnapshot(true));

  $('#compactBtn').addEventListener('click', async () => {
    const res = await fetch(`/api/rooms/${state.room.code}/compact`, { method: 'POST' });
    const data = await res.json();
    toast(`Hard-deleted ${data.purged} undone strokes.`);
  });

  $('#fitBtn').addEventListener('click', async () => {
    const res = await fetch(`/api/analytics/bounds?room=${state.room.code}`);
    const rows = (await res.json()).results;
    if (!rows.length) return toast('Nothing drawn yet.');
    const b = rows[0];
    toast(`Content spans ${b.width} x ${b.height} logical px across ${b.strokes} strokes.`);
  });

  $('#leaveBtn').addEventListener('click', () => {
    net.close();
    location.hash = '';
    location.reload();
  });
}

function wireKeyboard() {
  window.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    const combo = (e.ctrlKey || e.metaKey);
    if (combo && e.key.toLowerCase() === 'z' && !e.shiftKey) { e.preventDefault(); net.send({ type: 'undo' }); return; }
    if (combo && (e.key.toLowerCase() === 'y' || (e.shiftKey && e.key.toLowerCase() === 'z'))) {
      e.preventDefault(); net.send({ type: 'redo' }); return;
    }
    const map = { p: 'pen', e: 'eraser', l: 'line', r: 'rect', o: 'ellipse', t: 'text' };
    if (map[e.key.toLowerCase()]) selectTool(map[e.key.toLowerCase()]);
  });
}

// =============================================================== snapshots
function maybeSnapshot() {
  if (state.strokesSinceSnapshot < state.snapshotInterval) return;
  state.strokesSinceSnapshot = 0;
  saveSnapshot(false);
}

function saveSnapshot(announce) {
  net.send({ type: 'snapshot', upToSeq: state.maxSeq, image: board.exportSnapshot() });
  if (announce) toast('Snapshot saved — new joiners replay only strokes after it.');
}

// =============================================================== socket events
function handleMessage(msg) {
  switch (msg.type) {
    case 'init': {
      $('#instanceBadge').textContent = `instance ${msg.instance}`;
      state.maxSeq = msg.maxSeq || 0;
      state.snapshotInterval = msg.snapshotInterval || 500;
      setSeq(state.maxSeq);

      board.background = msg.room.background || '#ffffff';
      board.setSnapshot(msg.snapshotImage).then(() => board.setStrokes(msg.strokes));

      if (msg.truncated) {
        $('#snapshotHint').textContent =
          `Room holds ${msg.availableAfterSnapshot.toLocaleString()} strokes; only the newest `
          + `${msg.strokes.length.toLocaleString()} were replayed. Save a snapshot to load it in one read.`;
        toast(`History truncated: showing ${msg.strokes.length.toLocaleString()} of `
          + `${msg.availableAfterSnapshot.toLocaleString()} strokes.`);
      } else {
        $('#snapshotHint').textContent = msg.snapshot
          ? `Snapshot at seq ${msg.snapshot.upToSeq}; replayed ${msg.strokes.length} strokes after it.`
          : `No snapshot yet; replayed all ${msg.strokes.length} strokes.`;
      }

      (msg.presence || []).forEach((p) => {
        if (p.userId !== state.userId) board.updateCursor(p);
      });
      refreshPeople(msg.room.participants || []);
      break;
    }

    case 'ack':
      // Swap the optimistic placeholder for the server's identity.
      state.maxSeq = Math.max(state.maxSeq, msg.seq);
      setSeq(state.maxSeq);
      for (let i = board.strokes.length - 1; i >= 0; i--) {
        if (board.strokes[i].id === `pending-${msg.clientMsgId}`) {
          board.strokes[i].id = msg.id;
          board.strokes[i].seq = msg.seq;
          break;
        }
      }
      break;

    case 'stroke':
      board.appendStroke(msg.stroke);
      state.maxSeq = Math.max(state.maxSeq, msg.stroke.seq || 0);
      setSeq(state.maxSeq);
      break;

    case 'preview':
      if (msg.userId !== state.userId) board.setPreview(msg.userId, msg);
      break;

    case 'cursor':
      if (msg.userId !== state.userId) board.updateCursor(msg);
      break;

    case 'undo':
      board.removeStroke(msg.strokeId);
      if (msg.userId === state.userId) toast(`Undid stroke #${msg.seq}.`);
      break;

    case 'redo':
      if (msg.stroke) board.appendStroke(msg.stroke);
      break;

    case 'noop':
      toast(`Nothing to ${msg.of}.`);
      break;

    case 'cleared':
      board.clear();
      state.strokesSinceSnapshot = 0;
      toast(`Board cleared by ${msg.by} — ${msg.deleted} documents deleted.`);
      break;

    case 'strokeUpdated':
      board.replaceStroke(msg.stroke);
      break;

    case 'roomUpdated':
      state.room = msg.room;
      board.background = msg.room.background || '#ffffff';
      if (document.activeElement !== $('#roomName')) $('#roomName').value = msg.room.name;
      board.invalidate();
      break;

    case 'joined':
      toast(`${msg.userName} joined.`);
      refreshRoomMeta();
      break;

    case 'left':
      board.dropCursor(msg.userId);
      refreshRoomMeta();
      break;

    case 'snapshotSaved':
      $('#snapshotHint').textContent =
        `Snapshot at seq ${msg.snapshot.upToSeq} (${Math.round(msg.snapshot.bytes / 1024)} KB).`;
      break;
  }
}

async function refreshRoomMeta() {
  const res = await fetch(`/api/rooms/${state.room.code}`);
  if (!res.ok) return;
  const room = await res.json();
  refreshPeople(room.participants || []);
}

function refreshPeople(participants) {
  $('#peopleList').innerHTML = participants.length
    ? participants.map((p) => `<li>
        <span class="dot" style="background:${escapeHtml(p.color || '#94a3c4')}"></span>
        ${escapeHtml(p.userName)}${p.userId === state.userId ? ' <span class="muted">(you)</span>' : ''}
      </li>`).join('')
    : '<li class="muted">Just you.</li>';
}

function setStatus(status) {
  const badge = $('#statusBadge');
  badge.className = 'badge' + (status === 'live' ? ' live' : status === 'offline' ? ' down' : '');
  badge.textContent = status === 'live' ? 'live' : status;
}

function setSeq(seq) { $('#seqBadge').textContent = `seq ${seq}`; }

let toastTimer;
function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3200);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

initLobby();
