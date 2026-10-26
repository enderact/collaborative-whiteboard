/**
 * WebSocket client with automatic reconnect.
 *
 * Cursor and preview messages are throttled to roughly 60 Hz. Without that, a
 * fast pointer generates hundreds of messages per second per user, all of which
 * would fan out through Redis to every other participant.
 */

export class Net {
  constructor({ onMessage, onStatus }) {
    this.onMessage = onMessage;
    this.onStatus = onStatus;
    this.ws = null;
    this.url = null;
    this.retry = 0;
    this.closing = false;
    this.lastEphemeral = 0;
  }

  connect(code, userId, userName) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const q = new URLSearchParams({ userId, userName });
    this.url = `${proto}://${location.host}/ws/${code}?${q}`;
    this._open();
  }

  _open() {
    this.onStatus('connecting');
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.retry = 0;
      this.onStatus('live');
      this.heartbeat = setInterval(() => this.send({ type: 'ping' }), 15000);
    };

    this.ws.onmessage = (evt) => {
      try { this.onMessage(JSON.parse(evt.data)); }
      catch (err) { console.error('bad frame', err); }
    };

    this.ws.onclose = () => {
      clearInterval(this.heartbeat);
      if (this.closing) return;
      this.onStatus('offline');
      // Backoff caps at 8s so a brief server restart recovers quickly.
      const delay = Math.min(8000, 500 * 2 ** this.retry++);
      setTimeout(() => this._open(), delay);
    };

    this.ws.onerror = () => this.onStatus('offline');
  }

  send(msg) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  /** Drop ephemeral traffic that arrives faster than one frame. */
  sendEphemeral(msg) {
    const now = performance.now();
    if (now - this.lastEphemeral < 16) return;
    this.lastEphemeral = now;
    this.send(msg);
  }

  close() {
    this.closing = true;
    clearInterval(this.heartbeat);
    this.ws?.close();
  }
}
