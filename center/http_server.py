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
  GET  /api/calib        当前定位（校准）结果
  GET  /frame/<cam_id>   MJPEG 预览流（带叠加）
  GET  /snapshot/<cam_id> 单帧 JPEG（带叠加）
  GET  /raw/<cam_id>     MJPEG 预览流（原始帧，定位用）
  GET  /rawsnap/<cam_id> 单帧 JPEG（原始帧，定位用）
  POST /api/calibrate    按 ROI 框选执行定位（自动检测定位方块）
  POST /api/calibrate_manual  手动标记 4 个定位标识（顺时针）建立定位
  POST /api/guide        显示/隐藏 display 上的定位方块
  POST /api/monitor_fps  通知采集端 monitor 修改采集帧率
"""

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from calib import calibrate_player, calibrate_player_manual

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

    def __init__(self, cfg, store, recognition, ws_server, save_config_fn, calib=None):
        self.cfg = cfg
        self.store = store
        self.recognition = recognition
        self.ws_server = ws_server
        self.save_config_fn = save_config_fn
        self.calib = calib

    def _monitor_bases(self):
        """从当前摄像头地址里取出唯一的采集端 monitor 基地址（scheme://host:port）。"""
        mode = self.cfg.get("mode", "single")
        if mode == "dual":
            urls = [c.get("url", "") for c in self.cfg.get("dual", {}).get("cameras", [])]
        else:
            urls = [self.cfg.get("single", {}).get("url", "")]
        bases = []
        for u in urls:
            if not u or str(u).isdigit():   # 本地摄像头索引，无 monitor 可通知
                continue
            p = urllib.parse.urlsplit(str(u))
            if p.scheme and p.netloc:
                base = f"{p.scheme}://{p.netloc}"
                if base not in bases:
                    bases.append(base)
        return bases

    def set_monitor_fps(self, fps):
        """通知采集端 monitor 修改目标帧率（POST {base}/api/fps）。"""
        try:
            fps = int(fps)
        except (TypeError, ValueError):
            raise RuntimeError("帧率必须是整数")
        if fps < 1:
            raise RuntimeError("帧率需 ≥ 1")
        bases = self._monitor_bases()
        if not bases:
            raise RuntimeError("没有可通知的采集端地址（本地摄像头无法远程改帧率）")
        results, errors = {}, {}
        for base in bases:
            try:
                req = urllib.request.Request(
                    base + "/api/fps",
                    data=json.dumps({"fps": fps}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    results[base] = json.loads(resp.read().decode("utf-8") or "{}")
            except Exception as e:  # noqa: BLE001
                errors[base] = str(e)
        return {"ok": not errors, "fps": fps, "results": results, "errors": errors}

    def status(self):
        st = self.recognition.status()
        st["ws_clients"] = self.ws_server.client_count
        st["ws_client_ids"] = self.ws_server.client_ids
        st["version"] = self.store.version
        st["calibrations"] = self.calib.status() if self.calib is not None else []
        return st

    def apply_config(self, new_cfg):
        cfg = self.save_config_fn(new_cfg)          # 落盘并返回合并后的配置
        self.cfg.clear()
        self.cfg.update(cfg)                          # 原地更新，worker 共享引用
        self.recognition.restart()
        return cfg

    # ---- 定位/校准 --------------------------------------------------------
    def calibrate(self, cam_id, rois):
        """
        rois: {player: [x0,y0,x1,y1]}（画面像素）。
        对每个玩家在其 ROI 内检测 4 个定位方块并建立校准；全部成功则重发战场快照。
        """
        if self.calib is None:
            raise RuntimeError("未启用定位功能")
        frame = self.recognition.get_raw_frame(cam_id)
        if frame is None:
            raise RuntimeError(f"摄像头 {cam_id} 暂无画面，无法定位")
        mode = self.cfg["mode"]
        results, errors = {}, {}
        for player, roi in rois.items():
            try:
                pc = calibrate_player(frame, roi, cam_id, str(player), mode)
                self.calib.set(pc)
                results[str(player)] = pc.status()
            except Exception as e:  # noqa: BLE001
                errors[str(player)] = str(e)
        ok = not errors
        if ok:
            self.store.rebroadcast()                 # 重新定位后重发战场快照给 control/display
        return {"ok": ok, "results": results, "errors": errors}

    def calibrate_manual(self, cam_id, player, corners):
        """
        手动标记定位标识：corners 为框选小方格的中心（画面像素），
        顺序 tl → tr → br → bl（从左上角开始顺时针）。
        """
        if self.calib is None:
            raise RuntimeError("未启用定位功能")
        frame = self.recognition.get_raw_frame(cam_id)
        if frame is None:
            raise RuntimeError(f"摄像头 {cam_id} 暂无画面，无法定位")
        h, w = frame.shape[:2]
        pc = calibrate_player_manual(corners, cam_id, str(player),
                                     self.cfg["mode"], (w, h))
        self.calib.set(pc)
        self.store.rebroadcast()                 # 重新定位后重发战场快照
        return {"ok": True, "result": pc.status()}

    def set_guide(self, show):
        """显示/隐藏 display 上的定位方块。"""
        msg = {"type": "on_marker_guide", "show": bool(show)}
        if show and self.calib is not None:
            msg["quads"] = self.calib.quads()
        self.ws_server.broadcast(msg)
        return {"ok": True, "show": bool(show), "sent": msg.get("quads", {})}

    def calibrations(self):
        return self.calib.status() if self.calib is not None else []

    def raw_jpeg(self, cam_id):
        """原始帧编码为 JPEG（校准预览用）。"""
        cv2 = self.recognition.models.cv2
        frame = self.recognition.get_raw_frame(cam_id)
        if cv2 is None or frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return buf.tobytes() if ok else None


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
            if path == "/api/calib":
                return self._json(200, {"calibrations": self.app.calibrations()})
            if path.startswith("/frame/"):
                return self._stream(path[len("/frame/"):], raw=False)
            if path.startswith("/raw/"):
                return self._stream(path[len("/raw/"):], raw=True)
            if path.startswith("/snapshot/"):
                return self._snapshot(path[len("/snapshot/"):], raw=False)
            if path.startswith("/rawsnap/"):
                return self._snapshot(path[len("/rawsnap/"):], raw=True)
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
            if path == "/api/calibrate":
                cam_id = str(data.get("cam_id", ""))
                rois = data.get("rois", {})
                if not cam_id or not isinstance(rois, dict) or not rois:
                    return self._json(400, {"error": "缺少 cam_id 或框选区域"})
                return self._json(200, self.app.calibrate(cam_id, rois))
            if path == "/api/calibrate_manual":
                cam_id = str(data.get("cam_id", ""))
                player = data.get("player")
                corners = data.get("corners")
                if not cam_id or player is None or \
                        not isinstance(corners, list) or len(corners) != 4:
                    return self._json(400, {"error": "缺少 cam_id / player / corners(4 点)"})
                return self._json(200, self.app.calibrate_manual(cam_id, player, corners))
            if path == "/api/guide":
                return self._json(200, self.app.set_guide(data.get("show", False)))
            if path == "/api/monitor_fps":
                if "fps" not in data:
                    return self._json(400, {"error": "缺少 fps"})
                return self._json(200, self.app.set_monitor_fps(data.get("fps")))
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
    def _snapshot(self, cam_id, raw=False):
        if raw:
            frame = self.app.raw_jpeg(cam_id)
        else:
            frame = self.app.recognition.get_frame(cam_id)
        if not frame:
            return self._send(404, "no frame")
        return self._send(200, frame, "image/jpeg")

    def _stream(self, cam_id, raw=False):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            while True:
                frame = self.app.raw_jpeg(cam_id) if raw \
                    else self.app.recognition.get_frame(cam_id)
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
