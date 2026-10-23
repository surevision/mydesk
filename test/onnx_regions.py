#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""onnx_regions.py — 跑一个 YOLO 检测 ONNX（轴对齐 bbox），把检出的框画出来。

输出 [1, 5, N]（x,y,w,h,conf，单类）或 [1, 4+nc, N]。只推理 + 画框，不做分析。

运行：
  python test/onnx_regions.py --image test/t1.png --model models/best.onnx --conf 0.25
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=str(BASE_DIR / "t1.png"))
    ap.add_argument("--model", default=str(ROOT_DIR / "models" / "best.onnx"))
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--nms", type=float, default=0.5)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    import onnxruntime as ort

    image_path = Path(args.image).resolve()
    image = imread(image_path)
    if image is None:
        raise SystemExit(f"无法读取图片: {image_path}")

    sess = ort.InferenceSession(args.model, providers=["CPUExecutionProvider"])
    iname = sess.get_inputs()[0].name
    oname = sess.get_outputs()[0].name
    shape = sess.get_inputs()[0].shape
    size = int(shape[2]) if len(shape) == 4 and isinstance(shape[2], int) else 640

    tensor, scale, padx, pady = recognize.onnx_letterbox(cv2, np, image, size)
    out = sess.run([oname], {iname: tensor})[0][0]
    data = out.T if out.shape[0] < out.shape[1] else out          # [N, 4+nc]

    confs = data[:, 4]
    sel = data[confs >= args.conf]
    boxes, scores = [], []
    for row in sel:
        cx, cy, w, h = row[0], row[1], row[2], row[3]
        x = (cx - padx) / scale
        y = (cy - pady) / scale
        bw = w / scale
        bh = h / scale
        boxes.append([float(x - bw / 2), float(y - bh / 2), float(bw), float(bh)])
        scores.append(float(row[4]))

    if boxes:
        idx = cv2.dnn.NMSBoxes(boxes, scores, args.conf, args.nms)
        idx = np.array(idx).reshape(-1).tolist()
    else:
        idx = []

    print(f"model={Path(args.model).name} size={size} image={image_path.name} "
          f"{image.shape[1]}x{image.shape[0]} conf>={args.conf} -> {len(idx)} 框"
          f"（NMS 前 {len(boxes)}）")

    vis = image.copy()
    order = sorted(idx, key=lambda i: -scores[i])
    for rank, i in enumerate(order, 1):
        x, y, w, h = boxes[i]
        cv2.rectangle(vis, (int(x), int(y)), (int(x + w), int(y + h)), (0, 255, 0), 2)
        cv2.putText(vis, f"#{rank} {scores[i]:.2f}", (int(x), int(y) - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
        print(f"  #{rank:<2} conf={scores[i]:.4f} xyxy=({x:.0f},{y:.0f},{x + w:.0f},{y + h:.0f}) "
              f"wh=({w:.0f},{h:.0f})")

    out_path = Path(args.out) if args.out else \
        BASE_DIR / f"{image_path.stem}_{Path(args.model).stem}_regions.png"
    imwrite(out_path, vis)
    print(f"标注图 -> {out_path}")


if __name__ == "__main__":
    main()
