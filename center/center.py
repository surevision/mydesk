# -*- coding: utf-8 -*-
"""
center.py
主控端入口：启动 HTTP 管理服务 + WebSocket 服务 + 摄像头识别。

    python center.py

职责：
- WebSocket 中转：display（Godot）与 controller（浏览器）都连到这里。
- 保存当前战场权威状态（人工优先，识别补充）。
- 摄像头识别：把识别到的卡牌按中心坐标落到对应格子，更新战场并广播。
- HTTP 管理页面：切换摄像头模式/参数、查看视频流与运行状态。
"""

import argparse
import json
import time

import config as config_mod
import http_server
from recognize import RecognitionManager
from state import BattlefieldStore
from ws_server import WebSocketServer

PHASE_INDEX = ["draw", "standby", "main1", "battle", "main2", "end"]


def main():
    parser = argparse.ArgumentParser(description="YGO 投影系统 center 主控端")
    parser.add_argument("--http-port", type=int, help="覆盖 HTTP 端口")
    parser.add_argument("--ws-port", type=int, help="覆盖 WebSocket 端口")
    args = parser.parse_args()

    cfg = config_mod.load_config()
    if args.http_port:
        cfg["http_port"] = args.http_port
    if args.ws_port:
        cfg["ws_port"] = args.ws_port

    store = BattlefieldStore()
    ws = WebSocketServer(cfg["ws_host"], cfg["ws_port"])
    recognition = RecognitionManager(store, cfg)

    def broadcast_change(kind, data):
        if kind == "battlefield":
            ws.broadcast({"type": "on_battlefield_change",
                          "battlefield": json.dumps(data, ensure_ascii=False)})
        elif kind == "lp":
            ws.broadcast({"type": "on_lp_change", **data})
        elif kind == "phase":
            key = data.get("phase")
            idx = PHASE_INDEX.index(key) if key in PHASE_INDEX else 0
            ws.broadcast({"type": "on_phase_anim", "phase_index": idx})

    store.on_change = broadcast_change

    def on_message(client, obj):
        t = obj.get("type")
        if t == "on_battlefield_change":
            bf = obj.get("battlefield")
            if isinstance(bf, str):
                try:
                    bf = json.loads(bf)
                except ValueError:
                    return
            if isinstance(bf, dict):
                store.set_from_controller(bf)
            return
        if t == "on_lp_change":
            store.set_lp(obj.get("player", 1), obj.get("lp", 0))
            return
        if t == "on_phase_anim":
            store.set_phase(obj.get("phase_index", obj.get("phase")))
            return
        # 其余动画/音效/导入等信息原样转发给其它端（主要是 display）
        ws.broadcast(obj, exclude=client)

    def on_connect(client):
        client.send_json({"type": "on_battlefield_change",
                          "battlefield": json.dumps(store.snapshot(), ensure_ascii=False)})

    ws.on_message = on_message
    ws.on_connect = on_connect

    app = http_server.AdminApp(cfg, store, recognition, ws, config_mod.save_config)
    httpd = http_server.create_server(app, cfg["http_host"], cfg["http_port"])

    ws.start()
    http_server.serve_forever(httpd)
    recognition.start()

    print(f"[center] 管理页面  http://{cfg['http_host']}:{cfg['http_port']}/")
    print(f"[center] WebSocket ws://{cfg['ws_host']}:{cfg['ws_port']}")
    print("[center] Ctrl+C 退出")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[center] 正在退出...")
        recognition.stop()
        ws.stop()
        httpd.shutdown()


if __name__ == "__main__":
    main()
