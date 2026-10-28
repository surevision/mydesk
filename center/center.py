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
import os
import time

import config as config_mod
import http_server
from blacklist import BlacklistStore
from calib import CalibrationStore
from recognize import RecognitionManager
from state import BattlefieldStore, DeckStore
from ws_server import WebSocketServer


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
    calib = CalibrationStore(os.path.join(config_mod.CONFIG_DIR, "calib.json"))
    decks = DeckStore()                      # 已导入卡组：卡名识别候选约束
    blacklist = BlacklistStore()             # 卡名黑名单：不按卡面处理
    muted = False                            # display 全局静音状态
    recognition = RecognitionManager(store, cfg, calib, decks, blacklist)

    def broadcast_change(kind, data):
        if kind == "battlefield":
            ws.broadcast({"type": "on_battlefield_change",
                          "battlefield": json.dumps(data, ensure_ascii=False)})
        elif kind == "lp":
            ws.broadcast({"type": "on_lp_change", **data})
        elif kind == "phase":
            # phase_index 用阶段字符串（draw/standby/main1/battle/main2/end），与 display 约定一致
            ws.broadcast({"type": "on_phase_anim", "phase_index": data.get("phase")})

    store.on_change = broadcast_change

    def on_message(client, obj):
        nonlocal muted
        t = obj.get("type")
        # voice 模块的指令带 source=voice：统一打印一条日志（source 不转发给其它端）
        if obj.pop("source", None) == "voice":
            print(f"[center] 收到语音指令: {json.dumps(obj, ensure_ascii=False)}")
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
        # 导入卡组：记录卡号（供卡名识别做候选约束），再转发给其它端
        if t == "on_import_ydk":
            n = decks.set(obj.get("player", 1), obj.get("ids", []))
            print(f"[center] 记录 P{obj.get('player', 1)} 卡组 {n} 张（用于卡名识别约束）")
            ws.broadcast(obj, exclude=client)
            return
        # 决斗结束：复位战场（同时把「是否开始」置为未开始），并广播空战场
        # 不论当前是否已开始都照常广播（重复指令由显示端自行忽略）
        if t == "on_game_reset":
            store.reset(emit=False)
            bf = json.dumps(store.snapshot(), ensure_ascii=False)
            ws.broadcast({"type": "on_game_reset", "battlefield": bf}, exclude=client)
            ws.broadcast({"type": "on_battlefield_change", "battlefield": bf})
            print("[center] 决斗结束：战场已清空（未开始状态，暂停识别）")
            return
        # 开始决斗：置为已开始（恢复识别），再广播给所有 controller / display
        # 不论当前是否已开始都照常广播（重复指令由显示端自行忽略）
        if t == "on_game_start":
            store.set_started(True)
            ws.broadcast({"type": "on_game_start"})
            print("[center] 开始决斗（恢复识别）")
            return
        # 骰子 / 硬币：转发给其它端（display 播放对应动画/音效）
        if t in ("on_dice", "on_coin"):
            ws.broadcast(obj, exclude=client)
            return
        # 切换战场规模：原样转发给其它端（display 端实现留空）
        if t == "on_switch_sizemode":
            ws.broadcast(obj, exclude=client)
            return
        # 显示/隐藏定位方块：转为 display 用的 on_marker_guide（附带四角坐标）
        if t == "on_guide":
            show = bool(obj.get("show"))
            msg = {"type": "on_marker_guide", "show": show}
            if show:
                msg["quads"] = calib.quads()
            ws.broadcast(msg)
            return
        # 全局静音：记录状态并同步给所有端（display 控制音频总线）
        if t == "on_mute":
            muted = bool(obj.get("mute"))
            ws.broadcast({"type": "on_mute", "mute": muted})
            print(f"[center] display 静音: {muted}")
            return
        # 其余动画/音效/导入等信息原样转发给其它端（主要是 display）
        ws.broadcast(obj, exclude=client)

    def on_connect(client):
        client.send_json({"type": "on_mute", "mute": muted})
        client.send_json({"type": "on_battlefield_change",
                          "battlefield": json.dumps(store.snapshot(), ensure_ascii=False)})

    ws.on_message = on_message
    ws.on_connect = on_connect

    app = http_server.AdminApp(cfg, store, recognition, ws, config_mod.save_config, calib,
                              blacklist)
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
