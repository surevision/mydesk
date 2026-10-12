"""
训练完成后，在 val 集上评估模型。
"""
from ultralytics import YOLO

MODEL = "../runs/obb/cardback_v1/weights/best.pt"
DATA = "../cardback_dataset/data.yaml"

model = YOLO(MODEL)
metrics = model.val(data=DATA, imgsz=640, device=0, plots=True)

print(f"\nmAP50:    {metrics.box.map50:.4f}")
print(f"mAP50-95: {metrics.box.map:.4f}")
print(f"\n预测示例图: runs/obb/cardback_v1/val_batch0_pred.jpg")