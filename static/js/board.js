/**
 * Canvas rendering and pointer input.
 *
 * Coordinates are stored in a fixed 1600x900 logical space, never in screen
 * pixels. Two people on a laptop and a phone must agree on where a stroke sits,
 * so the conversion to screen space happens only at draw time.
 *
 * Committed strokes are painted once onto an offscreen base canvas. Appending a
 * stroke draws just that stroke; only undo, redo, restyle, and clear force a full
 * rebuild. Without that split, a room with 100k strokes would re-render its
 * entire history on every pointer move.
 */

export const LOGICAL_W = 1600;
export const LOGICAL_H = 900;

export class Board {
  constructor(canvas, cursorLayer) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.cursorLayer = cursorLayer;

    this.base = document.createElement('canvas');
    this.baseCtx = this.base.getContext('2d');

    this.strokes = [];            // committed and active
    this.previews = new Map();    // userId -> {tool, style, points}
    this.cursors = new Map();     // userId -> {x, y, color, userName, el}
    this.snapshotImage = null;    // HTMLImageElement drawn beneath everything
    this.background = '#ffffff';

    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.scale = 1;
    this.frameQueued = false;

    this._resize();
    window.addEventListener('resize', () => this._resize());
  }

  // ------------------------------------------------------------- geometry
  _resize() {
    const wrap = this.canvas.parentElement;
    const pad = 32;
    const availW = wrap.clientWidth - pad;
    const availH = wrap.clientHeight - pad;
    this.scale = Math.min(availW / LOGICAL_W, availH / LOGICAL_H);

    const cssW = LOGICAL_W * this.scale;
    const cssH = LOGICAL_H * this.scale;
    this.canvas.style.width = `${cssW}px`;
    this.canvas.style.height = `${cssH}px`;
    this.canvas.width = Math.round(cssW * this.dpr);
    this.canvas.height = Math.round(cssH * this.dpr);

    this.base.width = Math.round(LOGICAL_W * this.dpr);
    this.base.height = Math.round(LOGICAL_H * this.dpr);

    this.rebuild();
  }

  /** Screen event -> logical canvas coordinates. */
  toLogical(evt) {
    const r = this.canvas.getBoundingClientRect();
    return {
      x: (evt.clientX - r.left) / this.scale,
      y: (evt.clientY - r.top) / this.scale,
    };
  }

  /** Logical coordinates -> position within the cursor overlay. */
  toScreen(x, y) {
    const r = this.canvas.getBoundingClientRect();
    const w = this.cursorLayer.getBoundingClientRect();
    return { left: r.left - w.left + x * this.scale, top: r.top - w.top + y * this.scale };
  }

  // -------------------------------------------------------------- drawing
  _path(ctx, stroke) {
    const s = stroke.style || {};
    ctx.save();
    ctx.scale(this.dpr, this.dpr);
    ctx.globalAlpha = s.opacity ?? 1;
    ctx.globalCompositeOperation = s.blend === 'destination-out' ? 'destination-out' : 'source-over';
    ctx.strokeStyle = s.color || '#111827';
    ctx.fillStyle = s.color || '#111827';
    ctx.lineWidth = s.width ?? 3;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    const pts = stroke.points;
    const g = stroke.geometry;

    if (stroke.tool === 'text' && stroke.text) {
      ctx.font = stroke.font || '16px Inter, sans-serif';
      ctx.textBaseline = 'top';
      const at = pts?.[0] || { x: g?.x ?? 0, y: g?.y ?? 0 };
      ctx.fillText(stroke.text, at.x, at.y);
    } else if (stroke.tool === 'rect' && g) {
      ctx.strokeRect(g.x, g.y, g.w, g.h);
    } else if (stroke.tool === 'ellipse' && g) {
      ctx.beginPath();
      ctx.ellipse(g.x + g.w / 2, g.y + g.h / 2, Math.abs(g.w / 2), Math.abs(g.h / 2), 0, 0, Math.PI * 2);
      ctx.stroke();
    } else if (stroke.tool === 'line' && g) {
      ctx.beginPath();
      ctx.moveTo(g.x, g.y);
      ctx.lineTo(g.x + g.w, g.y + g.h);
      ctx.stroke();
    } else if (pts && pts.length) {
      ctx.beginPath();
      if (pts.length === 1) {
        // A tap still has to leave a mark.
        ctx.arc(pts[0].x, pts[0].y, (s.width ?? 3) / 2, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.moveTo(pts[0].x, pts[0].y);
        // Quadratic midpoints smooth the polyline without storing extra points.
        for (let i = 1; i < pts.length - 1; i++) {
          const mx = (pts[i].x + pts[i + 1].x) / 2;
          const my = (pts[i].y + pts[i + 1].y) / 2;
          ctx.quadraticCurveTo(pts[i].x, pts[i].y, mx, my);
        }
        const last = pts[pts.length - 1];
        ctx.lineTo(last.x, last.y);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  /** Repaint the offscreen base from scratch. Only needed on structural change. */
  rebuild() {
    this.baseCtx.setTransform(1, 0, 0, 1, 0, 0);
    this.baseCtx.clearRect(0, 0, this.base.width, this.base.height);
    if (this.snapshotImage) {
      this.baseCtx.drawImage(this.snapshotImage, 0, 0, this.base.width, this.base.height);
    }
    for (const stroke of this.strokes) this._path(this.baseCtx, stroke);
    this.invalidate();
  }

  appendStroke(stroke) {
    this.strokes.push(stroke);
    this._path(this.baseCtx, stroke);   // incremental: one stroke, not the history
    this.invalidate();
  }

  setStrokes(strokes) {
    this.strokes = strokes.filter((s) => s.active !== false);
    this.rebuild();
  }

  removeStroke(strokeId) {
    const before = this.strokes.length;
    this.strokes = this.strokes.filter((s) => s.id !== strokeId);
    if (this.strokes.length !== before) this.rebuild();  // a hole appeared; full repaint
  }

  replaceStroke(stroke) {
    const i = this.strokes.findIndex((s) => s.id === stroke.id);
    if (i >= 0) { this.strokes[i] = stroke; this.rebuild(); }
  }

  clear() {
    this.strokes = [];
    this.snapshotImage = null;
    this.rebuild();
  }

  setSnapshot(dataUrl) {
    return new Promise((resolve) => {
      if (!dataUrl) { this.snapshotImage = null; resolve(); return; }
      const img = new Image();
      img.onload = () => { this.snapshotImage = img; this.rebuild(); resolve(); };
      img.onerror = () => resolve();
      img.src = dataUrl;
    });
  }

  setPreview(userId, preview) {
    if (!preview || !preview.points?.length) this.previews.delete(userId);
    else this.previews.set(userId, preview);
    this.invalidate();
  }

  // ------------------------------------------------------------ compositing
  invalidate() {
    if (this.frameQueued) return;
    this.frameQueued = true;
    requestAnimationFrame(() => { this.frameQueued = false; this._paint(); });
  }

  _paint() {
    const ctx = this.ctx;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = this.background;
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.drawImage(this.base, 0, 0, this.canvas.width, this.canvas.height);

    // In-flight strokes live on top and are never written to the base.
    const sx = this.canvas.width / this.base.width;
    ctx.save();
    ctx.scale(sx, sx);
    for (const p of this.previews.values()) this._path(ctx, p);
    ctx.restore();
  }

  /** Snapshot the committed canvas only, at logical resolution. */
  exportSnapshot() {
    const out = document.createElement('canvas');
    out.width = LOGICAL_W;
    out.height = LOGICAL_H;
    const c = out.getContext('2d');
    c.fillStyle = this.background;
    c.fillRect(0, 0, LOGICAL_W, LOGICAL_H);
    c.drawImage(this.base, 0, 0, LOGICAL_W, LOGICAL_H);
    return out.toDataURL('image/png');
  }

  // --------------------------------------------------------------- cursors
  updateCursor({ userId, userName, color, x, y }) {
    let entry = this.cursors.get(userId);
    if (!entry) {
      const el = document.createElement('div');
      el.className = 'remote-cursor';
      el.innerHTML = `<div class="arrow">➤</div><div class="tag"></div>`;
      this.cursorLayer.appendChild(el);
      entry = { el };
      this.cursors.set(userId, entry);
    }
    entry.el.querySelector('.arrow').style.color = color;
    const tag = entry.el.querySelector('.tag');
    tag.textContent = userName;
    tag.style.background = color;
    const pos = this.toScreen(x, y);
    entry.el.style.left = `${pos.left}px`;
    entry.el.style.top = `${pos.top}px`;
    entry.el.hidden = x < 0 || y < 0;
  }

  dropCursor(userId) {
    const entry = this.cursors.get(userId);
    if (entry) { entry.el.remove(); this.cursors.delete(userId); }
    this.previews.delete(userId);
    this.invalidate();
  }
}
