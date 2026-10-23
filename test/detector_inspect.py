import argparse, json
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


def nms(boxes, scores, thr):
    if len(boxes) == 0:
        return []
    xywh = boxes.copy()
    xywh[:, 0] -= xywh[:, 2] / 2
    xywh[:, 1] -= xywh[:, 3] / 2
    idx = cv2.dnn.NMSBoxes(xywh.tolist(), scores.tolist(), 0.0, thr)
    return list(np.array(idx).reshape(-1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True)
    ap.add_argument('--model', default=r'D:\Git\ygodesk\models\detector.onnx')
    ap.add_argument('--conf', type=float, default=0.25)
    ap.add_argument('--iou', type=float, default=0.45)
    ap.add_argument('--col', default='6', help='4/5/6, 4*5, 4*6, 4*5*6, max, or maxcls')
    ap.add_argument('--prep', default='rgb255', choices=['rgb255', 'bgr255', 'rgbraw', 'bgrraw'])
    ap.add_argument('--stretch', action='store_true', help='stretch instead of letterbox')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    img = cv2.imdecode(np.fromfile(a.image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if a.stretch:
        canvas = cv2.resize(img, (INPUT_W, INPUT_H))
        r, dx, dy = INPUT_W / img.shape[1], 0, 0
    else:
        canvas, r, dx, dy = letterbox(img, INPUT_W, INPUT_H)
    arr = canvas[:, :, ::-1] if a.prep.startswith('rgb') else canvas
    arr = arr.astype(np.float32)
    if a.prep.endswith('255'):
        arr /= 255.0
    x = arr.transpose(2, 0, 1)[None]

    s = ort.InferenceSession(a.model, providers=['CPUExecutionProvider'])
    out = s.run([s.get_outputs()[0].name], {s.get_inputs()[0].name: x})[0]
    pred = out[0] if out.ndim == 3 else out
    print('output', out.shape, 'anchors', pred.shape[0], 'feat', pred.shape[1])

    c4, c5, c6 = pred[:, 4], pred[:, 5], pred[:, 6]
    print(f'col4 [{c4.min():.3f},{c4.max():.3f}] m={c4.mean():.4f}')
    print(f'col5 [{c5.min():.3f},{c5.max():.3f}] m={c5.mean():.4f}')
    print(f'col6 [{c6.min():.3f},{c6.max():.3f}] m={c6.mean():.4f}')
    for name, sc in (('4', c4), ('5', c5), ('6', c6), ('5*6', c5 * c6),
                     ('max', np.max(pred[:, 4:7], axis=1))):
        print(f'  cand {name}: >0.25={int((sc > 0.25).sum())} >0.05={int((sc > 0.05).sum())}')

    if a.col == 'max':
        score = np.max(pred[:, 4:7], axis=1)
    elif a.col == 'maxcls':
        score = np.max(pred[:, 5:7], axis=1)
    elif '*' in a.col:
        score = np.ones(len(pred))
        for c in a.col.split('*'):
            score *= pred[:, int(c)]
    else:
        score = pred[:, int(a.col)]

    keep = np.where(score >= a.conf)[0]
    boxes = pred[keep, :4].copy()
    scores = score[keep]
    ks = nms(boxes, scores, a.iou)
    boxes, scores = boxes[ks], scores[ks]
    order = np.argsort(scores)[::-1]
    boxes, scores = boxes[order], scores[order]

    ih, iw = img.shape[:2]
    vis = img.copy()
    print(f'col={a.col} conf>={a.conf}: {len(scores)} boxes after NMS '
          f'({int((score >= a.conf).sum())} before)')
    for i, (bx, sc) in enumerate(zip(boxes, scores)):
        cx = (bx[0] - dx) / r
        cy = (bx[1] - dy) / r
        bw = bx[2] / r
        bh = bx[3] / r
        x1, y1 = int(cx - bw / 2), int(cy - bh / 2)
        x2, y2 = int(cx + bw / 2), int(cy + bh / 2)
        print(f'  #{i+1} {sc:.3f} ({x1},{y1},{x2},{y2}) size {x2-x1}x{y2-y1}')
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(vis, f'{i+1}:{sc:.2f}', (x1, max(0, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)

    out_path = a.out or a.image.rsplit('.', 1)[0] + f'_detector_c{a.col.replace("*","x")}_{a.conf}.png'
    cv2.imencode('.png', vis)[1].tofile(out_path)
    print('saved', out_path)


if __name__ == '__main__':
    main()
