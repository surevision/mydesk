#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nowyolotest.py — 逐阶段检查 test.jpg 为什么最终没有识别结果。

直接复用 center/recognize.py 的：
  Models / Detector / onnx_letterbox / parse_onnx_obb / analyze_card / _card_name

输出：
  1. 模型与图片信息
  2. 原始 ONNX 输出的置信度分布、各阈值检出数
  3. 每个检测框的裁切、HSV 统计、卡名 top-k
  4. Detector.detect() 的最终结果
  5. 标注图 + 每个卡片的矫正裁图

注意：draw2 网页不做“正反面过滤”，所有 YOLO 检测框都会继续分类/显示。
      当前 recognize.py 的顺序是：先做卡名识别，识别成功即按正面；
      未识别时由卡背模型判断，命中且区域为暗色才按反面，否则按卡面（无卡名）。

运行：
  python test/nowyolotest.py
  python test/nowyolotest.py --image test/test.jpg --conf 0.01
"""

from __future__ import annotations

import argparse
import json
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
    ok, buf = cv2.imencode(path.suffix or ".jpg", image)
    if not ok:
        return False
    buf.tofile(str(path))
    return True


def load_detector(cfg):
    print("=" * 78)
    print("1. 模型加载")
    print("=" * 78)
    models = recognize.Models(cfg)
    ok = models.load()
    print(f"models.load() = {ok}")
    print(f"reason: {models.reason}")
    print(f"providers: {models.providers}")
    print(f"front model: {cfg['models']['yolo_front']}")
    print(f"name model : {cfg['models']['name_onnx']}")
    if not ok:
        raise SystemExit("共享模型加载失败，后续无法检查。")

    blacklist = BlacklistStore()
    models.blacklist = blacklist
    print(f"blacklist: {blacklist.ids()}")

    detector = models.make_detector("horizontal")
    print(f"detector.ready = {detector.ready}")
    if detector.error:
        print(f"detector.error = {detector.error}")
    if not detector.ready:
        raise SystemExit("检测器加载失败，后续无法检查。")
    print(f"front ONNX: {detector.front_onnx}, imgsz={detector.imgsz}")
    if detector.front_sess is not None:
        inp = detector.front_sess.get_inputs()[0]
        out = detector.front_sess.get_outputs()[0]
        print(f"ONNX input : name={inp.name!r} shape={inp.shape} type={inp.type}")
        print(f"ONNX output: name={out.name!r} shape={out.shape} type={out.type}")
    return models, detector


def split_output(out):
    """返回 (2D 输出, 是否特征在前, 置信度数组)。"""
    arr = out[0] if out.ndim == 3 else out
    feats_first = arr.shape[0] < arr.shape[1]
    conf = arr[4] if feats_first else arr[:, 4]
    return arr, feats_first, conf


def print_conf_stats(conf, thresholds):
    print(f"conf min/max: {float(conf.min()):.6f} / {float(conf.max()):.6f}")
    for thr in thresholds:
        print(f"  conf >= {thr:<5}: {int(np.sum(conf >= thr))}")

    order = np.argsort(conf)[::-1][:10]
    print("top confidences:")
    for rank, idx in enumerate(order, 1):
        print(f"  #{rank:<2} index={int(idx):<5} conf={float(conf[idx]):.6f}")


def print_top_dets(arr, feats_first, conf, k=5):
    order = np.argsort(conf)[::-1][:k]
    print(f"top {k} raw boxes (原图像素坐标):")
    for rank, idx in enumerate(order, 1):
        if feats_first:
            x, y, w, h, c, a = arr[:, idx]
        else:
            x, y, w, h, c, a = arr[idx, :]
        print(f"  #{rank} conf={float(c):.4f} xywhr="
              f"[{float(x):.2f}, {float(y):.2f}, {float(w):.2f}, {float(h):.2f}, {float(a):.4f}]")


def raw_onnx_check(detector, image, conf_thr, website_conf, thresholds):
    print()
    print("=" * 78)
    print("2. 原始 ONNX 检测（不经过 recognize 的正反面/卡名过滤）")
    print("=" * 78)
    t0 = time.perf_counter()
    tensor, scale, padx, pady = recognize.onnx_letterbox(
        cv2, np, image, detector.imgsz)
    infer_t = time.perf_counter() - t0
    print(f"image: {image.shape[1]}x{image.shape[0]}")
    print(f"letterbox: tensor={tensor.shape} dtype={tensor.dtype} "
          f"min={float(tensor.min()):.3f} max={float(tensor.max()):.3f}")
    print(f"scale={scale:.6f} padx={padx} pady={pady} "
          f"({infer_t * 1000:.1f}ms)")

    t0 = time.perf_counter()
    raw = detector.front_sess.run(
        [detector.front_oname], {detector.front_iname: tensor})[0]
    run_ms = (time.perf_counter() - t0) * 1000
    print(f"ONNX output: shape={raw.shape} dtype={raw.dtype} ({run_ms:.1f}ms)")

    arr, feats_first, conf = split_output(raw)
    print(f"layout: {'[6,N] 特征在前' if feats_first else '[N,6] 特征在后'}, "
          f"解析数组 shape={arr.shape}")
    print_conf_stats(conf, thresholds)
    print_top_dets(arr, feats_first, conf)

    raw_cfg = recognize.parse_onnx_obb(
        np, arr, scale, padx, pady, conf_thr, detector.nms_iou)
    raw_web = recognize.parse_onnx_obb(
        np, arr, scale, padx, pady, website_conf, detector.nms_iou)
    print(f"当前阈值 {conf_thr}: {len(raw_cfg)} 个框")
    print(f"draw2 网页阈值 {website_conf}: {len(raw_web)} 个框")
    if raw_cfg:
        print("检测框（当前阈值）:")
        for i, d in enumerate(raw_cfg, 1):
            print(f"  #{i} conf={d['conf']:.4f} xywhr="
                  f"[{float(d['xywhr'][0]):.1f}, {float(d['xywhr'][1]):.1f}, "
                  f"{float(d['xywhr'][2]):.1f}, {float(d['xywhr'][3]):.1f}, "
                  f"{float(d['xywhr'][4]):.4f}]")
    return raw_cfg


def classify_topk(detector, crop, k=5):
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    s = detector.crop_size
    im = rgb if (rgb.shape[0] == s and rgb.shape[1] == s) \
        else cv2.resize(rgb, (s, s), interpolation=cv2.INTER_CUBIC)
    x = ((im.astype(np.float32) / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)[None]
    logits = detector.sess.run(
        [detector.oname], {detector.iname: x})[0][0]
    e = np.exp(logits - logits.max())
    prob = e / e.sum()
    order = np.argsort(prob)[::-1][:k]
    out = []
    for idx in order:
        info = detector.names.get(str(int(idx))) or {}
        out.append({
            "idx": int(idx),
            "card_id": info.get("card_id"),
            "name": info.get("EN", ""),
            "score": float(prob[idx]),
        })
    return out


def crop_stats(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    h_ch, _s, v_ch = cv2.split(hsv)
    s = image.shape[0]
    cx0, cx1 = int(s * 0.25), int(s * 0.75)
    cy0, cy1 = int(s * 0.25), int(s * 0.75)
    center_v = v_ch[cy0:cy1, cx0:cx1]
    dark = float(np.sum(center_v < 60) / center_v.size) if center_v.size else 0.0
    mean_v = float(np.mean(center_v)) if center_v.size else 0.0
    h_var = float(np.var(h_ch))
    return {"dark": dark, "mean_v": mean_v, "h_var": h_var}


def analyze_check(detector, image, dets, name_thr, save_dir):
    print()
    print("=" * 78)
    print("3. 卡图裁切 + 卡名识别（逐框）")
    print("=" * 78)
    detector._frame = image
    reasons = []
    for i, d in enumerate(dets):
        conf = float(d["conf"])
        side, ori, crop = detector.analyze_card(d["corners"], d["xywhr"])
        print(f"\n#{i} conf={conf:.4f} -> analyze_card side={side!r} orientation={ori}")
        if crop is None:
            print("  crop=None（角点/透视变换失败）")
            reasons.append((i, conf, side, "crop 生成失败"))
            continue

        stats = crop_stats(crop)
        print(f"  HSV: dark={stats['dark']:.3f} "
              f"mean_v={stats['mean_v']:.1f} h_var={stats['h_var']:.1f}")
        print("  新逻辑: 先 ViT 识别卡名，成功即正面；"
              "失败后由卡背模型判断，命中且暗色才按反面，否则按卡面")

        top = classify_topk(detector, crop, 5)
        print("  卡名 top5（原方向，未套阈值）:")
        for rank, item in enumerate(top, 1):
            print(f"    {rank}. [{item['card_id']}] {item['name']} "
                  f"score={item['score']:.6f}")

        top180 = classify_topk(detector, cv2.rotate(crop, cv2.ROTATE_180), 3)
        print("  卡名 top3（旋转 180°）:")
        for rank, item in enumerate(top180, 1):
            print(f"    {rank}. [{item['card_id']}] {item['name']} "
                  f"score={item['score']:.6f}")

        crop_path = save_dir / f"nowyolotest_crop_{i}.jpg"
        imwrite(crop_path, crop)
        print(f"  crop -> {crop_path}")

        if top[0]["score"] >= name_thr:
            reason = (f"卡名可识别（{top[0]['score']:.4f} >= {name_thr}），"
                      "识别成功按正面")
        else:
            reason = (f"卡名低于阈值（{top[0]['score']:.4f} < {name_thr}）；"
                      "由卡背模型决定：命中且暗色才按反面，否则按卡面（无卡名）")
        reasons.append((i, conf, side, reason))
    return reasons


def draw_result(image, dets, detector, out_path):
    vis = image.copy()
    for i, d in enumerate(dets):
        pts = d["corners"].astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(vis, [pts], True, (0, 255, 0), 2)
        label = f"raw{i} {d['conf']:.2f}"
        cv2.putText(vis, label, (int(d["xywhr"][0]) - 40, int(d["xywhr"][1])),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1, cv2.LINE_AA)

        side, ori, _crop = detector.analyze_card(d["corners"], d["xywhr"])
        color = (0, 255, 0) if side == "正面" else \
            (255, 0, 0) if side == "反面" else (0, 165, 255)
        cv2.putText(vis, f"{side}/{ori}",
                    (int(d["xywhr"][0]) - 40, int(d["xywhr"][1]) + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

    imwrite(out_path, vis)
    print(f"标注图 -> {out_path}")


def main():
    parser = argparse.ArgumentParser(description="检查 test.jpg 为什么没有识别结果")
    parser.add_argument("--image", default=str(BASE_DIR / "test.jpg"),
                        help="待检查图片（默认 test/test.jpg）")
    parser.add_argument("--config", default="",
                        help="center config.json；默认 center/config/config.json")
    parser.add_argument("--conf", type=float, default=0.01,
                        help="诊断时使用的低阈值（默认 0.01）")
    parser.add_argument("--website-conf", type=float, default=0.2,
                        help="draw2 网页使用的阈值（默认 0.2）")
    parser.add_argument("--save-dir", default=str(BASE_DIR),
                        help="标注图/裁图输出目录（默认 test/）")
    args = parser.parse_args()

    image_path = Path(args.image).resolve()
    save_dir = Path(args.save_dir).resolve()
    save_dir.mkdir(parents=True, exist_ok=True)

    if args.config:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    else:
        cfg = center_config.load_config()

    models, detector = load_detector(cfg)

    print()
    print("=" * 78)
    print("图片")
    print("=" * 78)
    print(f"path: {image_path}")
    if not image_path.is_file():
        raise SystemExit(f"图片不存在: {image_path}")
    image = imread(image_path)
    if image is None:
        raise SystemExit(f"无法读取图片: {image_path}")
    print(f"shape: {image.shape} (H,W,C)")

    front_conf = float(cfg["detect"]["front_conf"])
    name_thr = float(cfg["detect"]["name_thr"])
    thresholds = [0.01, 0.05, 0.1, 0.2, 0.25, 0.5]

    dets = raw_onnx_check(
        detector, image, args.conf, args.website_conf, thresholds)

    reasons = analyze_check(detector, image, dets, name_thr, save_dir)

    print()
    print("=" * 78)
    print("4. Detector.detect() 最终结果")
    print("=" * 78)
    t0 = time.perf_counter()
    final = detector.detect(image)
    print(f"最终 detections = {len(final)}（耗时 {(time.perf_counter() - t0) * 1000:.1f}ms）")
    print(f"timing = {detector.timing}")
    for i, d in enumerate(final, 1):
        info = d.get("info")
        name = f"{info['name']} ({info['card_id']}) {info['score']:.3f}" if info else "未识别卡名"
        print(f"  #{i} side={d['side']} orientation={d['orientation']} "
              f"center=({d['cx']:.1f},{d['cy']:.1f}) {name}")

    print()
    print("=" * 78)
    print("5. 结论")
    print("=" * 78)
    print(f"配置 front_conf={front_conf}, name_thr={name_thr}, "
          f"draw2 网页阈值={args.website_conf}")
    print(f"原始 ONNX 检出（诊断阈值 {args.conf}）= {len(dets)}")
    print(f"Detector.detect() 最终结果 = {len(final)}")

    if dets and not final:
        print("\n原始正面 YOLO 能检出框，但后续阶段没有输出：")
        for i, conf, side, reason in reasons:
            print(f"  #{i} conf={conf:.4f} side={side!r}: {reason}")
        print("\n当前顺序：先 ViT 识别卡名，成功即正面；未识别时由卡背模型判断，"
              "命中且暗色才按反面，否则按卡面。正常不应再出现“检出但被丢弃”。")
    elif not dets:
        print("\n正面 ONNX 检测阶段就是 0：检查输入形状/颜色通道、输出 layout、"
              "模型文件和置信度阈值。")
    else:
        print("\n最终有结果，见上方详情。")
        if any(d["side"] == "back" for d in final):
            print("其中 back 表示 ViT 未识别出卡名，且卡背模型命中并确认是暗色区域。")

    if dets:
        draw_result(image, dets, detector, save_dir / "nowyolotest_annotated.jpg")


if __name__ == "__main__":
    main()
