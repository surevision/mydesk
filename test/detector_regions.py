import argparse
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
    ap.add_argument('--conf', type=float, default=0.1)
    ap.add_argument('--iou', type=float, default=0.45)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    img = cv2.imdecode(np.fromfile(a.image, dtype=np.uint8), cv2.IMREAD_COLOR)
    lb, r, dx, dy = letterbox(img, INPUT_W, INPUT_H)
    x = lb.astype(np.float32).transpose(2, 0, 1)[None]  # BGR, 0-255

    s = ort.InferenceSession(a.model, providers=['CPUExecutionProvider'])
    pred = s.run([s.get_outputs()[0].name], {s.get_inputs()[0].name: x})[0][0]

    conf = pred[:, 4]
    front = pred[:, 5]
    back = pred[:, 6]

    keep = np.where(conf >= a.conf)[0]
    boxes = pred[keep, :4].copy()
    scores = conf[keep]
    ks = nms(boxes, scores, a.iou)
    boxes, scores = boxes[ks], scores[ks]
    fronts, backs = front[keep][ks], back[keep][ks]
    order = np.argsort(scores)[::-1]
    boxes, scores, fronts, backs = boxes[order], scores[order], fronts[order], backs[order]

    vis = img.copy()
    print(f'conf>={a.conf}: {len(scores)} boxes after NMS ({int((conf >= a.conf).sum())} before)')
    nfront = nback = 0
    for i, (bx, sc) in enumerate(zip(boxes, scores)):
        cx = (bx[0] - dx) / r
        cy = (bx[1] - dy) / r
        bw = bx[2] / r
        bh = bx[3] / r
        x1, y1 = int(cx - bw / 2), int(cy - bh / 2)
        x2, y2 = int(cx + bw / 2), int(cy + bh / 2)
        is_back = backs[i] > fronts[i]
        if is_back:
            nback += 1
            col, tag = (0, 0, 255), 'B'
        else:
            nfront += 1
            col, tag = (0, 255, 0), 'F'
        print(f'  #{i+1} {tag} conf={sc:.3f} front={fronts[i]:.3f} back={backs[i]:.3f} '
              f'({x1},{y1},{x2},{y2}) {x2-x1}x{y2-y1}')
        cv2.rectangle(vis, (x1, y1), (x2, y2), col, 2)
        cv2.putText(vis, f'{tag}{i+1}:{sc:.2f}', (x1, max(10, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)
    print(f'front={nfront} back={nback}')

    out_path = a.out or a.image.rsplit('.', 1)[0] + f'_detector_{a.conf}.png'
    cv2.imencode('.png', vis)[1].tofile(out_path)
    print('saved', out_path)


if __name__ == '__main__':
    main()
