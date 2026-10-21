# -*- coding: utf-8 -*-
"""
monitor/test_monitor.py — 用静态图片模拟视频采集端

不打开物理摄像头，把指定图片按固定帧率包装成 MJPEG，接口与 monitor.py 一致，
center 可以直接把摄像头地址指向本服务做识别测试。

接口：
  GET /                说明页
  GET /video/<idx>     MJPEG 视频流（center 用）
  GET /video           等价 /video/0
  GET /snapshot/<idx>  单帧 JPEG
  GET /status          各路状态 JSON

运行：
  python test_monitor.py --image ..\\test\\dm6.jpg
  python test_monitor.py --image ..\\test\\dm6.jpg --cams 2 --port 4581
  python test_monitor.py --image ..\\test\\dm6.jpg --image ..\\test\\dm7.jpg

依赖：opencv-python（见 requirements.txt）
"""

import argparse
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOUNDARY = "frame"


def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _default_image():
    for name in ("0 (2).jpg"):
        path = os.path.abspath(os.path.join(BASE_DIR, "..", "test", name))
        if os.path.isfile(path):
            return path
    return ""


def _prepare_jpeg(path, width, height, quality):
    try:
        import cv2
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"缺少 opencv-python: {e}") from e

    image = cv2.imread(path)
    if image is None:
        raise RuntimeError(f"无法读取图片: {path}")

    h, w = image.shape[:2]
    if width and height:
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    elif width:
        scale = width / float(w)
        image = cv2.resize(image, (width, max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    elif height:
        scale = height / float(h)
        image = cv2.resize(image, (max(1, round(w * scale)), height), interpolation=cv2.INTER_AREA)

    ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError(f"JPEG 编码失败: {path}")
    out_h, out_w = image.shape[:2]
    return buf.tobytes(), (out_w, out_h)


class ImageStream(threading.Thread):
    """周期性推进帧序号；所有客户端读取最新 JPEG。"""

    def __init__(self, idx, source, jpeg, fps):
        super().__init__(name=f"image-{idx}", daemon=True)
        self.idx = idx
        self.source = source
        self.fps = max(1, int(fps))
        self._jpeg = jpeg
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._seq = 0
        self.connected = True
        self.error = ""
        self.fps_real = 0.0

    def stop(self):
        self._stop.set()

    def latest_seq(self):
        with self._lock:
            return self._seq, self._jpeg

    def latest(self):
        with self._lock:
            return self._jpeg

    def run(self):
        interval = 1.0 / self.fps
        count = 0
        t0 = time.time()
        while not self._stop.is_set():
            with self._lock:
                self._seq += 1
            count += 1
            now = time.time()
            if now - t0 >= 2.0:
                self.fps_real = count / (now - t0)
                count = 0
                t0 = now
            self._stop.wait(interval)
        self.connected = False

    def status(self):
        return {
            "idx": self.idx,
            "index": self.idx,
            "source": self.source,
            "connected": self.connected,
            "fps": round(self.fps_real, 1),
            "target_fps": self.fps,
            "error": self.error,
        }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    streams = []

    def log_message(self, *args):
        pass

    @staticmethod
    def _send(handler, code, body, ctype="text/plain; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", ctype)
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        if handler.command != "HEAD":
            handler.wfile.write(body)

    @staticmethod
    def _idx_of(path, prefix):
        try:
            return int(path[len(prefix):])
        except ValueError:
            return -1

    def _stream(self, idx):
        if not (0 <= idx < len(self.streams)):
            return self._send(self, 404, "no such stream")
        stream = self.streams[idx]
        self.send_response(200)
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            last = -1
            while True:
                seq, frame = stream.latest_seq()
                if frame is not None and seq != last:
                    last = seq
                    self.wfile.write(f"--{BOUNDARY}\r\n".encode())
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                else:
                    time.sleep(1.0 / 60)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _snapshot(self, idx):
        if not (0 <= idx < len(self.streams)):
            return self._send(self, 404, "no such stream")
        frame = self.streams[idx].latest()
        if not frame:
            return self._send(self, 404, "no frame")
        return self._send(self, 200, frame, "image/jpeg")

    def _index(self):
        port = self.server.server_address[1]
        ip = _lan_ip()
        rows = "".join(
            f"<li>流 {s.idx}: {s.source} &nbsp; "
            f"{s.fps_real:.1f} fps &nbsp; "
            f"<a href='/video/{s.idx}'>MJPEG</a>"
            f" | <a href='/snapshot/{s.idx}'>快照</a></li>"
            for s in self.streams
        )
        links = "".join(
            f"<li><code>http://{ip}:{port}/video/{s.idx}</code></li>"
            for s in self.streams
        )
        html = (
            "<!doctype html><meta charset='utf-8'><title>test monitor</title>"
            "<h2>静态图片测试流</h2>"
            f"<ul>{rows}</ul>"
            "<h3>center 摄像头地址</h3>"
            f"<ul>{links}</ul>"
        )
        return self._send(self, 200, html, "text/html; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path in ("/", "/index.html"):
                return self._index()
            if path == "/status":
                return self._send(self, 200,
                                  json.dumps([s.status() for s in self.streams],
                                             ensure_ascii=False),
                                  "application/json; charset=utf-8")
            if path == "/video":
                return self._stream(0)
            if path.startswith("/video/"):
                return self._stream(self._idx_of(path, "/video/"))
            if path == "/snapshot":
                return self._snapshot(0)
            if path.startswith("/snapshot/"):
                return self._snapshot(self._idx_of(path, "/snapshot/"))
            return self._send(self, 404, "404 Not Found")
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    parser = argparse.ArgumentParser(description="用静态图片模拟 monitor 的 MJPEG 视频流")
    parser.add_argument("--image", action="append", default=[],
                        help="测试图片路径，可重复；默认使用 test/dm6.jpg")
    parser.add_argument("--images", default="",
                        help="逗号分隔的多张图片路径（与 --image 等价）")
    parser.add_argument("--cams", type=int,
                        help="模拟几路流；默认等于图片数量，图片不足时循环使用")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址（默认 0.0.0.0）")
    parser.add_argument("--port", type=int, default=4581, help="监听端口（默认 4581）")
    parser.add_argument("--fps", type=int, default=5, help="每路帧率（默认 5）")
    parser.add_argument("--quality", type=int, default=90, help="JPEG 质量 1-100（默认 90）")
    parser.add_argument("--width", type=int, help="缩放宽度")
    parser.add_argument("--height", type=int, help="缩放高度")
    args = parser.parse_args()

    paths = list(args.image)
    paths += [p.strip() for p in args.images.split(",") if p.strip()]
    if not paths:
        default = _default_image()
        if default:
            paths = [default]
    if not paths:
        parser.error("请用 --image 指定测试图片")
    paths = [os.path.abspath(p) for p in paths]
    for p in paths:
        if not os.path.isfile(p):
            parser.error(f"图片不存在: {p}")

    cams = max(1, int(args.cams or len(paths)))
    prepared = [_prepare_jpeg(p, args.width, args.height, args.quality) for p in paths]

    streams = []
    for idx in range(cams):
        source = paths[idx % len(paths)]
        jpeg, size = prepared[idx % len(prepared)]
        stream = ImageStream(idx, source, jpeg, args.fps)
        streams.append(stream)
        print(f"[test-monitor] /video/{idx}  <- {source}  {size[0]}x{size[1]} @{args.fps}fps")

    for s in streams:
        s.start()

    Handler.streams = streams
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True

    ip = _lan_ip()
    print(f"[test-monitor] 服务 http://{args.host}:{args.port}/  局域网 {ip}")
    for s in streams:
        print(f"[test-monitor] center 填 http://{ip}:{args.port}/video/{s.idx}")
    print("[test-monitor] Ctrl+C 退出")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[test-monitor] 正在退出 ...")
    finally:
        for s in streams:
            s.stop()
        httpd.shutdown()


if __name__ == "__main__":
    main()
