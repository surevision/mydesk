#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""t1_diag.py — 把当前识别算法在 t1.png 上的每一阶段画成中间过程图。

阶段：
  A 正面模型(ygo_yolo)原始检出
  B 卡背模型(cardback_best)原始检出
  C 每个检出框的矫正裁图拼版（带 dark/mean_v + ViT top1）
  D detect() 最终分类（side + source）

运行：
  python test/t1_diag.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
sys.path.insert(0, str(ROOT_DIR / "center"))

import config as center_config  # noqa: E402
import recognize  # noqa: E402
from blacklist import BlacklistStore  # noqa: E402


def imread(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def imwrite(path: Path, image) -> bool:
    ok, buf = cv2.imencode(path.suffix or ".png", image)
    if not ok:
        return False
    buf.tofile(str(path))
    return True


def hsv_stats(crop):
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2]
    s = crop.shape[0]
    c = v[int(s * 0.25):int(s * 0.75), int(s * 0.25):int(s * 0.75)]
    dark = float(np.sum(c < 60) / c.size) if c.size else 0.0
    return dark, float(np.mean(c)) if c.size else 0.0


def vit_top1(detector, crop):
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    s = detector.crop_size
    im = rgb if (rgb.shape[0] == s and rgb.shape[1] == s) \
        else cv2.resize(rgb, (s, s), interpolation=cv2.INTER_CUBIC)
    x = ((im.astype(np.float32) / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)[None]
    logits = detector.sess.run([detector.oname], {detector.iname: x})[0][0]
    e = np.exp(logits - logits.max())
    prob = e / e.sum()
    idx = int(np.argmax(prob))
    info = detector.names.get(str(idx)) or {}
    return info.get("EN", ""), float(prob[idx])


def draw_boxes(img, dets, color, title):
    for i, d in enumerate(dets):
        pts = d["corners"].astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(img, [pts], True, color, 2)
        cv2.putText(img, f"#{i} {d['conf']:.3f}",
                    (int(d["xywhr"][0]) - 40, int(d["xywhr"][1])),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
    cv2.putText(img, title, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2, cv2.LINE_AA)
    return img


def montage(crops, cols=6, cell=224, pad=28):
    if not crops:
        return np.zeros((cell + pad, cell, 3), np.uint8)
    rows = (len(crops) + cols - 1) // cols
    out = np.full((rows * (cell + pad), cols * cell, 3), 30, np.uint8)
    for i, (img, label) in enumerate(crops):
        r, c = divmod(i, cols)
        y0, x0 = r * (cell + pad), c * cell
        im = cv2.resize(img, (cell, cell))
        out[y0 + pad:y0 + pad + cell, x0:x0 + cell] = im
        cv2.putText(out, label, (x0 + 2, y0 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
    return out


def main():
    cfg = center_config.load_config()
    cfg["mode"] = "single"
    dcfg = cfg["detect"]
    print("config:", {k: dcfg[k] for k in ("front_conf", "back_conf", "name_thr")})

    models = recognize.Models(cfg)
    if not models.load():
        raise SystemExit(models.reason)
    models.blacklist = BlacklistStore()
    detector = models.make_detector("vertical")  # single 模式
    print("front_onnx:", detector.front_onnx, "imgsz:", detector.imgsz)

    image = imread(BASE_DIR / "t1.png")
    detector._frame = image
    h, w = image.shape[:2]

    # A 正面模型
    t = time.perf_counter()
    front = detector._infer_onnx(image, dcfg["front_conf"])
    print(f"front [{dcfg['front_conf']}] = {len(front)}  ({(time.perf_counter()-t)*1000:.0f}ms)")

    # B 卡背模型
    t = time.perf_counter()
    back = detector._infer(detector.back, image, dcfg["back_conf"], 100000)
    print(f"back  [{dcfg['back_conf']}] = {len(back)}  ({(time.perf_counter()-t)*1000:.0f}ms)")

    a = draw_boxes(image.copy(), front, (0, 255, 0),
                   f"STAGE A: front ygo_yolo conf>={dcfg['front_conf']} n={len(front)}")
    imwrite(BASE_DIR / "t1_stage_A_front.png", a)
    b = draw_boxes(image.copy(), back, (255, 0, 0),
                   f"STAGE B: back cardback_best conf>={dcfg['back_conf']} n={len(back)}")
    imwrite(BASE_DIR / "t1_stage_B_back.png", b)

    # C 裁图拼版
    crops = []
    print("\n--- per detection (front) ---")
    for i, d in enumerate(front):
        _s, ori, crop = detector.analyze_card(d["corners"], d["xywhr"])
        if crop is None:
            print(f"F#{i} crop=None")
            continue
        dark, mv = hsv_stats(crop)
        name, score = vit_top1(detector, crop)
        print(f"F#{i} conf={d['conf']:.3f} ori={ori} dark={dark:.2f} mean_v={mv:.0f} "
              f"vit='{name}' {score:.4f}")
        crops.append((crop.copy(), f"F#{i} d={dark:.2f} v={mv:.0f} {score:.3f}"))
    print("--- per detection (back) ---")
    for i, d in enumerate(back):
        _s, ori, crop = detector.analyze_card(d["corners"], d["xywhr"])
        if crop is None:
            print(f"B#{i} crop=None")
            continue
        dark, mv = hsv_stats(crop)
        name, score = vit_top1(detector, crop)
        print(f"B#{i} conf={d['conf']:.3f} ori={ori} dark={dark:.2f} mean_v={mv:.0f} "
              f"vit='{name}' {score:.4f}")
        crops.append((crop.copy(), f"B#{i} d={dark:.2f} v={mv:.0f} {score:.3f}"))
    imwrite(BASE_DIR / "t1_stage_C_crops.png", montage(crops))

    # D 最终
    final = detector.detect(image)
    vis = image.copy()
    for i, d in enumerate(final, 1):
        color = (0, 255, 0) if d["side"] == "front" else (255, 0, 0)
        pts = d["corners"].astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(vis, [pts], True, color, 2)
        info = d.get("info")
        label = f"{d['source']} {d['side']}"
        if info:
            label = f"{info['name'][:18]} {info['score']:.3f} [{d['source']}]"
        cv2.putText(vis, label, (int(d["cx"]) - 60, int(d["cy"])),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
    cv2.putText(vis, f"STAGE D: detect() n={len(final)}", (12, 34),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2, cv2.LINE_AA)
    imwrite(BASE_DIR / "t1_stage_D_final.png", vis)

    print(f"\nfinal = {len(final)}")
    for i, d in enumerate(final, 1):
        info = d.get("info")
        nm = f"{info['name']} {info['score']:.4f}" if info else "-"
        print(f"  #{i} {d['side']:5} {d['source']:8} ({d['cx']:.0f},{d['cy']:.0f}) {nm}")


if __name__ == "__main__":
    main()
