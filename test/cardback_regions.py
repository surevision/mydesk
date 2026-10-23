#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cardback_regions.py — 只跑卡背模型 cardback_best.pt，把检出的区域画出来。

不改任何识别算法：仅加载模型、对图片做一次推理、按给定阈值画 OBB 框。

运行：
  python test/cardback_regions.py --image test/t1.png --conf 0.05
  python test/cardback_regions.py --image test/dm6.jpg --conf 0.1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
sys.path.insert(0, str(ROOT_DIR / "center"))

import config as center_config  # noqa: E402
import recognize  # noqa: E402


def imread(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def imwrite(path: Path, image) -> bool:
    ok, buf = cv2.imencode(path.suffix or ".png", image)
    if not ok:
        return False
    buf.tofile(str(path))
    return True


def conf_color(conf: float):
    if conf >= 0.5:
        return (255, 0, 0)      # 蓝：高置信
    if conf >= 0.25:
        return (0, 165, 255)    # 橙：中
    return (0, 255, 255)        # 黄：低


def main():
    parser = argparse.ArgumentParser(description="输出卡背模型检出的区域")
    parser.add_argument("--image", default=str(BASE_DIR / "t1.png"))
    parser.add_argument("--conf", type=float, default=0.05)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    image = imread(image_path)
    if image is None:
        raise SystemExit(f"无法读取图片: {image_path}")

    cfg = center_config.load_config()
    models = recognize.Models(cfg)
    if not models.load():
        raise SystemExit(models.reason)
    det = models.make_detector("vertical")
    det._frame = image

    dets = det._infer(det.back, image, args.conf, 100000)
    dets.sort(key=lambda d: -d["conf"])
    print(f"image={image_path.name} {image.shape[1]}x{image.shape[0]} "
          f"conf>={args.conf} -> {len(dets)} 个框")

    vis = image.copy()
    for i, d in enumerate(dets, 1):
        color = conf_color(d["conf"])
        pts = d["corners"].astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(vis, [pts], True, color, 2)
        x, y = int(d["xywhr"][0]), int(d["xywhr"][1])
        w, h = d["xywhr"][2], d["xywhr"][3]
        cv2.putText(vis, f"#{i} {d['conf']:.3f}", (x - 30, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
        print(f"  #{i:<2} conf={d['conf']:.4f} center=({x},{y}) wh=({w:.0f},{h:.0f})")

    out = Path(args.out) if args.out else BASE_DIR / f"{image_path.stem}_cardback_regions.png"
    imwrite(out, vis)
    print(f"标注图 -> {out}")


if __name__ == "__main__":
    main()
