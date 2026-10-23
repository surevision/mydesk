import argparse
import math
import cv2
import numpy as np
import onnxruntime as ort

INPUT_W, INPUT_H = 640, 384


def letterbox(img, w, h, color=114):
    ih, iw = img.shape[:2]
    r = min(w / iw, h / ih)
    nw, nh = int(round(iw * r)), int(round(ih * r))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((h, w, 3), color, np.uint8)
    dx, dy = (w - nw) // 2, (h - nh) // 2
    canvas[dy:dy + nh, dx:dx + nw] = resized
    return canvas, r, dx, dy


def rbox_to_aabb(pts):
    xs, ys = pts[:, 0], pts[:, 1]
    return [float(xs.min()), float(ys.min()), float(xs.max() - xs.min()), float(ys.max() - ys.min())]


def nms_rotated(boxes, scores, thr):
    order = np.argsort(scores)[::-1]
    keep = []
    aabbs = []
    for i in order:
        b = rbox_to_aabb(boxes[i])
        drop = False
        for j, kb in zip(keep, aabbs):
            xa1, ya1, wa, ha = b
            xb1, yb1, wb, hb = kb
            xa2, ya2 = xa1 + wa, ya1 + ha
            xb2, yb2 = xb1 + wb, yb1 + hb
            ix = max(0.0, min(xa2, xb2) - max(xa1, xb1))
            iy = max(0.0, min(ya2, yb2) - max(ya1, yb1))
            inter = ix * iy
            union = wa * ha + wb * hb - inter
            if union > 0 and inter / union > thr:
                drop = True
                break
        if not drop:
            keep.append(i)
            aabbs.append(b)
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True)
    ap.add_argument('--model', default=r'D:\Git\ygodesk\models\detector.onnx')
    ap.add_argument('--conf', type=float, default=0.25)
    ap.add_argument('--iou', type=float, default=0.45)
    ap.add_argument('--cls', default='1', help='0 / 1 / both')
    ap.add_argument('--angle-mode', default='sigmoid', choices=['sigmoid', 'raw'])
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    img = cv2.imdecode(np.fromfile(a.image, dtype=np.uint8), cv2.IMREAD_COLOR)
    lb, r, dx, dy = letterbox(img, INPUT_W, INPUT_H)
    x = lb[:, :, ::-1].astype(np.float32).transpose(2, 0, 1)[None] / 255.0

    s = ort.InferenceSession(a.model, providers=['CPUExecutionProvider'])
    out = s.run([s.get_outputs()[0].name], {s.get_inputs()[0].name: x})[0]
    pred = out[0] if out.ndim == 3 else out

    cls_cols = {'0': [4], '1': [5], 'both': [4, 5]}[a.cls]
    if len(cls_cols) == 1:
        score = pred[:, cls_cols[0]]
        cls_id = np.full(len(score), cls_cols[0] - 4)
    else:
        score = pred[:, cls_cols].max(axis=1)
        cls_id = pred[:, cls_cols].argmax(axis=1)

    raw_angle = pred[:, 6]
    ang = ((raw_angle - 0.25) * math.pi / 2) if a.angle_mode == 'sigmoid' else raw_angle

    keep = np.where(score >= a.conf)[0]
    boxes, scores, angles, cids = [], [], [], []
    ih, iw = img.shape[:2]
    for i in keep:
        cx = (pred[i, 0] - dx) / r
        cy = (pred[i, 1] - dy) / r
        bw = pred[i, 2] / r
        bh = pred[i, 3] / r
        rect = ((cx, cy), (bw, bh), math.degrees(ang[i]))
        pts = cv2.boxPoints(rect)
        boxes.append(pts)
        scores.append(float(score[i]))
        cids.append(int(cls_id[i]))
    keep2 = nms_rotated(boxes, np.array(scores), a.iou)
    order = sorted(keep2, key=lambda i: -scores[i])

    vis = img.copy()
    colors = {0: (0, 200, 255), 1: (0, 255, 0)}
    print(f'shape {out.shape} cls={a.cls} conf>={a.conf}: {len(order)} boxes after NMS '
          f'({int((score >= a.conf).sum())} before)')
    for n, i in enumerate(order):
        pts = boxes[i].astype(np.int32)
        col = colors.get(cids[i], (255, 0, 255))
        cv2.polylines(vis, [pts], True, col, 2)
        cx, cy = pts[:, 0].mean(), pts[:, 1].mean()
        label = f'{n+1}:{scores[i]:.2f}c{cids[i]}'
        cv2.putText(vis, label, (int(cx) - 20, int(cy)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)
        (_, _), (w, h), _ = cv2.minAreaRect(pts)
        print(f'  #{n+1} cls{cids[i]} {scores[i]:.3f} center=({cx:.0f},{cy:.0f}) '
              f'size={w:.0f}x{h:.0f} angle={math.degrees(ang[i]):.1f}')

    out_path = a.out or a.image.rsplit('.', 1)[0] + f'_obb_c{a.cls}_{a.conf}.png'
    cv2.imencode('.png', vis)[1].tofile(out_path)
    print('saved', out_path)


if __name__ == '__main__':
    main()
