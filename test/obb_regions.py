#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""obb_regions.py — 用任意 OBB .pt 模型跑一张图，画出检测框并统计每框暗色程度。

用途：对比 cardcaptor_v3_best.pt / cardback_best.pt 等模型能否框到卡背。
不改识别算法，仅推理 + 画框 + HSV 统计。

运行：
  python test/obb_regions.py --image test/t1.png --model models/cardcaptor_v3_best.pt --conf 0.05
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent


def imread(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def imwrite(path: Path, image) -> bool:
    ok, buf = cv2.imencode(path.suffix or ".png", image)
    if not ok:
        return False
    buf.tofile(str(path))
    return True


def crop_quad(image, corners, size=224):
    pts = np.asarray(corners, dtype=np.float32).reshape(4, 2)
    if not np.all(np.isfinite(pts)):
        return None
    c = pts.mean(axis=0)
    pts = (c + (pts - c) * 0.92).astype(np.float32)
    dst = np.array([[0, 0], [size - 1, 0], [size - 1, size - 1], [0, size - 1]],
                   dtype=np.float32)
    try:
        M = cv2.getPerspectiveTransform(pts, dst)
        return cv2.warpPerspective(image, M, (size, size))
    except cv2.error:
        return None


def dark_stats(crop):
    if crop is None:
        return 0.0, 0.0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2]
    s = crop.shape[0]
    c = v[int(s * 0.25):int(s * 0.75), int(s * 0.25):int(s * 0.75)]
    if c.size == 0:
        return 0.0, 0.0
    return float((c < 60).mean()), float(c.mean())


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=str(BASE_DIR / "t1.png"))
    ap.add_argument("--model", default=str(ROOT_DIR / "models" / "cardcaptor_v3_best.pt"))
    ap.add_argument("--conf", type=float, default=0.05)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    from ultralytics import YOLO

    image_path = Path(args.image).resolve()
    image = imread(image_path)
    if image is None:
        raise SystemExit(f"无法读取图片: {image_path}")
    model = YOLO(args.model)
    print(f"model={Path(args.model).name} task={model.task} names={model.names}")
    r = model.predict(image, conf=args.conf, device=args.device, verbose=False)[0]
    if r.obb is None or len(r.obb) == 0:
        print(f"conf>={args.conf}: 0 个框")
        return

    pts = r.obb.xyxyxyxy.cpu().numpy()
    xywhr = r.obb.xywhr.cpu().numpy()
    confs = r.obb.conf.cpu().numpy()
    order = np.argsort(-confs)

    print(f"image={image_path.name} {image.shape[1]}x{image.shape[0]} "
          f"conf>={args.conf} -> {len(pts)} 个框")

    ref = {"top_black": (1419, 256, 1491, 309),
           "mid_dark": (1350, 450, 1395, 510),
           "bot_dark": (1455, 710, 1510, 750)}

    vis = image.copy()
    for rank, i in enumerate(order, 1):
        c = pts[i]
        bb = (c[:, 0].min(), c[:, 1].min(), c[:, 0].max(), c[:, 1].max())
        dark, mv = dark_stats(crop_quad(image, c))
        color = (255, 0, 0) if (dark > 0.5 and mv < 80) else (0, 200, 0)
        cv2.polylines(vis, [c.astype(np.int32).reshape((-1, 1, 2))], True, color, 2)
        x, y = int(xywhr[i][0]), int(xywhr[i][1])
        cv2.putText(vis, f"#{rank} {confs[i]:.2f} d={dark:.2f}", (x - 40, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        hits = [name for name, reg in ref.items() if iou(bb, reg) > 0.15]
        print(f"  #{rank:<2} conf={confs[i]:.4f} center=({x},{y}) "
              f"wh=({xywhr[i][2]:.0f},{xywhr[i][3]:.0f}) dark={dark:.2f} mean_v={mv:.0f}"
              f"{'  <== ' + ','.join(hits) if hits else ''}")

    out = Path(args.out) if args.out else BASE_DIR / f"{image_path.stem}_{Path(args.model).stem}_regions.png"
    imwrite(out, vis)
    print(f"标注图 -> {out}")


if __name__ == "__main__":
    main()
