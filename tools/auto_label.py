"""
用现有 cardcaptor 模型自动预标注。
把采集的图放到 cardback_dataset/images/raw/ 下，运行后
会在 cardback_dataset/labels/raw/ 生成 YOLO OBB 格式的 .txt。

预标注不完美，必须用 X-AnyLabeling 人工修正！
"""
from ultralytics import YOLO
import cv2
import os

# ---------------- 配置 ----------------
MODEL_PATH = "../src/models/cardcaptor_v3_best.pt"
IMG_DIR = "../cardback_dataset/images/raw"
LBL_DIR = "../cardback_dataset/labels/raw"
CONF = 0.3            # 预标注置信度，低一点宁可多框
CLASS_ID = 0          # cardback

os.makedirs(LBL_DIR, exist_ok=True)

print(f"加载模型 {MODEL_PATH} ...")
model = YOLO(MODEL_PATH)

exts = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
files = [f for f in os.listdir(IMG_DIR) if f.lower().endswith(exts)]
files.sort()
print(f"共 {len(files)} 张图待标注")

total_boxes = 0
for idx, fname in enumerate(files, 1):
    img_path = os.path.join(IMG_DIR, fname)
    img = cv2.imread(img_path)
    if img is None:
        print(f"[跳过] 读不到: {fname}")
        continue
    H, W = img.shape[:2]

    r = model.predict(img_path, conf=CONF, verbose=False)[0]

    lines = []
    if r.obb is not None and len(r.obb) > 0:
        pts = r.obb.xyxyxyxy.cpu().numpy()   # (N, 4, 2) 像素坐标
        for c in pts:
            norm = c.astype(float).copy()
            norm[:, 0] /= W
            norm[:, 1] /= H
            norm = norm.clip(0, 1)
            flat = norm.flatten()
            lines.append(f"{CLASS_ID} " +
                         " ".join(f"{v:.6f}" for v in flat))

    out_path = os.path.join(LBL_DIR,
                            os.path.splitext(fname)[0] + ".txt")
    with open(out_path, "w") as f:
        f.write("\n".join(lines))

    total_boxes += len(lines)
    print(f"[{idx}/{len(files)}] {fname}: {len(lines)} 框")

print(f"\n完成。共 {total_boxes} 个预标注框，存到 {LBL_DIR}")
print("下一步：用 X-AnyLabeling 打开 images/raw 和 labels/raw 人工修正")