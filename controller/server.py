#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
投影控制端（controller）HTTP 服务。

职责（按当前设计）：
  1. 提供静态页面：index.html、css/、js/、assets/，供 Pad 浏览器访问。
  2. 提供少量后端接口（后续可继续增加）：
        GET  /api/config  读取 center 的 ip/端口及行为配置
        POST /api/config  保存配置（写入 config.json，方便手动修改）
       POST /api/ydk     上传 ydk 文件并解析出卡号列表

注意：
  - 页面与 center 的 WebSocket 连接由浏览器 JS 完成，本服务不主动连接 center。
  - 战场状态保存在 center 端，Controller 页面只是「接收 + 回发指令」。
  - 仅使用 Python 标准库（http.server），无需 pip 安装依赖。
"""

import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

# ----------------------------------------------------------------------------
# 路径与默认配置
# ----------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# center 连接默认地址（页面打开时会读取该配置并回填）
DEFAULT_CONFIG = {
    "center_ip": "127.0.0.1",
    "center_port": 4560,
    "dice_coin_choose_player": False,
}

# 静态文件扩展名 -> MIME
MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".txt": "text/plain; charset=utf-8",
}


# ----------------------------------------------------------------------------
# 配置读写
# ----------------------------------------------------------------------------

def load_config():
    """读取配置；文件不存在或损坏时返回默认值。"""
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 合并默认值，保证字段齐全
        cfg = dict(DEFAULT_CONFIG)
        cfg.update(data if isinstance(data, dict) else {})
        return cfg
    except (OSError, ValueError) as e:
        print(f"[config] 读取失败，使用默认配置: {e}")
        return dict(DEFAULT_CONFIG)


def save_config(cfg):
    """保存配置到 config.json。"""
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg if isinstance(cfg, dict) else {})
    # 端口统一转成整数
    try:
        merged["center_port"] = int(merged.get("center_port", DEFAULT_CONFIG["center_port"]))
    except (TypeError, ValueError):
        merged["center_port"] = DEFAULT_CONFIG["center_port"]
    merged["dice_coin_choose_player"] = bool(merged.get("dice_coin_choose_player", False))
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return merged


# ----------------------------------------------------------------------------
# ydk 解析
# ----------------------------------------------------------------------------

def parse_ydk(text):
    """
    解析 ydk 文本。ydk 结构：

        #created by ...
        #main
        12345678
        ...
        #extra
        87654321
        ...
        !side
        11111111
        ...

    返回 {'main': [...], 'extra': [...], 'side': [...], 'ids': [...]}
    """
    main, extra, side = [], [], []
    section = "main"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("#main"):
            section = "main"
            continue
        if low.startswith("#extra"):
            section = "extra"
            continue
        if low.startswith("!side"):
            section = "side"
            continue
        # 跳过其它 # / ! 开头的注释行
        if line[0] in "#!":
            continue
        if line.isdigit():
            card_id = int(line)
            if section == "extra":
                extra.append(card_id)
            elif section == "side":
                side.append(card_id)
            else:
                main.append(card_id)
    return {
        "main": main,
        "extra": extra,
        "side": side,
        "ids": main + extra + side,
    }


def parse_multipart(body, boundary):
    """极简 multipart/form-data 解析（避免依赖 Python 3.13 已移除的 cgi 模块）。"""
    fields = {}
    delimiter = b"--" + boundary
    for part in body.split(delimiter):
        if not part or part in (b"--", b"--\r\n", b"\r\n"):
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        header_blob, sep, data = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        name = None
        for hline in header_blob.split(b"\r\n"):
            if hline.lower().startswith(b"content-disposition"):
                m = re.search(rb'name="([^"]*)"', hline)
                if m:
                    name = m.group(1).decode("utf-8", "replace")
        if name is not None:
            fields[name] = data
    return fields


# ----------------------------------------------------------------------------
# HTTP 处理
# ----------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "YGODeskController/0.1"

    # ---- 日志 ----
    def log_message(self, fmt, *args):
        print(f"[http] {self.address_string()} {fmt % args}")

    # ---- 工具 ----
    def _send_json(self, obj, status=200):
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        return self.rfile.read(length) if length > 0 else b""

    # ---- GET ----
    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/config":
            self._send_json(load_config())
            return

        # 其它一律作为静态文件
        self._serve_static(path)

    # ---- POST ----
    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/config":
            body = self._read_body()
            try:
                cfg = json.loads(body.decode("utf-8") or "{}")
            except ValueError:
                self._send_json({"ok": False, "error": "invalid json"}, 400)
                return
            saved = save_config(cfg)
            self._send_json({"ok": True, "config": saved})
            return

        if path == "/api/ydk":
            self._handle_ydk()
            return

        self._send_json({"ok": False, "error": "not found"}, 404)

    # ---- OPTIONS (便于将来跨域调试) ----
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ---- ydk 上传 ----
    def _handle_ydk(self):
        body = self._read_body()
        content_type = self.headers.get("Content-Type", "")
        player = 0
        text = None

        try:
            if "multipart/form-data" in content_type:
                m = re.search(r"boundary=([^;]+)", content_type)
                boundary = m.group(1).strip().strip('"').encode() if m else None
                if not boundary:
                    raise ValueError("missing boundary")
                fields = parse_multipart(body, boundary)
                if "player" in fields:
                    player = int(fields["player"].decode().strip() or 0)
                if "file" in fields:
                    text = fields["file"].decode("utf-8", "replace")
                elif "content" in fields:
                    text = fields["content"].decode("utf-8", "replace")
            else:
                # 兼容 JSON: {player, content}
                data = json.loads(body.decode("utf-8") or "{}")
                player = int(data.get("player", 0) or 0)
                text = data.get("content", "")
        except (ValueError, KeyError, TypeError) as e:
            self._send_json({"ok": False, "error": f"解析上传失败: {e}"}, 400)
            return

        if text is None:
            self._send_json({"ok": False, "error": "缺少 ydk 文件内容"}, 400)
            return

        parsed = parse_ydk(text)
        parsed["ok"] = True
        parsed["player"] = player
        self._send_json(parsed)

    # ---- 静态文件 ----
    def _serve_static(self, path):
        if path in ("", "/"):
            path = "/index.html"

        # 归一化并防止目录穿越
        rel = unquote(path).lstrip("/\\")
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(STATIC_DIR):
            self._send_json({"ok": False, "error": "forbidden"}, 403)
            return
        if not os.path.isfile(full):
            self._send_json({"ok": False, "error": "not found"}, 404)
            return

        ext = os.path.splitext(full)[1].lower()
        mime = MIME_TYPES.get(ext, "application/octet-stream")
        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError as e:
            self._send_json({"ok": False, "error": str(e)}, 500)
            return

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


# ----------------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------------

def main():
    host = "0.0.0.0"
    port = 4582
    # 允许 python server.py [port]
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    # 确保配置文件存在
    cfg = load_config()
    print(f"[config] center 默认地址 {cfg['center_ip']}:{cfg['center_port']}")

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"[http] 控制端页面: http://<本机IP>:{port}/    (静态目录: {STATIC_DIR})")
    print("[http] Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[http] 正在退出 ...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
