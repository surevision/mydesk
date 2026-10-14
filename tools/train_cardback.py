from ultralytics import YOLO
import torch


def main():
    # ---------------- 检查环境 ----------------
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"显存: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

    # ---------------- 加载预训练 OBB 模型 ----------------
    model = YOLO("yolov8n-obb.pt")

    # ---------------- 训练 ----------------
    results = model.train(
        data="../cardback_dataset/data.yaml",
        epochs=150,
        imgsz=640,
        batch=16,
        workers=4,
        device=0,
        project="D:/git/ygodesk/runs/obb",   # 绝对路径，避免 runs/runs 嵌套
        name="cardback_v1",
        patience=30,
        save=True,
        plots=True,
        val=True,
        degrees=180.0,
        translate=0.1,
        scale=0.5,
        shear=2.0,
        perspective=0.0005,
        flipud=0.0,
        fliplr=0.5,
        mosaic=1.0,
        mixup=0.0,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        optimizer="auto",
        lr0=0.01,
        lrf=0.01,
        momentum=0.937,
        weight_decay=0.0005,
        warmup_epochs=3.0,
        cos_lr=True,
    )

    print("\n训练完成")
    print(f"最佳权重: {results.save_dir}/weights/best.pt")


if __name__ == "__main__":
    main()