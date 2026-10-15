# -*- coding: utf-8 -*-
"""
http_server.py
center 的管理页面 + 接口 + 视频预览。

接口：
  GET  /                 管理页面
  GET  /api/config       读取配置
  POST /api/config       保存配置（并重启识别）
  GET  /api/state        当前战场 + 运行状态
  GET  /api/status       仅运行状态
  GET  /frame/<cam_id>   MJPEG 预览流
  GET  /snapshot/<cam_id> 单帧 JPEG
"""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class AdminApp:
    """把各组件串起来，供 HTTP 处理函数调用。"""

    def __init__(self, cfg, store, recognition, ws_server, save_config_fn):
        self.cfg = cfg
        self.store = store
        self.recognition = recognition
        self.ws_server = ws_server
        self.save_config_fn = save_config_fn

    def status(self):
        st = self.recognition.status()
        st["ws_clients"] = self.ws_server.client_count
        st["ws_client_ids"] = self.ws_server.client_ids
        st["version"] = self.store.version
        return st

    def apply_config(self, new_cfg):
        cfg = self.save_config_fn(new_cfg)          # 落盘并返回合并后的配置
        self.cfg.clear()
        self.cfg.update(cfg)                          # 原地更新，worker 共享引用
        self.recognition.restart()
        return cfg


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    app = None  # 由 create_server 注入

    def log_message(self, *args):
        pass

    # ---- 发送辅助 ---------------------------------------------------------
    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    # ---- 路由 -------------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path in ("/", "/index.html"):
                return self._static("admin.html")
            if path == "/api/config":
                return self._json(200, self.app.cfg)
            if path == "/api/status":
                return self._json(200, self.app.status())
            if path == "/api/state":
                return self._json(200, {"battlefield": self.app.store.snapshot(),
                                        "status": self.app.status()})
            if path.startswith("/frame/"):
                return self._stream(path[len("/frame/"):])
            if path.startswith("/snapshot/"):
                return self._snapshot(path[len("/snapshot/"):])
            return self._static(path.lstrip("/"))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            try:
                self._json(500, {"error": str(e)})
            except OSError:
                pass

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError) as e:
            return self._json(400, {"error": f"非法请求体: {e}"})
        try:
            if path == "/api/config":
                cfg = self.app.apply_config(data)
                return self._json(200, {"ok": True, "config": cfg})
            return self._json(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            return self._json(500, {"error": str(e)})

    # ---- 静态文件 ---------------------------------------------------------
    def _static(self, rel):
        rel = rel.replace("\\", "/")
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            return self._send(404, "404 Not Found")
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as f:
            body = f.read()
        return self._send(200, body, _MIME.get(ext, "application/octet-stream"))

    # ---- 预览 -------------------------------------------------------------
    def _snapshot(self, cam_id):
        frame = self.app.recognition.get_frame(cam_id)
        if not frame:
            return self._send(404, "no frame")
        return self._send(200, frame, "image/jpeg")

    def _stream(self, cam_id):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            while True:
                frame = self.app.recognition.get_frame(cam_id)
                if frame:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                time.sleep(0.1)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


def create_server(app, host, port):
    Handler.app = app
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    return httpd


def serve_forever(httpd):
    threading.Thread(target=httpd.serve_forever, name="http", daemon=True).start()
