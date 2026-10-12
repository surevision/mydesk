"""
把 raw 里的图和标签按比例随机划分到 train/val。
"""
import os
import shutil
import random

# ---------------- 配置 ----------------
ROOT = "../cardback_dataset"
RAW_IMG = os.path.join(ROOT, "images/raw")
RAW_LBL = os.path.join(ROOT, "labels/raw")
TRAIN_IMG = os.path.join(ROOT, "images/train")
VAL_IMG = os.path.join(ROOT, "images/val")
TRAIN_LBL = os.path.join(ROOT, "labels/train")
VAL_LBL = os.path.join(ROOT, "labels/val")

VAL_RATIO = 0.2
SEED = 42

# ---------------- 清理 + 创建 ----------------
for d in (TRAIN_IMG, VAL_IMG, TRAIN_LBL, VAL_LBL):
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d, exist_ok=True)

# ---------------- 收集 ----------------
exts = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
files = [f for f in os.listdir(RAW_IMG) if f.lower().endswith(exts)]
files.sort()

random.seed(SEED)
random.shuffle(files)

n_val = int(len(files) * VAL_RATIO)
val_files = files[:n_val]
train_files = files[n_val:]

def copy_pair(fname, img_dst, lbl_dst):
    src_img = os.path.join(RAW_IMG, fname)
    base = os.path.splitext(fname)[0]
    src_lbl = os.path.join(RAW_LBL, base + ".txt")

    shutil.copy2(src_img, os.path.join(img_dst, fname))
    if os.path.exists(src_lbl):
        shutil.copy2(src_lbl, os.path.join(lbl_dst, base + ".txt"))
    else:
        # 负样本（纯卡面 / 空白桌面），建空 txt
        open(os.path.join(lbl_dst, base + ".txt"), "w").close()

for f in train_files:
    copy_pair(f, TRAIN_IMG, TRAIN_LBL)
for f in val_files:
    copy_pair(f, VAL_IMG, VAL_LBL)

print(f"train: {len(train_files)} 张")
print(f"val:   {len(val_files)} 张")
print("划分完成")