# -*- coding: utf-8 -*-
"""
recognize.py
摄像头识别：读取视频流 → YOLO(OBB) 检测卡牌 → 透视矫正/朝向 → 卡名识别
（识别成功即正面）→ 未识别时由卡背模型判定，且区域为暗色才按反面，否则按卡面
→ 中心坐标映射到 (玩家, 格子) → 写入 BattlefieldStore。

多路并发：Models 只保存无状态共享资源（cv2/numpy、卡名 ONNX 会话、卡名库），
每路摄像头各自建一个 Detector（独占 YOLO 实例与跟踪器、卡名缓存），
因此两路摄像头可同时识别，且 OBB 跟踪 id 不会相互串号。

参考 test/videotest.py（实时）与 test/yolotest.py（图片）：
- OBB 结果同时给 corners 与 xywhr，朝向/尺寸用 xywhr 判断（更稳）。
- 使用 OBB 跟踪 id + 卡名缓存（TTL）避免每帧重跑 ONNX。
- 卡名识别用 onnxruntime，优先 CUDA( GPU ) 提供者。
- YOLO 推理走 GPU（device 可配置）。

依赖 cv2 / numpy / ultralytics / onnxruntime，均为延迟导入，未装时仅预览。
"""

import copy
import json
import os
import threading
import time

import gridmap
from calib import ORIENTATION_V, normalize_orientation
from state import empty_card


def _log(*a):
    print("[recog]", *a)


