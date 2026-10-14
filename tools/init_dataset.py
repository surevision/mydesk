"""
初始化 cardback_dataset 目录结构，并生成 data.yaml、classes.txt。

用法：
    cd tools
    python init_dataset.py

运行后会在项目根创建：
    cardback_dataset/
    ├── data.yaml          # YOLO 配置，path 为绝对路径
    ├── classes.txt        # 类别名
    ├── images/
    │   ├── raw/
    │   ├── train/
    │   └── val/
    └── labels/
        ├── raw/
        ├── train/
        └── val/

已存在的文件不会被覆盖。
"""
import os
from pathlib import Path


# ---------------- 配置 ----------------
# 数据集根目录：脚本所在目录的上一级 / cardback_dataset
DATASET_ROOT = Path(__file__).resolve().parent.parent / "cardback_dataset"

# 需要创建的目录（相对 DATASET_ROOT）
DIRS = [
    "images/raw",
    "images/train",
    "images/val",
    "labels/raw",
    "labels/train",
    "labels/val",
]

# 类别名（每行一个）
CLASSES = ["cardback"]


def main():
    root = DATASET_ROOT
    print(f"数据集根目录: {root}")

    # ---------- 1. 创建目录 ----------
    root.mkdir(parents=True, exist_ok=True)
    for d in DIRS:
        p = root / d
        p.mkdir(parents=True, exist_ok=True)
        print(f"  [目录] {p}")

    # ---------- 2. 生成 classes.txt ----------
    classes_path = root / "classes.txt"
    if not classes_path.exists():
        classes_path.write_text(
            "\n".join(CLASSES) + "\n",
            encoding="utf-8",
        )
        print(f"  [文件] {classes_path} (已创建)")
    else:
        print(f"  [文件] {classes_path} (已存在，跳过)")

    # ---------- 3. 生成 data.yaml（path 用绝对路径）----------
    yaml_path = root / "data.yaml"
    if not yaml_path.exists():
        # Windows 反斜杠改成正斜杠，避免 YAML 转义问题
        # Linux / macOS 本来就是正斜杠，不变
        root_posix = root.as_posix()

        yaml_content = (
            f"path: {root_posix}\n"
            f"train: images/train\n"
            f"val: images/val\n"
            f"\n"
            f"names:\n"
        )
        for i, name in enumerate(CLASSES):
            yaml_content += f"  {i}: {name}\n"

        yaml_path.write_text(yaml_content, encoding="utf-8")
        print(f"  [文件] {yaml_path} (已创建)")
        print(f"         path = {root_posix}")
    else:
        print(f"  [文件] {yaml_path} (已存在，跳过)")

    # ---------- 4. 完成提示 ----------
    print("\n初始化完成。")
    print("\n目录结构：")
    print(f"  {root}")
    print(f"  ├── data.yaml")
    print(f"  ├── classes.txt")
    print(f"  ├── images/")
    for d in ("raw", "train", "val"):
        print(f"  │   ├── {d}/")
    print(f"  └── labels/")
    for d in ("raw", "train", "val"):
        print(f"      ├── {d}/")

    print("\n下一步：")
    print(f"  1. 把图片放到 {root / 'images' / 'raw'}")
    print(f"  2. 把标签放到 {root / 'labels' / 'raw'}")
    print(f"  3. python auto_label.py        # 自动预标注（可选）")
    print(f"  4. python split_dataset.py     # 划分 train / val")
    print(f"  5. python train_cardback.py    # 训练")


if __name__ == "__main__":
    main()