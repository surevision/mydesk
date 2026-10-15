/**
 * center.js
 * ---------------------------------------------------------------------------
 * 浏览器端与 center 的 WebSocket 客户端。
 * 提供：连接/断开、自动重连、应用层心跳（ping/pong）。
 *
 * 消息为 JSON 文本，形如 { "type": "on_battlefield_change", ... }。
 */
export class CenterClient {
  constructor() {
    this.ws = null;
    this.url = "";
    this.status = "disconnected"; // disconnected | connecting | connected
    this.autoReconnect = true;
    this.reconnectInterval = 3000; // ms
    this.heartbeatInterval = 5000; // ms
    this.heartbeatTimeout = 15000; // ms

    this._statusCbs = [];
    this._messageCbs = [];

    this._reconnectTimer = null;
    this._pingTimer = null;
    this._lastRecv = 0;
    this._manualClose = false;
  }

  // ---- 事件订阅 ----
  onStatus(cb) {
    this._statusCbs.push(cb);
    cb(this.status, this.url);
  }
  onMessage(cb) {
    this._messageCbs.push(cb);
  }
  _emitStatus() {
    this._statusCbs.forEach((cb) => cb(this.status, this.url));
  }
  _emitMessage(data) {
    this._messageCbs.forEach((cb) => cb(data));
  }

  /** 连接到指定 ip / port */
  connect(ip, port) {
    this.disconnect(true);
    this._manualClose = false;
    this.url = `ws://${ip}:${port}`;
    this._open();
  }

  _open() {
    if (this.ws) {
      try { this.ws.close(); } catch (e) { /* ignore */ }
      this.ws = null;
    }
    this.status = "connecting";
    this._emitStatus();

    let ws;
    try {
      ws = new WebSocket(this.url);
    } catch (e) {
      console.warn("[center] 创建 WebSocket 失败:", e);
      this._scheduleReconnect();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      this.status = "connected";
      this._lastRecv = Date.now();
      this._emitStatus();
      this._startHeartbeat();
    };

    ws.onmessage = (ev) => {
      this._lastRecv = Date.now();
      let data;
      try {
        data = JSON.parse(ev.data);
      } catch (e) {
        console.warn("[center] 收到非法 JSON:", ev.data);
        return;
      }
      // 心跳应答
      if (data && data.type === "ping") {
        this.send({ type: "pong" });
        return;
      }
      if (data && data.type === "pong") return;
      this._emitMessage(data);
    };

    ws.onerror = () => {
      // 具体错误信息浏览器不暴露，这里只做状态提示
    };

    ws.onclose = () => {
      this._stopHeartbeat();
      this.ws = null;
      if (this.status !== "disconnected") {
        this.status = "disconnected";
        this._emitStatus();
      }
      this._scheduleReconnect();
    };
  }

  /** 断开连接。manual=true 时不再自动重连 */
  disconnect(manual = true) {
    this._manualClose = manual;
    this._clearReconnect();
    this._stopHeartbeat();
    if (this.ws) {
      try { this.ws.onclose = null; this.ws.close(); } catch (e) { /* ignore */ }
      this.ws = null;
    }
    this.status = "disconnected";
    this._emitStatus();
  }

  /** 发送一个对象（自动 JSON 序列化） */
  send(obj) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn("[center] 未连接，消息未发送:", obj);
      return false;
    }
    try {
      this.ws.send(JSON.stringify(obj));
      return true;
    } catch (e) {
      console.warn("[center] 发送失败:", e);
      return false;
    }
  }

  /** 发送原始文本 */
  sendRaw(text) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    try { this.ws.send(text); return true; } catch (e) { return false; }
  }

  // ---- 心跳 ----
  _startHeartbeat() {
    this._stopHeartbeat();
    this._pingTimer = setInterval(() => {
      const now = Date.now();
      if (now - this._lastRecv > this.heartbeatTimeout) {
        console.warn("[center] 心跳超时，断开重连");
        try { this.ws && this.ws.close(); } catch (e) { /* ignore */ }
        return;
      }
      this.send({ type: "ping" });
    }, this.heartbeatInterval);
  }
  _stopHeartbeat() {
    if (this._pingTimer) {
      clearInterval(this._pingTimer);
      this._pingTimer = null;
    }
  }

  // ---- 重连 ----
  _scheduleReconnect() {
    if (!this.autoReconnect || this._manualClose) return;
    if (this._reconnectTimer) return;
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      if (!this._manualClose && this.autoReconnect) this._open();
    }, this.reconnectInterval);
  }
  _clearReconnect() {
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
  }
}
