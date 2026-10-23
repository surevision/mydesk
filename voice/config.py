# -*- coding: utf-8 -*-
"""
config.py
---------------------------------------------------------------------------
voice 模块配置读写（voice/config.json）。

配置项：
    serial_port   串口名（CH340 常见为 COM1 / COM3）
    baudrate      波特率
    center_host   center 的 WebSocket 地址（也可直接填 ws://ip:port）
    center_port   center 的 WebSocket 端口（默认 4560）
    http_host     本模块配置页面监听地址
    http_port     本模块配置页面端口（默认 4583）
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "serial_port": "COM3",
    "baudrate": 115200,
    "center_host": "127.0.0.1",
    "center_port": 4560,
    "http_host": "0.0.0.0",
    "http_port": 4583,
}


def parse_center(text, default_port=4560):
    """把 '127.0.0.1:4560' / 'ws://192.168.1.5:4560' 解析成 (host, port)。"""
    s = (text or "").strip()
    for prefix in ("ws://", "wss://", "http://", "https://"):
        if s.lower().startswith(prefix):
            s = s[len(prefix):]
            break
    s = s.split("/", 1)[0].strip()
    host, port = s, default_port
    if s.startswith("[") and "]" in s:            # [::1]:4560
        host, _, rest = s.partition("]")
        host = host[1:]
        if rest.startswith(":"):
            try:
                port = int(rest[1:])
            except ValueError:
                port = default_port
    elif s.count(":") == 1:                       # host:port
        host, _, raw = s.partition(":")
        try:
            port = int(raw)
        except ValueError:
            port = default_port
    return (host or "127.0.0.1"), port


def _sanitize(raw):
    """把外部传入的配置整理成合法值（缺省/非法时回落到默认值）。"""
    cfg = dict(DEFAULT_CONFIG)
    if not isinstance(raw, dict):
        return cfg

    if raw.get("serial_port") is not None:
        cfg["serial_port"] = str(raw.get("serial_port")).strip()

    try:
        baud = int(raw.get("baudrate", cfg["baudrate"]))
        if baud > 0:
            cfg["baudrate"] = baud
    except (TypeError, ValueError):
        pass

    host, port = parse_center(raw.get("center_host", cfg["center_host"]), cfg["center_port"])
    try:
        port = int(raw.get("center_port", port))
    except (TypeError, ValueError):
        pass
    if port <= 0 or port > 65535:
        port = DEFAULT_CONFIG["center_port"]
    cfg["center_host"], cfg["center_port"] = host, port

    cfg["http_host"] = str(raw.get("http_host", cfg["http_host"])).strip() or cfg["http_host"]
    try:
        http_port = int(raw.get("http_port", cfg["http_port"]))
        if 0 < http_port <= 65535:
            cfg["http_port"] = http_port
    except (TypeError, ValueError):
        pass
    return cfg


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        raw = {}
    cfg = _sanitize(raw)
    if not os.path.exists(CONFIG_PATH):
        save_config(cfg)
    return cfg


def save_config(cfg):
    cfg = _sanitize(cfg)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, CONFIG_PATH)
    return cfg


def center_url(cfg):
    """给日志/页面显示用的 center WebSocket 地址。"""
    return f"ws://{cfg['center_host']}:{cfg['center_port']}"
