"""
训练 cardback YOLOv8-OBB 模型。
4060 Ti (8GB) 推荐配置。
"""
from ultralytics import YOLO
import torch

# ---------------- 检查环境 ----------------
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"显存: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

# ---------------- 加载预训练 OBB 模型 ----------------
# n = nano 最快，s = small 更准。4060 Ti 建议先用 n，效果不够再换 s
model = YOLO("yolov8n-obb.pt")
# model = YOLO("yolov8s-obb.pt")   # 想要更准就换这行

# ---------------- 训练 ----------------
results = model.train(
    data="../cardback_dataset/data.yaml",
    epochs=150,
    imgsz=640,
    batch=16,             # 4060 Ti 8GB 用 16 稳；若 OOM 降到 8
    workers=4,
    device=0,
    project="../runs/obb",
    name="cardback_v1",
    patience=30,          # 30 epoch 无提升早停
    save=True,
    plots=True,
    val=True,
    # ---- 数据增广（卡背场景针对性配置）----
    degrees=180.0,        # 任意旋转（卡背会转）
    translate=0.1,
    scale=0.5,
    shear=2.0,
    perspective=0.0005,   # 轻微透视（手机拍卡有角度）
    flipud=0.0,           # 卡背上下有区别 → 不上下翻
    fliplr=0.5,
    mosaic=1.0,
    mixup=0.0,            # mixup 对小数据集不友好
    hsv_h=0.015,
    hsv_s=0.7,
    hsv_v=0.4,
    # ---- 优化器 ----
    optimizer="auto",
    lr0=0.01,
    lrf=0.01,
    momentum=0.937,
    weight_decay=0.0005,
    warmup_epochs=3.0,
    cos_lr=True,
)

print("\n训练完成")
print(f"最佳权重: runs/obb/cardback_v1/weights/best.pt")