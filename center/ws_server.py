# -*- coding: utf-8 -*-
"""
ws_server.py
纯标准库实现的 WebSocket 服务端（RFC6455），无需第三方依赖。
- 每个连接一个线程，收消息后回调 on_message(client, obj)。
- server.broadcast(obj, exclude) 向所有客户端广播（线程安全）。

display（Godot）与 controller（浏览器）都连到这里。
"""

import base64
import hashlib
import json
import socket
import struct
import threading

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT = 0x0
OP_TEXT = 0x1
OP_BIN = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA


class WebSocketClient:
    def __init__(self, conn, addr, server):
        self.conn = conn
        self.addr = addr
        self.server = server
        self._send_lock = threading.Lock()
        self._closed = False
        self._id = f"{addr[0]}:{addr[1]}"

    @property
    def id(self):
        return self._id

    def handshake(self):
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = self.conn.recv(1024)
            if not chunk:
                return False
            data += chunk
            if len(data) > 16384:
                return False
        head = data.split(b"\r\n\r\n", 1)[0].decode("latin-1")
        lines = head.split("\r\n")
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        key = headers.get("sec-websocket-key")
        if not key:
            return False
        accept = base64.b64encode(
            hashlib.sha1((key + GUID).encode("latin-1")).digest()).decode("latin-1")
        resp = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        )
        self.conn.sendall(resp.encode("latin-1"))
        return True

    # ---- 接收 -------------------------------------------------------------
    def run(self):
        frag_op = None
        frag = b""
        try:
            while not self._closed:
                frame = self._read_frame()
                if frame is None:
                    break
                fin, opcode, payload = frame
                if opcode == OP_CLOSE:
                    break
                if opcode == OP_PING:
                    self._send_frame(OP_PONG, payload)
                    continue
                if opcode == OP_PONG:
                    continue
                if opcode in (OP_TEXT, OP_BIN):
                    if fin:
                        msg = payload
                    else:
                        frag_op, frag = opcode, payload
                        continue
                elif opcode == OP_CONT:
                    frag += payload
                    if not fin:
                        continue
                    msg, opcode = frag, frag_op
                    frag = b""
                else:
                    continue
                if opcode == OP_TEXT:
                    self._handle_text(msg)
        finally:
            self._closed = True
            self.server._remove(self)
            try:
                self.conn.close()
            except OSError:
                pass

    def _handle_text(self, raw):
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            print(f"[ws] 非法 JSON 来自 {self._id}: {e}")
            return
        cb = self.server.on_message
        if cb:
            try:
                cb(self, obj)
            except Exception as e:
                print(f"[ws] 处理消息出错: {e}")

    def _read_frame(self):
        hdr = self._recv_exact(2)
        if not hdr:
            return None
        b1, b2 = hdr[0], hdr[1]
        fin = bool(b1 & 0x80)
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        length = b2 & 0x7F
        if length == 126:
            ext = self._recv_exact(2)
            if ext is None:
                return None
            length = struct.unpack(">H", ext)[0]
        elif length == 127:
            ext = self._recv_exact(8)
            if ext is None:
                return None
            length = struct.unpack(">Q", ext)[0]
        mask = self._recv_exact(4) if masked else None
        if masked and mask is None:
            return None
        payload = self._recv_exact(length) if length else b""
        if payload is None:
            return None
        if masked:
            payload = bytes(payload[i] ^ mask[i % 4] for i in range(len(payload)))
        return fin, opcode, payload

    def _recv_exact(self, n):
        if n == 0:
            return b""
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = self.conn.recv(n - len(buf))
            except OSError:
                return None
            if not chunk:
                return None
            buf += chunk
        return bytes(buf)

    # ---- 发送 -------------------------------------------------------------
    def _send_frame(self, opcode, payload):
        with self._send_lock:
            if self._closed or self.conn is None:
                return
            header = bytearray()
            header.append(0x80 | opcode)
            n = len(payload)
            if n < 126:
                header.append(n)
            elif n < 65536:
                header.append(126)
                header += struct.pack(">H", n)
            else:
                header.append(127)
                header += struct.pack(">Q", n)
            try:
                self.conn.sendall(bytes(header) + payload)
            except OSError:
                self._closed = True

    def send_text(self, text):
        self._send_frame(OP_TEXT, text.encode("utf-8"))

    def send_json(self, obj):
        self.send_text(json.dumps(obj, ensure_ascii=False))

    def close(self, code=1000):
        if self._closed:
            return
        self._send_frame(OP_CLOSE, struct.pack(">H", code))
        self._closed = True
        try:
            self.conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


class WebSocketServer:
    def __init__(self, host, port, on_message=None, on_connect=None, on_disconnect=None):
        self.host = host
        self.port = port
        self.on_message = on_message
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self._sock = None
        self._clients = set()
        self._lock = threading.Lock()
        self._running = False

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(16)
        self._running = True
        threading.Thread(target=self._accept_loop, name="ws-accept", daemon=True).start()
        print(f"[ws] WebSocket 服务监听 ws://{self.host}:{self.port}")

    def stop(self):
        self._running = False
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass
        with self._lock:
            clients = list(self._clients)
        for c in clients:
            c.close()

    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self._sock.accept()
            except OSError:
                break
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            t = threading.Thread(
                target=self._serve, args=(conn, addr), name=f"ws-{addr[1]}", daemon=True)
            t.start()

    def _serve(self, conn, addr):
        client = WebSocketClient(conn, addr, self)
        if not client.handshake():
            try:
                conn.close()
            except OSError:
                pass
            return
        self._add(client)
        print(f"[ws] 客户端已连接 {client.id}")
        if self.on_connect:
            try:
                self.on_connect(client)
            except Exception as e:
                print(f"[ws] on_connect 出错: {e}")
        client.run()
        print(f"[ws] 客户端已断开 {client.id}")
        if self.on_disconnect:
            try:
                self.on_disconnect(client)
            except Exception as e:
                print(f"[ws] on_disconnect 出错: {e}")

    def _add(self, client):
        with self._lock:
            self._clients.add(client)

    def _remove(self, client):
        with self._lock:
            self._clients.discard(client)

    @property
    def client_count(self):
        with self._lock:
            return len(self._clients)

    @property
    def client_ids(self):
        with self._lock:
            return [c.id for c in self._clients]

    def broadcast(self, obj, exclude=None):
        with self._lock:
            clients = list(self._clients)
        for c in clients:
            if c is exclude:
                continue
            c.send_json(obj)
