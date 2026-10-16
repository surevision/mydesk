# -*- coding: utf-8 -*-
"""
monitor/monitor.py — 视频采集端

在本机打开 1~N 个物理摄像头，用 MJPEG-over-HTTP 推给 center：
center 端只需 cv2.VideoCapture("http://<本机IP>:<port>/video/<idx>")，不解析、不谈其它协议。

接口：
  GET /                说明页（各路状态 + 链接）
  GET /video/<idx>     MJPEG 视频流（center 用）
  GET /video           等价 /video/0（兼容单路）
  GET /snapshot/<idx>  单帧 JPEG（浏览器调试）
  GET /status          各路状态 JSON

运行：
  python monitor.py                    # 读取同目录 config.json
  python monitor.py --port 8081        # 覆盖端口
  python monitor.py --cams 0,1         # 覆盖摄像头索引（顺序即 /video/<idx>）
  python monitor.py --width 1280 --height 720 --quality 70

依赖：opencv-python（见 requirements.txt）

配置 monitor/config.json：
  host / port / quality / cameras:[{index,width,height,fps}]
"""

import argparse
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# 一个 MJPEG 分片边界名，与 center 自己的预览流一致
BOUNDARY = "frame"

DEFAULT_CONFIG = {
    "host": "0.0.0.0",
    "port": 8080,
    "quality": 70,             # JPEG 质量（1-100）
    "cameras": [
        {"index": 0, "width": 1280, "height": 720, "fps": 30},
        {"index": 1, "width": 1280, "height": 720, "fps": 30},
    ],
}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"[monitor] 读取配置失败，用默认: {e}")
        return json.loads(json.dumps(DEFAULT_CONFIG))
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    for k, v in data.items():
        cfg[k] = v
    return cfg


