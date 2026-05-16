/**
 * Auto-reconnecting WebSocket client for Dremio Lakehouse Monitor.
 */

const WS = {
  _socket: null,
  _listeners: {},
  _reconnectDelay: 1000,
  _maxDelay: 30000,
  _connected: false,

  connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${location.host}/ws`;

    try {
      this._socket = new WebSocket(url);
    } catch (e) {
      console.warn('WebSocket connection failed:', e);
      this._scheduleReconnect();
      return;
    }

    this._socket.onopen = () => {
      console.log('WebSocket connected');
      this._connected = true;
      this._reconnectDelay = 1000;
      this._emit('connection', { connected: true });
    };

    this._socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this._emit(msg.type, msg.data);
        this._emit('any', msg);
      } catch (e) {
        console.warn('Invalid WS message:', e);
      }
    };

    this._socket.onclose = () => {
      this._connected = false;
      this._emit('connection', { connected: false });
      this._scheduleReconnect();
    };

    this._socket.onerror = () => {
      this._socket.close();
    };
  },

  _scheduleReconnect() {
    setTimeout(() => {
      console.log('WebSocket reconnecting...');
      this.connect();
    }, this._reconnectDelay);
    this._reconnectDelay = Math.min(this._reconnectDelay * 1.5, this._maxDelay);
  },

  on(event, callback) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(callback);
  },

  _emit(event, data) {
    (this._listeners[event] || []).forEach(cb => {
      try { cb(data); } catch (e) { console.error('WS listener error:', e); }
    });
  },

  get connected() { return this._connected; }
};
