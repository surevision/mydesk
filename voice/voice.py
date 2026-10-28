# -*- coding: utf-8 -*-
"""
voice.py
---------------------------------------------------------------------------
voice 模块入口：串口语音指令 → center WebSocket 消息。

    python voice.py

- 串口：CH340（USB 转串口），读取语音模块输出的一行一条指令；
- 配置页：http://<本机>:4583/（串口、波特率、center 地址）；
- 只发送、不接收 center 的消息；发送失败忽略；串口失败 5 秒后重试。

串口消息与 center 指令的对应关系：
    VGS → {"type": "on_game_start"}
    VGR → {"type": "on_game_reset"}
    VD  → {"type": "on_dice", "player": 0, "value": 1-6}
    VC  → {"type": "on_coin", "player": 0, "value": 0/1}
"""

import json
import os
import random
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import config as config_mod
from serial_link import SerialLink, available_ports
from ws_client import send_json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# 串口文本 → 动作（语音模块实际发送 VGS/VGR/VD/VC）
MESSAGE_ACTIONS = {
    "VGS": "game_start",
    "VGR": "game_reset",
    "VD": "dice",
    "VC": "coin",
    "VSA": "summon_advance",
    "VSF": "summon_fusion",
    "VSS": "summon_synchro",
    "VSX": "summon_xyz",
    "VSP": "summon_pendulum",
    "VSL": "summon_link",
    "VSR": "summon_ritual",
}
_ACTIONS_LOWER = {k.lower(): v for k, v in MESSAGE_ACTIONS.items()}


def resolve_action(text):
    """大小写不敏感地查串口文本对应的动作；未识别返回 None。"""
    return MESSAGE_ACTIONS.get(text) or _ACTIONS_LOWER.get(text.lower())


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class VoiceApp:
    def __init__(self):
        self._lock = threading.Lock()
        self.cfg = config_mod.load_config()
        self.link = SerialLink(self.cfg["serial_port"], self.cfg["baudrate"], self.on_voice)
        self.tx_ok = 0
        self.tx_fail = 0
        self.last_action = ""
        self.last_sent = ""

    # ---- 串口消息 → center ------------------------------------------------
    def on_voice(self, text):
        action = resolve_action(text)
        if not action:
            return
        with self._lock:
            host, port = self.cfg["center_host"], self.cfg["center_port"]

        if action == "game_start":
            payload = {"type": "on_game_start"}
        elif action == "game_reset":
            payload = {"type": "on_game_reset"}
        elif action == "dice":
            payload = {"type": "on_dice", "player": 0, "value": random.randint(1, 6)}
        elif action == 'coin':
            payload = {"type": "on_coin", "player": 0, "value": random.randint(0, 1)}
        elif action == 'summon_advance':
            payload = {"type": "on_summon_anim", "summon_type": "advance"}
        elif action == 'summon_fusion':
            payload = {"type": "on_summon_anim", "summon_type": "fusion"}
        elif action == 'summon_synchro':
            payload = {"type": "on_summon_anim", "summon_type": "synchro"}
        elif action == 'summon_xyz':
            payload = {"type": "on_summon_anim", "summon_type": "xyz"}
        elif action == 'summon_pendulum':
            payload = {"type": "on_summon_anim", "summon_type": "pendulum"}
        elif action == 'summon_lilnk':
            payload = {"type": "on_summon_anim", "summon_type": "link"}
        elif action == 'summon_ritual':
            payload = {"type": "on_summon_anim", "summon_type": "ritual"}
        
        payload["source"] = "voice"    # 供 center 打印「收到语音指令」日志（center 不转发该字段）

        ok = send_json(host, port, payload)
        with self._lock:
            if ok:
                self.tx_ok += 1
            else:
                self.tx_fail += 1
            self.last_action = action
            self.last_sent = json.dumps(payload, ensure_ascii=False)

        if ok:
            print(f"[voice] 已发送 {self.last_sent} → ws://{host}:{port}")
        else:
            print(f"[voice] 发送失败（忽略） {self.last_sent} → ws://{host}:{port}")

    # ---- 配置 -------------------------------------------------------------
    def config_view(self):
        with self._lock:
            cfg = dict(self.cfg)
        return {
            "config": cfg,
            "center_url": config_mod.center_url(cfg),
            "serial_available": self.link.status()["serial_available"],
        }

    def apply_config(self, raw):
        with self._lock:
            old = dict(self.cfg)
            merged = dict(self.cfg)
        if isinstance(raw, dict):
            merged.update(raw)     # 页面只提交部分字段时，其余保持原值
        new = config_mod.save_config(merged)
        with self._lock:
            self.cfg = new
        if (old["serial_port"] != new["serial_port"]
                or old["baudrate"] != new["baudrate"]):
            self.link.configure(new["serial_port"], new["baudrate"])
            print(f"[voice] 串口配置已更新: {new['serial_port']} @ {new['baudrate']}")
        return self.config_view()

    def status_view(self):
        with self._lock:
            cfg = dict(self.cfg)
            tx_ok, tx_fail = self.tx_ok, self.tx_fail
            last_action, last_sent = self.last_action, self.last_sent
        return {
            "config": cfg,
            "center_url": config_mod.center_url(cfg),
            "serial": self.link.status(),
            "tx_ok": tx_ok,
            "tx_fail": tx_fail,
            "last_action": last_action,
            "last_sent": last_sent,
        }


class Handler(BaseHTTPRequestHandler):
    app = None  # VoiceApp，在 main 里注入
    server_version = "VoiceConfig/1.0"

    def log_message(self, fmt, *args):  # 静默访问日志
        pass

    def _send(self, code, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _static(self, rel_path):
        path = os.path.normpath(os.path.join(STATIC_DIR, rel_path))
        if not path.startswith(os.path.normpath(STATIC_DIR) + os.sep):
            return self._json(404, {"error": "not found"})
        if not os.path.isfile(path):
            return self._json(404, {"error": "not found"})
        ext = os.path.splitext(path)[1].lower()
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return self._json(500, {"error": "read failed"})
        return self._send(200, data, CONTENT_TYPES.get(ext, "application/octet-stream"))

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._static("index.html")
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        if path == "/api/config":
            return self._json(200, self.app.config_view())
        if path == "/api/status":
            return self._json(200, self.app.status_view())
        if path == "/api/ports":
            return self._json(200, {
                "ports": available_ports(),
                "serial_available": self.app.link.status()["serial_available"],
            })
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/config":
            return self._json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, OSError):
            return self._json(400, {"error": "请求体不是合法 JSON"})
        try:
            return self._json(200, self.app.apply_config(data))
        except Exception as exc:  # noqa: BLE001
            return self._json(500, {"error": str(exc)})


def main():
    app = VoiceApp()
    # 让配置页端口也生效：若 /api/config 改了端口，需要重启本进程（README 已说明）
    Handler.app = app

    httpd = ThreadingHTTPServer(
        (app.cfg["http_host"], app.cfg["http_port"]), Handler)
    httpd.daemon_threads = True

    app.link.start()
    print(f"[voice] 配置页面  http://{app.cfg['http_host']}:{app.cfg['http_port']}/")
    print(f"[voice] 串口  {app.cfg['serial_port']} @ {app.cfg['baudrate']}")
    print(f"[voice] center  {config_mod.center_url(app.cfg)}")
    print("[voice] Ctrl+C 退出")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[voice] 正在退出...")
    finally:
        app.link.stop()
        httpd.shutdown()


if __name__ == "__main__":
    main()