def _lan_ip():
    """取本机局域网 IP（给 center 填地址用）。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


class CameraStream(threading.Thread):
    """后台持续抓取一个摄像头，始终保留最新一帧 JPEG，供多个客户端读取。
    摄像头打不开/读帧失败会自动重连，不影响 HTTP 服务。"""

    def __init__(self, idx, spec, quality):
        super().__init__(name=f"cam-{idx}", daemon=True)
        self.idx = idx
        self.index = int(spec.get("index", idx))
        self.width = int(spec.get("width", 1280))
        self.height = int(spec.get("height", 720))
        self.fps = int(spec.get("fps", 30))
        self.quality = int(quality)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._jpeg = None
        self.connected = False
        self.error = ""
        self.fps_real = 0.0

    def stop(self):
        self._stop.set()

    def latest(self):
        with self._lock:
            return self._jpeg

    def _open(self, cv2):
        # Windows 优先 DirectShow（打开更快更稳），失败再退回默认后端
        for backend in (getattr(cv2, "CAP_DSHOW", 700), getattr(cv2, "CAP_ANY", 0)):
            cap = cv2.VideoCapture(self.index, backend)
            if cap.isOpened():
                try:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    cap.set(cv2.CAP_PROP_FPS, self.fps)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:  # noqa: BLE001
                    pass
                return cap
            cap.release()
        return None

    def run(self):
        try:
            import cv2
        except Exception as e:  # noqa: BLE001
            self.error = f"缺少 opencv-python: {e}"
            print(f"[monitor] {self.error}")
            return
        cap = None
        count = 0
        t0 = time.time()
        while not self._stop.is_set():
            if cap is None:
                cap = self._open(cv2)
                if cap is None:
                    self.connected = False
                    self.error = f"无法打开摄像头 index={self.index}"
                    time.sleep(1.0)
                    continue
                self.connected = True
                self.error = ""
                count = 0
                t0 = time.time()
                print(f"[monitor] 摄像头 {self.idx} (index={self.index}) 已打开 "
                      f"{self.width}x{self.height}@{self.fps}")
            ret, frame = cap.read()
            if not ret or frame is None:
                cap.release()
                cap = None
                self.connected = False
                self.error = "读帧失败，重连中"
                time.sleep(0.3)
                continue
            ok, buf = cv2.imencode(".jpg", frame,
                                   [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
            if ok:
                with self._lock:
                    self._jpeg = buf.tobytes()
                count += 1
            now = time.time()
            if now - t0 >= 2.0:
                self.fps_real = count / (now - t0)
                count = 0
                t0 = now
        if cap is not None:
            cap.release()
        self.connected = False

    def status(self):
        return {"idx": self.idx, "index": self.index,
                "connected": self.connected, "fps": round(self.fps_real, 1),
                "error": self.error}


class MonitorApp:
    def __init__(self, streams):
        self.streams = streams

    def get(self, idx):
        if 0 <= idx < len(self.streams):
            return self.streams[idx]
        return None

    def status(self):
        return [s.status() for s in self.streams]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    app = None  # 由 main 注入

    def log_message(self, *args):
        pass

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

    @staticmethod
    def _idx_of(path, prefix):
        try:
            return int(path[len(prefix):])
        except ValueError:
            return -1

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path in ("/", "/index.html"):
                return self._index()
            if path == "/status":
                return self._send(200, json.dumps(self.app.status(), ensure_ascii=False),
                                  "application/json; charset=utf-8")
            if path == "/video":
                return self._stream(0)
            if path.startswith("/video/"):
                return self._stream(self._idx_of(path, "/video/"))
            if path.startswith("/snapshot/"):
                return self._snapshot(self._idx_of(path, "/snapshot/"))
            return self._send(404, "404 Not Found")
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _stream(self, idx):
        cam = self.app.get(idx)
        if cam is None:
            return self._send(404, "no such camera")
        self.send_response(200)
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            while True:
                frame = cam.latest()
                if frame:
                    self.wfile.write(f"--{BOUNDARY}\r\n".encode())
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                time.sleep(1.0 / 30)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _snapshot(self, idx):
        cam = self.app.get(idx)
        frame = cam.latest() if cam else None
        if not frame:
            return self._send(404, "no frame")
        return self._send(200, frame, "image/jpeg")

    def _index(self):
        port = self.server.server_address[1]
        ip = _lan_ip()
        rows = "".join(
            f"<li>摄像头 {s.idx}（index={s.index}）: "
            f"{'在线 %.1f fps' % s.fps_real if s.connected else '离线'}"
            f" &nbsp; <a href='/video/{s.idx}'>MJPEG</a>"
            f" | <a href='/snapshot/{s.idx}'>快照</a>"
            f"{' &nbsp; <b>' + s.error + '</b>' if s.error else ''}</li>"
            for s in self.app.streams)
        links = "".join(
            f"<li><code>http://{ip}:{port}/video/{s.idx}</code></li>"
            for s in self.app.streams)
        html = (
            "<!doctype html><meta charset='utf-8'><title>monitor</title>"
            "<h2>视频采集端 monitor</h2>"
            f"<ul>{rows}</ul>"
            "<h3>center 端摄像头地址（config.json）</h3>"
            f"<ul>{links}</ul>")
        return self._send(200, html, "text/html; charset=utf-8")


def main():
    parser = argparse.ArgumentParser(description="YGO 视频采集端 monitor")
    parser.add_argument("--host", help="监听地址（默认 0.0.0.0）")
    parser.add_argument("--port", type=int, help="监听端口")
    parser.add_argument("--cams", help="逗号分隔的摄像头索引，如 0,1（覆盖 config）")
    parser.add_argument("--width", type=int, help="采集宽度")
    parser.add_argument("--height", type=int, help="采集高度")
    parser.add_argument("--quality", type=int, help="JPEG 质量 1-100")
    args = parser.parse_args()

    cfg = load_config()
    if args.host:
        cfg["host"] = args.host
    if args.port:
        cfg["port"] = args.port
    if args.quality:
        cfg["quality"] = args.quality
    if args.cams is not None:
        cams = [c.strip() for c in args.cams.split(",") if c.strip() != ""]
        cfg["cameras"] = [{"index": int(c)} for c in cams]
    for c in cfg["cameras"]:
        if args.width:
            c["width"] = args.width
        if args.height:
            c["height"] = args.height

    streams = [CameraStream(i, spec, cfg["quality"])
               for i, spec in enumerate(cfg["cameras"])]
    for s in streams:
        s.start()

    Handler.app = MonitorApp(streams)
    httpd = ThreadingHTTPServer((cfg["host"], cfg["port"]), Handler)
    httpd.daemon_threads = True

    ip = _lan_ip()
    print(f"[monitor] 采集端  http://{cfg['host']}:{cfg['port']}/")
    for s in streams:
        print(f"[monitor] /video/{s.idx}  ← 摄像头 index={s.index}"
              f"   →  center 填 http://{ip}:{cfg['port']}/video/{s.idx}")
    print("[monitor] Ctrl+C 退出")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[monitor] 正在退出...")
    finally:
        for s in streams:
            s.stop()
        httpd.shutdown()


if __name__ == "__main__":
    main()