def _as_int(v, default=-1):
    """卡号统一成 int。cardnames_onnx.json 里 card_id 是字符串（如 "12580477"）。"""
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# ---- ONNX 检测（移植 draw2 网页版 docs/scripts/pipeline.js）----------------
def onnx_letterbox(cv2, np, frame, size):
    """等比缩放 + 黑边填充到 size×size，BGR→RGB、/255、NCHW。返回 (tensor, scale, padx, pady)。"""
    h, w = frame.shape[:2]
    scale = min(size / w, size / h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    padx, pady = (size - nw) // 2, (size - nh) // 2
    canvas = np.zeros((size, size, 3), dtype=np.float32)
    canvas[pady:pady + nh, padx:padx + nw] = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
    chw = canvas[:, :, ::-1].transpose(2, 0, 1)[None]
    return np.ascontiguousarray(chw, dtype=np.float32) / 255.0, scale, padx, pady


def obb_corners(np, cx, cy, w, h, angle):
    """(cx,cy,w,h,angle) → 4 个角点（环形顺序），angle 为弧度。"""
    cos, sin = float(np.cos(angle)), float(np.sin(angle))
    hw, hh = float(w) / 2.0, float(h) / 2.0
    pts = np.array([[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]], dtype=np.float32)
    R = np.array([[cos, -sin], [sin, cos]], dtype=np.float32)
    return pts @ R.T + np.array([cx, cy], dtype=np.float32)


def iou_xyxy(a, b):
    """两个 [x0,y0,x1,y1] 框的 IoU。"""
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return float(inter / ua) if ua > 0 else 0.0


def parse_onnx_obb(np, out, scale, padx, pady, conf_thr, nms_iou=0.5):
    """
    解析 ONNX 输出为检测列表。输出为 [6, N]（x,y,w,h,conf,angle）或 [N, 6]，
    conf 已是 0-1 概率，angle 为弧度；坐标在 640 黑边空间 → 还原到原图。
    先整表过滤再算角点：8400 行的逐元素循环在 Python 里要 ~1s，必须向量化。
    """
    data = out.T if out.shape[0] < out.shape[1] else out          # [N, 6]
    sel = data[data[:, 4] >= conf_thr]
    if sel.shape[0] == 0:
        return []
    cx = (sel[:, 0] - padx) / scale
    cy = (sel[:, 1] - pady) / scale
    bw = sel[:, 2] / scale
    bh = sel[:, 3] / scale
    ang = sel[:, 5]
    conf = sel[:, 4]
    # 与 obb_corners 同一变换：p' = p·R^T + c，R = [[cos,-sin],[sin,cos]]
    cos, sin = np.cos(ang), np.sin(ang)
    hw, hh = bw / 2.0, bh / 2.0
    base = np.array([[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]], dtype=np.float32)
    px = base[None, :, 0] * hw[:, None]
    py = base[None, :, 1] * hh[:, None]
    xs = cx[:, None] + px * cos[:, None] - py * sin[:, None]
    ys = cy[:, None] + px * sin[:, None] + py * cos[:, None]
    corners = np.stack([xs, ys], axis=2).astype(np.float32)       # [k, 4, 2]
    dets = [{"corners": corners[i],
             "xywhr": np.array([cx[i], cy[i], bw[i], bh[i], ang[i]], dtype=np.float32),
             "conf": float(conf[i])}
            for i in range(sel.shape[0])]
    return nms_obb(np, dets, iou_thr=nms_iou)


def onnx_letterbox_bgr(cv2, np, frame, w, h, color=114):
    """等比缩放 + 灰边填充到 w×h，保持 BGR、0-255。
    detector.onnx（卡背二分类）的输入约定：喂 RGB/255 时输出会全零，必须原样送 BGR。"""
    ih, iw = frame.shape[:2]
    scale = min(w / iw, h / ih)
    nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
    padx, pady = (w - nw) // 2, (h - nh) // 2
    canvas = np.full((h, w, 3), color, dtype=np.uint8)
    canvas[pady:pady + nh, padx:padx + nw] = cv2.resize(
        frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
    chw = canvas.transpose(2, 0, 1)[None]
    return np.ascontiguousarray(chw, dtype=np.float32), scale, padx, pady


def parse_detector_onnx(np, out, scale, padx, pady, conf, cls_index=1, nms_iou=0.5):
    """解析 detector.onnx：输出 [N,7] = x,y,w,h,obj,cls_front,cls_back。
    取第 cls_index 类（默认 1=卡背），置信度 = obj × cls；模型不输出角度，按轴对齐矩形处理。
    返回结构与 parse_onnx_obb 一致（corners/xywhr/conf）。"""
    data = out[0] if getattr(out, "ndim", 2) == 3 else out
    if data.shape[0] < data.shape[1]:                # [7,N] → [N,7]
        data = data.T
    score = data[:, 4] * data[:, 5 + cls_index]
    sel = np.where(score >= conf)[0]
    if sel.shape[0] == 0:
        return []
    d = data[sel]
    cx = (d[:, 0] - padx) / scale
    cy = (d[:, 1] - pady) / scale
    bw = d[:, 2] / scale
    bh = d[:, 3] / scale
    hw, hh = bw / 2.0, bh / 2.0
    xs = np.stack([cx - hw, cx + hw, cx + hw, cx - hw], axis=1)
    ys = np.stack([cy - hh, cy - hh, cy + hh, cy + hh], axis=1)
    corners = np.stack([xs, ys], axis=2).astype(np.float32)      # [k, 4, 2]
    dets = [{"corners": corners[i],
             "xywhr": np.array([cx[i], cy[i], bw[i], bh[i], 0.0], dtype=np.float32),
             "conf": float(score[sel[i]])}
            for i in range(sel.shape[0])]
    return nms_obb(np, dets, iou_thr=nms_iou)


def nms_obb(np, dets, iou_thr=0.5):
    """按置信度贪心 NMS（用四边形外接框的近似 IoU，整表向量化）。"""
    n = len(dets)
    if n == 0:
        return []
    bb = np.empty((n, 4), dtype=np.float32)
    conf = np.empty(n, dtype=np.float32)
    for i, d in enumerate(dets):
        c = d["corners"]
        bb[i] = (c[:, 0].min(), c[:, 1].min(), c[:, 0].max(), c[:, 1].max())
        conf[i] = d["conf"]
    x0 = np.maximum(bb[:, None, 0], bb[None, :, 0])
    y0 = np.maximum(bb[:, None, 1], bb[None, :, 1])
    x1 = np.minimum(bb[:, None, 2], bb[None, :, 2])
    y1 = np.minimum(bb[:, None, 3], bb[None, :, 3])
    inter = np.clip(x1 - x0, 0, None) * np.clip(y1 - y0, 0, None)
    area = (bb[:, 2] - bb[:, 0]) * (bb[:, 3] - bb[:, 1])
    iou = inter / np.maximum(area[:, None] + area[None, :] - inter, 1e-9)
    keep, dead = [], np.zeros(n, dtype=bool)
    for i in np.argsort(-conf, kind="stable"):
        if dead[i]:
            continue
        keep.append(int(i))
        dead |= iou[i] > iou_thr
    return [dets[i] for i in keep]


# 探测 torch 的 CUDA 可用性（只探一次），返回 (可用, 卡数, 说明)
_torch_state = None


def _torch_cuda():
    global _torch_state
    if _torch_state is None:
        try:
            import torch
            if torch.cuda.is_available():
                count = torch.cuda.device_count()
                try:
                    name = torch.cuda.get_device_name(0)
                except Exception:  # noqa: BLE001
                    name = "?"
                _torch_state = (True, count, f"CUDA 可用（{count} 卡：{name}）")
            else:
                _torch_state = (False, 0, "torch 无可用 CUDA（CPU 版？）→ 用 CPU")
        except Exception as e:  # noqa: BLE001
            _torch_state = (False, 0, f"未导入 torch（{e}）→ 用 CPU")
    return _torch_state


def _resolve_device(dev):
    """
    按「配置 + 实际环境」决定推理设备，返回 (device, 说明)。
    dev 为 "cpu" 时强制 CPU；为数字（如 0）时若 torch 无 CUDA 则自动回退 CPU，
    并纠正越界的卡号。
    """
    if isinstance(dev, str) and dev.strip().lower() == "cpu":
        return "cpu", "配置指定 CPU"
    avail, count, note = _torch_cuda()
    if not avail:
        return "cpu", note
    try:
        dev_i = int(dev)
    except (TypeError, ValueError):
        dev_i = 0
    if count and not (0 <= dev_i < count):
        return 0, f"{note}；请求 device={dev_i} 越界，改用 0"
    return dev_i, note


class Models:
    """共享资源：cv2/numpy、卡名 ONNX 会话与卡名库。
    每路摄像头各自 make_detector() 出一个 Detector（独占 YOLO 与跟踪器），
    只共享无状态的 ONNX 会话，从而可安全并发。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.cv2 = None
        self.np = None
        self.sess = None
        self.iname = None
        self.oname = None
        self.names = None
        self.providers = []
        self.decks = None        # DeckStore：已导入卡组（卡名识别候选约束），可空
        self.blacklist = None    # BlacklistStore：不按卡面处理的 card_id，可空
        self.ok = False          # 共享识别链路可用（cv2/numpy + ONNX + 卡名库）
        self.ready = False       # 至少 cv2 可用（能取流预览）
        self.reason = "未加载"

    def load(self):
        try:
            import cv2
            import numpy as np
        except Exception as e:  # noqa: BLE001
            self.reason = f"缺少 cv2/numpy，识别与预览不可用: {e}"
            _log(self.reason)
            return False
        self.cv2, self.np = cv2, np
        self.ready = True

        m = self.cfg["models"]
        missing = [k for k, p in m.items() if not os.path.exists(p)]
        if missing:
            self.reason = f"模型文件缺失（仅预览）: {', '.join(missing)}"
            _log(self.reason)
            return False
        try:
            import onnxruntime as ort
            from ultralytics import YOLO  # noqa: F401  （实际实例在 Detector 里建）
        except Exception as e:  # noqa: BLE001
            self.reason = f"缺少 ultralytics/onnxruntime（仅预览）: {e}"
            _log(self.reason)
            return False
        try:
            # onnxruntime 优先 GPU（CUDA），否则回退 CPU
            avail = ort.get_available_providers()
            self.providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider")
                              if p in avail]
            self.sess = ort.InferenceSession(m["name_onnx"], providers=self.providers or None)
            self.iname = self.sess.get_inputs()[0].name
            self.oname = self.sess.get_outputs()[0].name
            with open(m["names_json"], "r", encoding="utf-8") as f:
                self.names = json.load(f)
        except Exception as e:  # noqa: BLE001
            self.reason = f"模型加载失败（仅预览）: {e}"
            _log(self.reason)
            return False
        self.ok = True
        used = self.sess.get_providers()
        self.reason = f"已加载（卡名库 {len(self.names)} 张，ONNX: {'/'.join(used)}）"
        _log(self.reason)
        return True

    def make_detector(self, orientation="horizontal"):
        """为一路摄像头创建独立识别器（各自的 YOLO 实例与跟踪器）。"""
        return Detector(self, orientation)

    def device_info(self):
        dev, note = _resolve_device(self.cfg["detect"].get("device", 0))
        return {"providers": self.providers, "device": dev, "device_note": note}


class Detector:
    """单摄像头的识别器：独占 YOLO(front/back) 实例与跟踪器、卡名缓存。
    多个 Detector 之间只共享无状态的 ONNX 会话，可安全并发。"""

    def __init__(self, models, orientation="horizontal"):
        self.models = models
        self.orientation = normalize_orientation(orientation)
        self.cfg = models.cfg
        self.cv2 = models.cv2
        self.np = models.np
        self.sess = models.sess
        self.iname = models.iname
        self.oname = models.oname
        self.names = models.names
        self.decks = models.decks      # DeckStore（卡名识别候选约束），可空
        self.blacklist = models.blacklist  # BlacklistStore（不按卡面处理），可空
        self.front = None
        self.back = None
        self.front_onnx = False        # 正面检测是否用 ONNX（draw2 网页版同款）
        self.front_sess = None
        self.front_iname = None
        self.front_oname = None
        self.back_onnx = False         # 卡背检测是否用 ONNX（detector.onnx，正面/卡背二分类）
        self.back_sess = None
        self.back_iname = None
        self.back_oname = None
        self.back_w, self.back_h = 640, 384
        self.imgsz = 640
        self.ready = False
        self.error = ""
        self._frame = None
        self._cache = {}         # tid -> info | None
        self._seen = {}          # tid -> 最近出现时间
        self.timing = {}         # 上次 detect 各段耗时（秒）
        # ONNX 无内置跟踪器，用简单的 IoU 跟踪维持稳定 id（卡名缓存的键）
        self._tracks = {}        # tid -> (bbox[x0,y0,x1,y1], 最近时间)
        self._next_tid = 0
        # 移植 draw2：把卡矫正成 224×224 方图；只残余 0°/180° 歧义
        self.crop_size = int(self.cfg["detect"].get("crop_size", 224))
        self.flip_low = float(self.cfg["detect"].get("flip_low", 0.15))
        self.flip_margin = float(self.cfg["detect"].get("flip_margin", 1.25))
        self.nms_iou = float(self.cfg["detect"].get("nms_iou", 0.5))
        self.track_iou = float(self.cfg["detect"].get("track_iou", 0.3))
        self.track_ttl = float(self.cfg["detect"].get("track_ttl", 1.0))
        # 推理设备：按配置 + 环境自动决定（无 CUDA 时回退 CPU）
        self.device, self.device_note = _resolve_device(self.cfg["detect"].get("device", 0))
        m = self.cfg["models"]
        try:
            if str(m["yolo_front"]).lower().endswith(".onnx"):
                import onnxruntime as ort
                self.front_sess = ort.InferenceSession(
                    m["yolo_front"], providers=models.providers or None)
                self.front_iname = self.front_sess.get_inputs()[0].name
                self.front_oname = self.front_sess.get_outputs()[0].name
                shp = self.front_sess.get_inputs()[0].shape
                if len(shp) == 4 and isinstance(shp[2], int):
                    self.imgsz = int(shp[2])
                self.front_onnx = True
                _log(f"正面检测使用 ONNX：{os.path.basename(m['yolo_front'])} "
                     f"（{self.imgsz}px，{'/'.join(self.front_sess.get_providers())}）")
            else:
                from ultralytics import YOLO
                self.front = YOLO(m["yolo_front"])
            back_path = str(m["yolo_back"])
            if back_path.lower().endswith(".onnx"):
                import onnxruntime as ort
                self.back_sess = ort.InferenceSession(
                    back_path, providers=models.providers or None)
                self.back_iname = self.back_sess.get_inputs()[0].name
                self.back_oname = self.back_sess.get_outputs()[0].name
                shp = self.back_sess.get_inputs()[0].shape
                if len(shp) == 4 and isinstance(shp[2], int) and isinstance(shp[3], int):
                    self.back_h, self.back_w = int(shp[2]), int(shp[3])
                self.back_onnx = True
                _log(f"卡背检测使用 ONNX：{os.path.basename(back_path)} "
                     f"（{self.back_w}x{self.back_h}，{'/'.join(self.back_sess.get_providers())}）")
            else:
                from ultralytics import YOLO
                self.back = YOLO(back_path)
            self.ready = True
            _log(f"识别器就绪，设备 {self.device}（{self.device_note}）")
        except Exception as e:  # noqa: BLE001
            self.error = f"检测模型加载失败: {e}"
            _log(self.error)

    # ---- 卡名识别（带缓存）------------------------------------------------
    def _card_name(self, card_bgr, thr):
        cv2, np = self.cv2, self.np
        if card_bgr is None or card_bgr.size == 0:
            return None
        rgb = cv2.cvtColor(card_bgr, cv2.COLOR_BGR2RGB)
        s = self.crop_size
        im = rgb if (rgb.shape[0] == s and rgb.shape[1] == s) \
            else cv2.resize(rgb, (s, s), interpolation=cv2.INTER_CUBIC)
        x = ((im.astype(np.float32) / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)[None]
        logits = self.sess.run([self.oname], {self.iname: x})[0][0]
        e = np.exp(logits - logits.max())
        prob = e / e.sum()

        # 卡组约束（借鉴 draw2 的 --deck-list）：已导入卡组时，在前 top_k 候选中
        # 只接受 id 落在卡组并集里的那一个，从而抑制相近卡混淆；无卡组则退化为 top-1。
        deck = self.decks.all_ids() if self.decks is not None else None
        if deck:
            deck_str = {str(c) for c in deck}
            k = min(int(self.cfg["detect"].get("top_k", 15)), int(prob.shape[0]))
            outside = None
            for idx in np.argsort(prob)[::-1][:k]:
                if float(prob[idx]) < thr:
                    break                     # 已按概率排序，后面更低
                info = self.names.get(str(int(idx)))
                if not info:
                    continue
                candidate = {"card_id": _as_int(info.get("card_id")),
                             "name": info.get("EN", ""),
                             "score": float(prob[idx])}
                if info.get("card_id") in deck_str:
                    if self.blacklist is not None and candidate["card_id"] in self.blacklist:
                        return None
                    return candidate
                if outside is None:
                    outside = candidate
            # 卡组内没有达到阈值的候选；如果 draw2 认出了卡组外的卡，返回 outside 标记，
            # 由 detect() 忽略该卡名，改用 HSV 亮度判定卡背/未知正面。
            if outside is not None:
                outside["outside"] = True
                return outside
            return None

        idx = int(np.argmax(prob))
        if float(prob[idx]) < thr:
            return None
        info = self.names[str(idx)]
        card_id = _as_int(info.get("card_id"))
        if self.blacklist is not None and card_id in self.blacklist:
            return None
        return {"card_id": card_id, "name": info.get("EN", ""),
                "score": float(prob[idx])}

    def name_for(self, tid, crop, thr):
        if tid in self._cache:
            return self._cache[tid]
        cv2 = self.cv2
        # 移植 draw2：矫正后只剩 0°/180° 歧义。先用卡面上下亮度猜（正立时
        # 卡名条在下半部更亮，实测正立卡下半 15% 平均亮度更高），置信度太低
        # 再试另一方向，且必须明显更好（1.25×）才采纳，避免两张低分互换。
        if crop is not None and crop.size:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape[:2]
            m = max(1, int(round(h * 0.15)))
            gx = max(1, int(round(w * 0.15)))
            top = float(gray[:m, gx:w - gx].mean())
            bot = float(gray[h - m:, gx:w - gx].mean())
            if top > bot:
                crop = cv2.rotate(crop, cv2.ROTATE_180)
        info = self._card_name(crop, thr)
        if (info is None or info["score"] < self.flip_low) and crop is not None:
            base = info["score"] if info else 0.0
            alt = self._card_name(cv2.rotate(crop, cv2.ROTATE_180), thr)
            if alt is not None and alt["score"] > base * self.flip_margin \
                    and (info is None or alt["score"] > info["score"]):
                info = alt
        self._cache[tid] = info
        return info

    # ---- 透视矫正 + 朝向（移植 draw2：长边竖直 + 224 方图）----------------
    def analyze_card(self, corners, xywhr):
        cv2, np = self.cv2, self.np
        w_real = float(xywhr[2])
        h_real = float(xywhr[3])
        if w_real < 30 or h_real < 30:
            return None, "未知", None
        orientation = "横向" if w_real > h_real else "纵向"
        # 竖向/单摄像头画面相对横向画面旋转 90°，纵横相反：只翻转朝向标记
        if self.orientation == ORIENTATION_V or self.cfg.get("mode") == "single":
            orientation = "纵向" if orientation == "横向" else "横向"

        # 角点重排：先统一绕向（与目标同向，避免镜像），再从「短边」起，
        # 使卡片长边竖直 —— ViT 只会看到正立或倒置，不会被压扁/横躺。
        P = np.asarray(corners, dtype=np.float32).reshape(4, 2)
        if not np.all(np.isfinite(P)):
            return None, orientation, None
        area = float(np.sum(P[:, 0] * np.roll(P[:, 1], -1)
                            - np.roll(P[:, 0], -1) * P[:, 1]))
        if abs(area) < 1e-3:                     # 退化为一条线
            return None, orientation, None
        if area < 0:
            P = P[::-1].copy()
        edges = np.linalg.norm(np.roll(P, -1, axis=0) - P, axis=1)
        ordered = np.roll(P, -int(np.argmin(edges)), axis=0)

        S = self.crop_size
        dst = np.array([[0, 0], [S - 1, 0], [S - 1, S - 1], [0, S - 1]], dtype=np.float32)
        try:
            M = cv2.getPerspectiveTransform(ordered, dst)
            crop = cv2.warpPerspective(self._frame, M, (S, S))
        except cv2.error:  # noqa: BLE001  个别奇异四边形
            return None, orientation, None
        return None, orientation, crop

    def is_dark_back(self, crop):
        """用中心区域亮度判断是否为暗色卡背；卡背模型命中、卡组外识别时使用。"""
        if crop is None or crop.size == 0:
            return False
        hsv = self.cv2.cvtColor(crop, self.cv2.COLOR_BGR2HSV)
        _h, _s, v_ch = self.cv2.split(hsv)
        S = crop.shape[0]
        center_v = v_ch[int(S * 0.25):int(S * 0.75), int(S * 0.25):int(S * 0.75)]
        if center_v.size == 0:
            return False
        dark = float(self.np.sum(center_v < 60) / center_v.size)
        mean_v = float(self.np.mean(center_v))
        return dark > 0.6 and mean_v < 80

    # ---- 检测 -------------------------------------------------------------
    @staticmethod
    def _crop(frame, roi):
        """按 ROI 裁剪帧。返回 (图, ox, oy)；不裁时返回原帧与 0,0。"""
        if not roi:
            return frame, 0, 0
        h, w = frame.shape[:2]
        x0 = max(0, min(int(roi[0]), w - 1))
        y0 = max(0, min(int(roi[1]), h - 1))
        x1 = max(x0 + 1, min(int(roi[2]), w))
        y1 = max(y0 + 1, min(int(roi[3]), h))
        if x1 - x0 < 32 or y1 - y0 < 32:
            return frame, 0, 0
        if x0 == 0 and y0 == 0 and x1 == w and y1 == h:
            return frame, 0, 0
        return frame[y0:y1, x0:x1], x0, y0

    def _shift(self, dets, ox, oy):
        """裁剪坐标 → 整帧坐标（下游落格/画框都用整帧坐标）。"""
        d = self.np.array([ox, oy], dtype=self.np.float32)
        for det in dets:
            det["corners"] = (det["corners"] + d).astype(self.np.float32)
            xy = det["xywhr"].copy()
            xy[0] += ox
            xy[1] += oy
            det["xywhr"] = xy

    def detect(self, frame, roi=None):
        """roi=(x0,y0,x1,y1)：只在该区域做检测与卡名识别（框选之外不识别）。"""
        self._frame = frame
        cfg = self.cfg["detect"]
        np = self.np
        out = []
        _t = time.perf_counter
        t_all = _t()
        src, ox, oy = self._crop(frame, roi)
        t0 = _t()
        if self.front_onnx:
            front = self._infer_onnx(src, cfg["front_conf"])
        else:
            front = self._infer(self.front, src, cfg["front_conf"], 0)
        t_front = _t() - t0
        t0 = _t()
        if self.back_onnx:
            back = self._infer_back_onnx(src, cfg["back_conf"])
        else:
            back = self._infer(self.back, src, cfg["back_conf"], 100000)
        t_back = _t() - t0
        if ox or oy:
            self._shift(front, ox, oy)
            self._shift(back, ox, oy)
        now = time.time()
        if self.front_onnx:
            self._assign_tids(front, now)
        if self.back_onnx:
            self._assign_tids(back, now)

        def near(a, b):
            return (abs(a["xywhr"][0] - b["xywhr"][0]) < 30
                    and abs(a["xywhr"][1] - b["xywhr"][1]) < 30)

        def classify(info, is_back, dark):
            # 卡组外的卡名不输出，也不采信 draw2 的低阈值结果；
            # 改用 HSV 亮度判断：暗色按卡背，否则按未知正面卡牌。
            outside = bool(info and info.get("outside"))
            if outside:
                return "back" if dark else "front"
            named = bool(info)
            return "front" if named or not is_back else "back"

        def visible_info(info):
            return None if (info is None or info.get("outside")) else info

        def source_of(info, side, has_back):
            if side == "front":
                if info and info.get("outside"):
                    return "DECK/HSV"
                return "ViT" if info else "ViT-none"
            return "CB" if (self.back_onnx and has_back) else ("CB+HSV" if has_back else "HSV")

        fronts = []
        for d in front:
            _side, ori, crop = self.analyze_card(d["corners"], d["xywhr"])
            if crop is None:
                continue
            info = self.name_for(d["tid"], crop, cfg["name_thr"])
            dark = self.is_dark_back(crop) if (info and info.get("outside")) else False
            fronts.append([d, ori, info, False, dark])

        back_only = []
        for d in back:
            _side, ori, crop = self.analyze_card(d["corners"], d["xywhr"])
            if crop is None:
                continue
            if self.back_onnx:
                # detector.onnx 直接输出「正面/卡背」两类，卡背类直接采信，不再用亮度或卡名反推
                dark = True
            else:
                dark = self.is_dark_back(crop)
            hit = next((f for f in fronts if near(d, f[0])), None)
            if hit is not None:
                if dark:
                    hit[3] = True
                    hit[4] = True
                continue
            info = None if self.back_onnx else self.name_for(
                d["tid"], crop, cfg["name_thr"])
            back_only.append((d, ori, info, dark))

        for d, ori, info, has_back, dark in fronts:
            side = classify(info, has_back, dark)
            self._seen[d["tid"]] = now
            out.append(self._make(
                d, side, ori, visible_info(info) if side == "front" else None, np,
                source_of(info, side, has_back)))
        for d, ori, info, dark in back_only:
            side = classify(info, dark, dark)
            self._seen[d["tid"]] = now
            out.append(self._make(
                d, side, ori, visible_info(info) if side == "front" else None, np,
                source_of(info, side, dark)))
        # 清理过期缓存
        ttl = float(cfg.get("name_cache_ttl", 3.0))
        for tid in [t for t, ts in self._seen.items() if now - ts > ttl]:
            self._seen.pop(tid, None)
            self._cache.pop(tid, None)
        self.timing = {"front": t_front, "back": t_back, "total": _t() - t_all,
                       "n_front": len(front), "n_back": len(back)}
        return out

    def _infer(self, model, frame, conf, id_offset):
        cfg = self.cfg["detect"]
        device = self.device          # 已解析（无 CUDA 时为 "cpu"）
        use_track = bool(cfg.get("track", True))
        try:
            if use_track:
                # 默认 tracker（tracktrack/botsort）带 GMC 稀疏光流：静态机位用不上，且我们
                # 喂的是裁剪帧，尺寸一变就会每帧刷 “GMC failed” 警告。ByteTrack 无 GMC。
                r = model.track(frame, persist=True, conf=conf, device=device,
                                verbose=False, tracker="bytetrack.yaml")[0]
            else:
                r = model.predict(frame, conf=conf, device=device, verbose=False)[0]
        except Exception as e:  # noqa: BLE001
            _log(f"推理失败: {e}")
            return []
        if r.obb is None or len(r.obb) == 0:
            return []
        pts = r.obb.xyxyxyxy.cpu().numpy()
        xywhr = r.obb.xywhr.cpu().numpy()
        confs = r.obb.conf.cpu().numpy()
        if r.obb.id is not None:
            ids = r.obb.id.cpu().numpy().astype(int)
        else:
            ids = self.np.arange(len(pts)) + id_offset
        return [{"corners": c.copy(), "xywhr": b.copy(), "tid": int(t),
                 "conf": float(cf)}
                for c, b, t, cf in zip(pts, xywhr, ids, confs)]

    # ---- ONNX 检测（draw2 网页版写法）-------------------------------------
    def _infer_onnx(self, frame, conf):
        try:
            tensor, scale, padx, pady = onnx_letterbox(self.cv2, self.np, frame, self.imgsz)
            out = self.front_sess.run([self.front_oname], {self.front_iname: tensor})[0][0]
        except Exception as e:  # noqa: BLE001
            _log(f"ONNX 推理失败: {e}")
            return []
        return parse_onnx_obb(self.np, out, scale, padx, pady, conf, self.nms_iou)

    def _infer_back_onnx(self, frame, conf):
        """卡背检测（detector.onnx）：BGR 0-255、灰边、非方形输入；取卡背类，得分 = obj×cls。"""
        try:
            tensor, scale, padx, pady = onnx_letterbox_bgr(
                self.cv2, self.np, frame, self.back_w, self.back_h)
            out = self.back_sess.run([self.back_oname], {self.back_iname: tensor})[0]
        except Exception as e:  # noqa: BLE001
            _log(f"卡背 ONNX 推理失败: {e}")
            return []
        return parse_detector_onnx(self.np, out, scale, padx, pady, conf, 1, self.nms_iou)

    def _assign_tids(self, dets, now):
        """简单 IoU 跟踪：给 ONNX 检测分配稳定 id（卡名缓存的键）。就地写 d['tid']。"""
        np = self.np
        for tid in [t for t, (_, ts) in self._tracks.items() if now - ts > self.track_ttl]:
            self._tracks.pop(tid, None)
        used = set()
        for d in dets:
            c = d["corners"]
            bb = np.array([c[:, 0].min(), c[:, 1].min(), c[:, 0].max(), c[:, 1].max()],
                          dtype=np.float32)
            best, best_iou = None, self.track_iou
            for tid, (tb, _) in self._tracks.items():
                if tid in used:
                    continue
                i = iou_xyxy(bb, tb)
                if i > best_iou:
                    best, best_iou = tid, i
            if best is None:
                best = self._next_tid
                self._next_tid += 1
            used.add(best)
            self._tracks[best] = (bb, now)
            d["tid"] = int(best)
        return dets

    def _make(self, d, side, ori, info, np, source=""):
        cx, cy = float(d["xywhr"][0]), float(d["xywhr"][1])
        return {
            "corners": d["corners"], "xywhr": d["xywhr"],
            "cx": cx, "cy": cy, "side": side,
            "orientation": "vertical" if ori == "纵向" else "horizontal",
            "info": info, "source": source,
        }


class CameraWorker(threading.Thread):
    def __init__(self, cam_id, url, players, store, models, cfg, frames,
                 calib=None, raw_frames=None, orientation="horizontal"):
        super().__init__(name=f"cam-{cam_id}", daemon=True)
        self.cam_id = cam_id
        self.url = url
        self.players = players           # 该摄像头负责的玩家列表 [1] 或 [1,2]
        self.orientation = normalize_orientation(orientation)
        self.store = store
        self.models = models             # 共享资源（cv2 等）
        self.cfg = cfg
        self.frames = frames            # {cam_id: jpeg bytes} 预览（带叠加）
        self.calib = calib              # CalibrationStore 或 None
        self.raw_frames = raw_frames    # {cam_id: bgr frame} 原始帧（校准用）
        self.detector = None            # 本摄像头独立的识别器（在 run 里创建）
        self._stopping = threading.Event()
        self.connected = False
        self.fps = 0.0
        self.detections = 0
        self.error = ""
        self._last_reco = None          # 上次打印的识别结果（变化时才打印）
        self._latest = None             # 最新原始帧（采集线程写）
        self._latest_seq = 0
        self._result = None             # 最近一次识别结果（识别线程写）
        self._read_avg = 0.0
        self._proc_avg = self._front_avg = self._back_avg = 0.0
        self._proc_n = 0
        self._keep = {}                 # player -> {(zone, idx): {"card":..., "miss": n}}

    def stop(self):
        self._stopping.set()

    def _open(self):
        cv2 = self.models.cv2
        is_local = str(self.url).isdigit()
        src = int(self.url) if is_local else self.url
        if not is_local:
            # 网络流：让 FFmpeg 不缓存、低延迟，尽量取最新帧（否则积压导致画面落后几秒）
            os.environ.setdefault(
                "OPENCV_FFMPEG_CAPTURE_OPTIONS",
                "fflags;nobuffer|flags;low_delay|reorder_queue_size;0")
        cap = cv2.VideoCapture(src)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:  # noqa: BLE001
            pass
        return cap

    def run(self):
        cv2 = self.models.cv2
        if cv2 is None:
            self.error = self.models.reason
            return
        # 本路独立识别器：独占 YOLO 与跟踪器，和多路并发互不干扰
        if self.models.ok:
            self.detector = self.models.make_detector(self.orientation)
        interval = max(0.05, float(self.cfg["detect"]["interval"]))
        # 采集 / 识别 / 发布拆成三条线程：识别慢时预览仍按采集帧率刷新，
        # 不再被推理拖成 1fps；识别只取最新帧，慢一点也只是结果稍旧。
        threading.Thread(target=self._reader, name=f"cam-{self.cam_id}-read",
                         daemon=True).start()
        if self.detector is not None:
            threading.Thread(target=self._detector_loop, args=(interval,),
                             name=f"cam-{self.cam_id}-det", daemon=True).start()
        self._publish_loop()

    def _reader(self):
        """持续读帧，只更新最新帧；读帧失败自动重连。"""
        cap = self._open()
        if not cap.isOpened():
            self.error = f"无法打开视频源: {self.url}"
            _log(self.error)
            return
        self.connected = True
        self.error = ""
        retries = 0
        _t = time.perf_counter
        while not self._stopping.is_set():
            tr = _t()
            ret, frame = cap.read()
            dt = _t() - tr
            if not ret or frame is None:
                self.connected = False
                retries += 1
                cap.release()
                if retries > 5:
                    self.error = "连续读帧失败，已停止重连"
                    break
                time.sleep(0.5)
                cap = self._open()
                self.connected = cap.isOpened()
                continue
            retries = 0
            self.connected = True
            self._read_avg = dt if not self._read_avg else self._read_avg * 0.8 + dt * 0.2
            self._latest = frame
            self._latest_seq += 1
        cap.release()
        self.connected = False

    def _detector_loop(self, interval):
        """取最新帧做识别（按 interval 限频），结果给发布线程复用。"""
        _t = time.perf_counter
        last_seq = -1
        last = 0.0
        paused = False
        while not self._stopping.is_set():
            frame = self._latest
            seq = self._latest_seq
            now = time.time()
            enabled = bool(self.cfg.get("recognition_enabled", True))
            # 暂停/断线/模型未就绪：这一轮根本不会识别，卡可能已被拿走或换掉
            idle = frame is None or not enabled or not self.detector.ready
            if idle or seq == last_seq or now - last < interval:
                if idle and not paused:
                    self._keep.clear()
                    paused = True
                time.sleep(0.01)
                continue
            paused = False
            last_seq = seq
            last = now
            try:
                tp = _t()
                result = self._process(frame)
                dt = _t() - tp
            except Exception as e:  # noqa: BLE001
                self.error = f"识别异常: {e}"
                _log(self.error)
                time.sleep(0.2)
                continue
            self._result = result
            tm = self.detector.timing
            f, b = tm.get("front", 0.0), tm.get("back", 0.0)
            self._proc_avg = dt if not self._proc_avg else self._proc_avg * 0.8 + dt * 0.2
            self._front_avg = f if not self._front_avg else self._front_avg * 0.8 + f * 0.2
            self._back_avg = b if not self._back_avg else self._back_avg * 0.8 + b * 0.2
            self._proc_n += 1

    def _publish_loop(self):
        """有新帧就发布预览（带最近一次识别结果），每 ~2 秒打印一次统计。"""
        _t = time.perf_counter
        count = 0
        t0 = time.time()
        last_seq = -1
        sum_pub = 0.0
        while not self._stopping.is_set():
            seq = self._latest_seq
            frame = self._latest
            if frame is None or seq == last_seq:
                time.sleep(0.005)
                continue
            last_seq = seq
            count += 1
            tp = _t()
            self._publish(frame, self._result)
            sum_pub += _t() - tp
            now = time.time()
            if now - t0 >= 2.0:
                n = count or 1
                self.fps = count / (now - t0)
                if self._proc_n:
                    proc_txt = (f"解析 {self._proc_avg * 1000:.0f}ms×{self._proc_n}"
                                f" (前 {self._front_avg * 1000:.0f}"
                                f"/背 {self._back_avg * 1000:.0f}ms)")
                elif self.detector is None:
                    proc_txt = "解析 未运行"
                else:
                    proc_txt = "解析 0ms×0"
                _log(f"[{self.cam_id}] 帧率 {self.fps:.1f} | {proc_txt}"
                     f" | 发布 {sum_pub / n * 1000:.0f}ms"
                     f" | 读帧 {self._read_avg * 1000:.0f}ms"
                     f" | 卡 {self.detections}")
                count = 0
                t0 = now
                sum_pub = 0.0
                self._proc_n = 0

    def _calib_roi(self, frame):
        """本路所有已校准玩家格子区域的外接框（整帧像素）；未校准则 None。"""
        if self.calib is None:
            return None
        polys = []
        h, w = frame.shape[:2]
        for p in self.players:
            pc = self.calib.get(self.cam_id, p)
            if pc is None:
                continue
            if tuple(pc.frame_size) != (w, h):
                continue          # 分辨率变了，旧像素坐标不可用
            polys.extend(poly for _zone, _idx, poly in pc.polygons())
        if not polys:
            return None
        xs = [pt[0] for poly in polys for pt in poly]
        ys = [pt[1] for poly in polys for pt in poly]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        # 留一点边，避免贴边卡片被裁掉
        mx = (x1 - x0) * 0.03 + 4
        my = (y1 - y0) * 0.03 + 4
        return (max(0, int(x0 - mx)), max(0, int(y0 - my)),
                min(w, int(x1 + mx)), min(h, int(y1 + my)))

    def _process(self, frame):
        dets = self.detector.detect(frame, self._calib_roi(frame))
        by_player = {p: {} for p in self.players}
        layout = self.cfg["layout"]
        mode = self.cfg["mode"]
        p1_side = self.cfg["single"]["player1_side"]
        swap = self.cfg["dual"].get("swap", False)
        h, w = frame.shape[:2]
        for d in dets:
            hit = None
            for p in self.players:
                pc = self.calib.get(self.cam_id, p) if self.calib is not None else None
                if pc is not None:
                    # 已校准：卡牌中心（像素）经单应映射到正空间 → 查格子
                    cell = pc.map_point(d["cx"], d["cy"])
                else:
                    # 未校准：回退旧的「玩家区域矩形 + 归一化 layout」映射
                    nx, ny = d["cx"] / w, d["cy"] / h
                    area = gridmap.player_area(mode, p1_side, p, swap)
                    cell = gridmap.map_point(layout, nx, ny, area)
                if cell:
                    hit = (p, cell)
                    break
            if not hit:
                continue
            p, (zone, index) = hit
            card = empty_card(
                face_up=(d["side"] == "front"), orientation=d["orientation"])
            card["extra"] = {"source": d.get("source", "")}
            if d["info"]:
                card["id"] = _as_int(d["info"].get("card_id"))
                card["name"] = d["info"]["name"]
                card["extra"]["score"] = d["info"]["score"]
            by_player[p][(zone, index)] = card
        self._keep_names(by_player)
        for p in self.players:
            self.store.apply_recognition(p, by_player[p])
        self.detections = sum(len(v) for v in by_player.values())
        self._log_reco(by_player)
        return dets

    def _keep_names(self, by_player):
        """卡名保持：这一轮该格有卡但没认出名字时，沿用该格上次认出的卡名。

        只在「正面且无卡名」时沿用；看到卡背视为状态变了，直接忘掉。
        该格这一轮没有卡（没检测到）就清记忆 —— 之后再来未知卡，就按未知卡处理，
        不会把旧名字贴到新卡上。
        """
        for p in self.players:
            mem = self._keep.setdefault(p, {})
            cells = by_player[p]
            for key in list(mem):
                if key not in cells:
                    mem.pop(key, None)
            for key, card in cells.items():
                if not card.get("face_up"):
                    mem.pop(key, None)          # 卡背：这一格换状态了
                    continue
                if card.get("name"):
                    mem[key] = copy.deepcopy(card)
                    continue
                kept = mem.get(key)
                if kept is None:
                    continue                    # 真的没认出过，就按未知卡
                kept = copy.deepcopy(kept)
                kept["face_up"] = card.get("face_up", True)
                kept["orientation"] = card.get("orientation") or kept.get("orientation")
                kept.setdefault("extra", {})["source"] = "keep"
                cells[key] = kept

    def _log_reco(self, by_player):
        """打印卡名识别结果（内容变化时才打印，避免每个识别周期刷屏）。"""
        def sort_key(kv):
            zone, index = kv[0]
            return (zone, index if index is not None else -1)

        items = []
        for p in self.players:
            for (zone, index), card in sorted(by_player[p].items(), key=sort_key):
                loc = f"P{p} {zone}{index + 1 if index else ''}"
                extra = card.get("extra", {})
                source = extra.get("source", "")
                if card.get("name"):
                    items.append(f"{loc} {card['name']}({card['id']}) "
                                 f"{extra.get('score', 0):.4f} [{source}]")
                else:
                    items.append(f"{loc} {'卡背' if not card.get('face_up') else '未识别'}"
                                 f" [{source}]")
        txt = " | ".join(items)
        if txt != self._last_reco:
            self._last_reco = txt
            _log(f"[{self.cam_id}] 识别 {txt or '（无）'}")

    def _publish(self, frame, dets):
        cv2 = self.models.cv2
        if self.raw_frames is not None:
            self.raw_frames[self.cam_id] = frame     # 原始帧（不带叠加），供校准取样
        img = frame.copy()
        if self.cfg.get("_overlay", True):
            self._draw_layout(img)
        if dets:
            for d in dets:
                color = (0, 255, 0) if d["side"] == "front" else (255, 0, 0)
                pts = d["corners"].astype(int).reshape((-1, 1, 2))
                cv2.polylines(img, [pts], True, color, 2)
                source = d.get("source", "")
                label = f"{source} {d['side']}"
                if d["info"]:
                    label = f"{d['info']['name'][:24]} {d['info']['score']:.4f} [{source}]"
                cv2.putText(img, label, (int(d["cx"]) - 40, int(d["cy"])),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if ok:
            self.frames[self.cam_id] = buf.tobytes()

    def _draw_layout(self, img):
        # 仅在已定位后，把正空间格子映射回画面画战场网格；
        # 未定位时不画（默认归一化区域并不代表真实战场位置）。
        if self.calib is None:
            return
        cv2 = self.models.cv2
        np = self.models.np
        for p in self.players:
            pc = self.calib.get(self.cam_id, p)
            if pc is None:
                continue
            for zone, index, poly in pc.polygons():
                pts = np.array(poly, dtype=np.int32).reshape((-1, 1, 2))
                cv2.polylines(img, [pts], True, (0, 255, 255), 1)
                cx = int(sum(pt[0] for pt in poly) / len(poly))
                cy = int(sum(pt[1] for pt in poly) / len(poly))
                cv2.putText(img, f"{zone}{index if index is not None else ''}",
                            (cx - 12, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

    def status(self):
        return {
            "id": self.cam_id, "url": self.url, "players": self.players,
            "orientation": self.orientation,
            "connected": self.connected, "fps": round(self.fps, 1),
            "detections": self.detections, "error": self.error,
            "model": self.detector.error if (self.detector and not self.detector.ready) else "",
        }


class RecognitionManager:
    def __init__(self, store, cfg, calib=None, decks=None, blacklist=None):
        self.store = store
        self.cfg = cfg
        self.calib = calib
        self.decks = decks               # DeckStore（卡名识别候选约束），可空
        self.models = Models(cfg)
        self.models.decks = decks
        self.models.blacklist = blacklist
        self.workers = []
        self.frames = {}
        self.raw_frames = {}
        self._lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._load_and_run, name="model-load", daemon=True).start()

    def _load_and_run(self):
        self.models.load()
        self.restart()

    def restart(self):
        with self._lock:
            for w in self.workers:
                w.stop()
            self.workers = []
            mode = self.cfg["mode"]
            if mode == "dual":
                swap = bool(self.cfg["dual"].get("swap", False))
                for i, cam in enumerate(self.cfg["dual"]["cameras"]):
                    player = cam.get("player", i + 1)
                    if swap:
                        player = 2 if str(player) == "1" else 1
                    self.workers.append(CameraWorker(
                        f"cam{i+1}", cam["url"], [player], self.store, self.models, self.cfg,
                        self.frames, self.calib, self.raw_frames,
                        orientation=cam.get("orientation", "horizontal")))
            else:
                self.workers.append(CameraWorker(
                    "single", self.cfg["single"]["url"], [1, 2], self.store, self.models, self.cfg,
                    self.frames, self.calib, self.raw_frames,
                    orientation="vertical"))
            for w in self.workers:
                w.start()

    def stop(self):
        with self._lock:
            for w in self.workers:
                w.stop()
            self.workers = []

    def get_frame(self, cam_id):
        return self.frames.get(cam_id)

    def get_raw_frame(self, cam_id):
        """原始帧（不带叠加），用于校准取样。"""
        return self.raw_frames.get(cam_id)

    def status(self):
        with self._lock:
            workers = [w.status() for w in self.workers]
        st = {
            "mode": self.cfg["mode"],
            "models_ok": self.models.ok,
            "models_ready": self.models.ready,
            "models_reason": self.models.reason,
            "cameras": workers,
            "decks": self.decks.summary() if self.decks is not None else {},
        }
        st.update(self.models.device_info())
        return st
