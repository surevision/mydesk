import sys
import cv2
import numpy as np

sys.path.insert(0, r'D:\Git\ygodesk\center')
from config import load_config
from recognize import Models

cfg = load_config()
models = Models(cfg)
if not models.load():
    print('models.load failed:', models.reason)
    raise SystemExit(1)

det = models.make_detector(cfg.get('dual', {}).get('cameras', [{}])[0].get('orientation', 'horizontal')
                           if cfg.get('mode') == 'dual' else 'horizontal')
if not det.ready:
    print('detector not ready:', det.error)
    raise SystemExit(1)
print('front_onnx', det.front_onnx, 'back_onnx', det.back_onnx, 'back size', det.back_w, det.back_h)

img_path = sys.argv[1] if len(sys.argv) > 1 else r'D:\Git\ygodesk\test\t1.png'
img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
dets = det.detect(img)
print('detections', len(dets), 'timing', {k: (round(v, 3) if isinstance(v, float) else v)
                                          for k, v in det.timing.items()})
for d in sorted(dets, key=lambda x: -x['xywhr'][3]):
    x, y, w, h, a = d['xywhr']
    info = d['info']
    print(f"  {d['side']:5s} {d['source']:9s} conf-w={w:6.1f} h={h:6.1f} "
          f"center=({x:6.1f},{y:6.1f}) name={info['name'] if info else '-'}")
