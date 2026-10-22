# -*- coding: utf-8 -*-
"""
center 配置：读写 config/config.json，提供默认值。
- config/config_default.json：随仓库提交的默认模板。
- config/config.json：本机实际配置，首次运行由模板复制生成（可加入 .gitignore）。
管理页面也可修改配置。
"""

import copy
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")           # 本机配置（运行时生成）
DEFAULT_PATH = os.path.join(CONFIG_DIR, "config_default.json")  # 提交的默认模板

# 模型默认放在项目 models 下（旧的 src/models 也兼容）
def _models_dir():
    """模型目录：优先 ../models，兼容旧的 ../src/models。"""
    for rel in (("..", "models"), ("..", "src", "models")):
        p = os.path.normpath(os.path.join(BASE_DIR, *rel))
        if os.path.isdir(p):
            return p
    return os.path.normpath(os.path.join(BASE_DIR, "..", "models"))


MODELS_DIR = _models_dir()


def _default_layout():
    """
    某一玩家区域内的格子归一化矩形（相对该玩家区域左上角，0-1）。
    back = 魔陷区（5），front = 怪兽区（5），ex = 额外怪兽区（2），
    其余为单格。默认排布仅作起点，需按实际拍摄微调（管理页面叠加显示）。
    """
    col = lambda i: 0.14 + 0.148 * i  # 第 i 列（0-4）的左边界
    return {
        "col_count": 5,
        "back": [{"x": col(i), "y": 0.10, "w": 0.13, "h": 0.28} for i in range(5)],
        "front": [{"x": col(i), "y": 0.42, "w": 0.13, "h": 0.28} for i in range(5)],
        "ex": [
            {"x": 0.005, "y": 0.42, "w": 0.105, "h": 0.28},
            {"x": 0.89, "y": 0.42, "w": 0.105, "h": 0.28},
        ],
        "field": {"x": 0.005, "y": 0.10, "w": 0.115, "h": 0.28},
        "grave": {"x": 0.88, "y": 0.10, "w": 0.115, "h": 0.28},
        "exdeck": {"x": 0.005, "y": 0.73, "w": 0.115, "h": 0.25},
        "deck": {"x": 0.88, "y": 0.73, "w": 0.115, "h": 0.25},
    }


DEFAULT_CONFIG = {
    # HTTP 服务（管理页面 + 接口 + 视频预览）
    "http_host": "0.0.0.0",
    "http_port": 4580,
    # WebSocket 服务（display / controller 连接）
    "ws_host": "0.0.0.0",
    "ws_port": 4560,

    # 摄像头模式：single（单摄像头拍双方）| dual（双摄像头各拍一方）
    "mode": "single",

    # 单摄像头模式
    "single": {
        # monitor 采集端的多路地址：单路用 /video/0
        "url": "http://10.10.1.105:4581/video/0",
        "player1_side": "left",   # left：画面左半为 player1；right：右半为 player1
    },

    # 双摄像头模式
    "dual": {
        "swap": False,            # 交换两个摄像头与玩家的对应
        # 两路必须填不同的地址（monitor 的 /video/0、/video/1）
        # orientation：摄像头画面方向，horizontal=横向（3 行×7 列），vertical=竖向（7 行×3 列）
        "cameras": [
            {"url": "http://10.10.1.105:4581/video/0", "player": 1,
             "orientation": "horizontal"},
            {"url": "http://10.10.1.105:4581/video/1", "player": 2,
             "orientation": "horizontal"},
        ],
    },

    # 模型路径（相对项目根目录或绝对路径皆可）
    "models": {
        # 正面：.onnx 走纯 ONNX（draw2 网页版同款，无需 ultralytics）；.pt 走 ultralytics
        "yolo_front": os.path.join(MODELS_DIR, "ygo_yolo.onnx"),
        # 卡背：.onnx 走纯 ONNX（detector.onnx，正面/卡背二分类）；.pt 走 ultralytics
        "yolo_back": os.path.join(MODELS_DIR, "detector.onnx"),
        "name_onnx": os.path.join(MODELS_DIR, "vit_fp32.onnx"),     # 卡名识别 ONNX
        "names_json": os.path.join(MODELS_DIR, "cardnames_onnx.json"),
    },

    # 识别参数（参考 test/videotest.py）
    "detect": {
        "front_conf": 0.1,      # 正面检测置信度阈值
        "back_conf": 0.5,       # 卡背置信度阈值
        "name_thr": 0.001,      # 卡名识别置信度阈值（低于则视为未识别，id=-1）
        "top_k": 15,            # 卡名识别候选数（有卡组时在前 top_k 中按卡组约束挑选）
        "interval": 0.1,        # 识别间隔（秒）
        "min_side": 30,         # 卡最小边长（像素），过小忽略
        "device": 0,            # 推理设备：0=第一块 GPU；"cpu"=CPU
        "track": True,          # 使用 OBB 跟踪（稳定身份 + 卡名缓存）
        "name_cache_ttl": 3.0,  # 同一跟踪 id 重跑卡名识别的间隔（秒）；到点用当前帧重识别并更新卡名
        # 移植 draw2：透视矫正成 crop_size×crop_size 方图，只残余 0°/180°
        "crop_size": 224,       # ViT 输入边长（方图，与训练分布一致）
        "flip_low": 0.15,       # 置信度低于此值才尝试 180° 翻转
        "flip_margin": 1.25,    # 翻转需比原方向好这么多倍才采纳
        "nms_iou": 0.5,         # ONNX 检测的 OBB NMS 阈值（网页版 0.5）
        "track_iou": 0.3,       # ONNX 无跟踪器：自建 IoU 跟踪的重叠阈值
        "track_ttl": 1.0,       # 跟踪丢失多久后回收 id（秒）
        # 定位方块屏蔽半径（像素）：打印的定位标识纸会被正面模型稳定检出
        # （conf ~0.9）并被误映射到其附近的格子（鬼影卡）。校准后按方块中心
        # 附近的检测框直接丢弃。0=不屏蔽。
        "marker_drop_radius": 60,
        # 单格短暂丢失保持秒数：识别偶尔丢一帧时格子里刚认出的卡不被清空
        # （display 端不闪）；卡被拿走时最长显示 cell_hold 秒余像
        "cell_hold": 1.0,
    },

    # 每玩家区域的格子布局
    "layout": _default_layout(),

    # 识别结果是否更新战场（可临时关闭，仅用人工操作）
    "recognition_enabled": True,
}


def _deep_merge(base, override):
    """把 override 合并进 base 的副本（递归）。"""
    out = copy.deepcopy(base)
    if not isinstance(override, dict):
        return out
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _seed_config():
    """config.json 不存在时生成：优先用 config_default.json 模板，否则用内置默认。"""
    if os.path.exists(DEFAULT_PATH):
        try:
            with open(DEFAULT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            _write_json(CONFIG_PATH, data)
            print("[config] 已由 config_default.json 生成 config/config.json")
            return
        except (OSError, ValueError) as e:
            print(f"[config] 读取 config_default.json 失败，改用内置默认: {e}")
    _write_json(CONFIG_PATH, DEFAULT_CONFIG)


def load_config():
    if not os.path.exists(CONFIG_PATH):
        _seed_config()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _deep_merge(DEFAULT_CONFIG, data)
    except (OSError, ValueError) as e:
        print(f"[config] 读取失败，使用默认配置: {e}")
        return copy.deepcopy(DEFAULT_CONFIG)


def save_config(cfg):
    merged = _deep_merge(DEFAULT_CONFIG, cfg)
    _write_json(CONFIG_PATH, merged)
    return merged
