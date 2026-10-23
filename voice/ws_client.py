# -*- coding: utf-8 -*-
"""
ws_client.py
---------------------------------------------------------------------------
极简 WebSocket 客户端（只发不收）。

voice 模块是独立模块，只负责把语音指令转成 center 的消息：
每条指令临时建立一次连接、发送一帧 JSON 文本后断开，避免长期连接失效
带来的状态维护；发送失败直接忽略（返回 False），下次指令再重连。
"""

import base64
import hashlib
import json
import os
import socket
import struct

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("连接已关闭")
        buf += chunk
    return buf


def _send_text_frame(sock, text):
    payload = text.encode("utf-8")
    mask = os.urandom(4)
    n = len(payload)
    if n < 126:
        header = bytes([0x81, 0x80 | n])
    elif n < 65536:
        header = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
    else:
        header = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", n)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    sock.sendall(header + mask + masked)


def send_json(host, port, obj, timeout=3.0):
    """
    向 ws://host:port 发送一条 JSON 文本消息。
    成功返回 True；任何异常都被吞掉并返回 False（调用方只需忽略）。
    """
    sock = None
    try:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        sock = socket.create_connection((host, int(port)), timeout=timeout)
        sock.settimeout(timeout)
        request = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        sock.sendall(request.encode("ascii"))

        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(1024)
            if not chunk:
                return False
            response += chunk
            if len(response) > 16384:
                return False
        head = response.decode("latin1", "replace")
        status_line = head.split("\r\n", 1)[0]
        if " 101 " not in status_line and not status_line.endswith(" 101"):
            return False
        expect = base64.b64encode(
            hashlib.sha1((key + _WS_GUID).encode("ascii")).digest()
        ).decode("ascii")
        if expect.lower() not in head.lower():
            return False

        _send_text_frame(sock, json.dumps(obj, ensure_ascii=False))
        return True
    except (OSError, ValueError):
        return False
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
