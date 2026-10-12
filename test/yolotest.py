from ultralytics import YOLO
import cv2
import numpy as np
import json
import onnxruntime as ort
import time
import os


# ============================================================
# ONNX 卡名识别器（只用于正面卡）
# ============================================================
ONNX = "../src/models/vit_fp32.onnx"
NAMES = "../src/models/cardnames_onnx.json"

print("加载 ONNX 卡名识别模型...")
sess = ort.InferenceSession(ONNX, providers=["CPUExecutionProvider"])
iname = sess.get_inputs()[0].name
oname = sess.get_outputs()[0].name
names = json.load(open(NAMES, encoding="utf-8"))
print(f"卡名库：{len(names)} 张")


def card_name(card_bgr, thr=0.01, topk=5):
    """
    对一张已裁好、正立的卡图做卡名识别
    card_bgr: (H, W, 3) BGR 图像
    返回 dict 或 None（低于置信度阈值时返回 None）
    """
    if card_bgr is None or card_bgr.size == 0:
        return None

    # 模型训练用的是 RGB，输入必须转 RGB
    card_rgb = cv2.cvtColor(card_bgr, cv2.COLOR_BGR2RGB)

    im = cv2.resize(card_rgb, (224, 224), interpolation=cv2.INTER_CUBIC)
    # [-1, 1] 归一化（已通过对比实验验证）
    x = ((im.astype(np.float32) / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)[None]

    logits = sess.run([oname], {iname: x})[0][0]
    e = np.exp(logits - logits.max())
    prob = e / e.sum()
    idx = np.argsort(-prob)[:topk]

    if prob[idx[0]] < thr:
        return None

    info = names[str(idx[0])]
    return {
        "card_id": info["card_id"],
        "name": info["EN"],
        "names": info,
        "score": float(prob[idx[0]]),
        "topk": [{"card_id": names[str(i)]["card_id"],
                  "score": float(prob[i])} for i in idx],
    }


# ============================================================
# 通用：透视矫正 + 判定正反面
# ============================================================
def _dist(a, b):
    return float(np.linalg.norm(a - b))


def analyze_card(corners, xywhr, img, debug=False):
    """
    对 OBB 框做透视矫正，返回：
      - side: '正面' / '反面' / None
      - orientation: '横向' / '纵向'
      - crop: 透视矫正后的卡图

    corners: (4,2) OBB 四角坐标
    xywhr:   (5,)  OBB 的 x, y, w, h, r
             —— 用 w/h 判断横竖（不受旋转影响，最可靠）
    """
    pts = corners.astype(np.float32)

    # ---------- 用 xywhr 的真实 w/h 判断朝向 ----------
    w_real = float(xywhr[2])
    h_real = float(xywhr[3])

    if w_real < 30 or h_real < 30:
        return None, "未知", None

    if w_real > h_real:
        orientation = "横向"
        W = int(round(h_real))   # 转正后宽 = 原短边
        H = int(round(w_real))
    else:
        orientation = "纵向"
        W = int(round(w_real))
        H = int(round(h_real))

    # ---------- 角点重排 ----------
    # xyxyxyxy 不保证是 TL→TR→BR→BL，按 y 分上下两组，各按 x 排序
    pts_sorted = pts[np.argsort(pts[:, 1])]
    top2 = pts_sorted[:2]
    bot2 = pts_sorted[2:]
    top2 = top2[np.argsort(top2[:, 0])]   # 左上、右上
    bot2 = bot2[np.argsort(bot2[:, 0])]   # 左下、右下

    ordered = np.array([top2[0], top2[1], bot2[1], bot2[0]],
                       dtype=np.float32)

    # ---------- 透视变换 ----------
    dst = np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]],
                   dtype=np.float32)
    M = cv2.getPerspectiveTransform(ordered, dst)
    crop = cv2.warpPerspective(img, M, (W, H))

    # ---------- 正反面判定 ----------
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h_ch, s_ch, v_ch = cv2.split(hsv)

    cx_min, cx_max = int(W * 0.25), int(W * 0.75)
    cy_min, cy_max = int(H * 0.25), int(H * 0.75)
    center_v = v_ch[cy_min:cy_max, cx_min:cx_max]
    center_dark_ratio = (np.sum(center_v < 60) / center_v.size
                         if center_v.size > 0 else 0)
    center_mean_v = np.mean(center_v) if center_v.size > 0 else 0
    h_var = np.var(h_ch)

    if debug:
        print(f"  [debug] W={W} H={H} orient={orientation} "
              f"dark_ratio={center_dark_ratio:.3f} "
              f"mean_v={center_mean_v:.1f} h_var={h_var:.1f}")

    # 卡背：中心大片暗色
    if center_dark_ratio > 0.6 and center_mean_v < 80:
        return "反面", orientation, crop
    # 卡面：色相方差大（彩色卡图）
    elif h_var > 500:
        return "正面", orientation, crop

    return None, orientation, crop


# ============================================================
# 主流程
# ============================================================
# ========== 1. 加载模型（只加载一次）==========
print("\n加载 DRAW2 (ygo_yolo)...")
model_draw = YOLO("../src/models/ygo_yolo.pt")
print("加载 cardcaptor...")
model_cap = YOLO("../src/models/cardcaptor_v3_best.pt")

# ========== 2. 图片列表 ==========
images = [
    "image.png",
    "imadfge (2).png",
    "imadfge.png",
    "imagfe.png",
]

# ========== 3. 循环识别 ==========
for img_path in images:
    if not os.path.exists(img_path):
        print(f"[跳过] 文件不存在: {img_path}")
        continue

    print(f"\n{'=' * 60}")
    print(f"处理: {img_path}")
    print('=' * 60)

    # ---------- DRAW2 推理（用于正面卡）----------
    t0 = time.time()
    r_draw = model_draw.predict(img_path, conf=0.1, verbose=False)[0]
    t_draw = time.time() - t0

    img = r_draw.orig_img.copy()

    draw_data = []
    if r_draw.obb is not None and len(r_draw.obb) > 0:
        pts = r_draw.obb.xyxyxyxy.cpu().numpy()
        xywhr = r_draw.obb.xywhr.cpu().numpy()
        for i, (c, b) in enumerate(zip(pts, xywhr)):
            draw_data.append({
                'corners': c.copy(),
                'xywhr': b.copy(),
                'center': (int(b[0]), int(b[1])),
                'index': i + 1,
            })

    # ---------- cardcaptor 推理（用于背面卡）----------
    t0 = time.time()
    r_cap = model_cap.predict(img_path, conf=0.5, verbose=False)[0]
    t_cap = time.time() - t0

    cap_data = []
    if r_cap.obb is not None and len(r_cap.obb) > 0:
        pts = r_cap.obb.xyxyxyxy.cpu().numpy()
        xywhr = r_cap.obb.xywhr.cpu().numpy()
        for i, (c, b) in enumerate(zip(pts, xywhr)):
            cap_data.append({
                'corners': c.copy(),
                'xywhr': b.copy(),
                'center': (int(b[0]), int(b[1])),
                'index': i + 1,
            })

    # ---------- 判定 ----------
    front_cards = []
    back_cards = []

    # 正面卡（来自 DRAW2）：先判定，再识别卡名
    for d in draw_data:
        side, orientation, crop = analyze_card(d['corners'], d['xywhr'], img)
        if side == "正面":
            t0 = time.time()
            info = card_name(crop, thr=0.4)
            t_name = time.time() - t0

            card_info = {
                'corners': d['corners'],
                'center': d['center'],
                'orientation': orientation,
                'crop': crop,
                'name_result': info,
                'infer_time': t_name,
            }
            front_cards.append(card_info)

    # 背面卡（来自 cardcaptor）
    for d in cap_data:
        side, orientation, crop = analyze_card(d['corners'], d['xywhr'], img)
        if side == "反面":
            dup = any(abs(f['center'][0] - d['center'][0]) < 30 and
                      abs(f['center'][1] - d['center'][1]) < 30
                      for f in front_cards)
            if not dup:
                back_cards.append({
                    'corners': d['corners'],
                    'center': d['center'],
                    'orientation': orientation,
                })

    # ---------- 绘制 ----------
    # 所有框细线
    for d in draw_data:
        corners = d['corners'].astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(img, [corners], True, (0, 0, 255), 2)
    for d in cap_data:
        corners = d['corners'].astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(img, [corners], True, (255, 0, 255), 2)

    # 正面：绿粗线 + 卡名
    for c in front_cards:
        corners = c['corners'].astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(img, [corners], True, (0, 255, 0), 4)

        info = c['name_result']
        if info is None:
            label = f"正面/{c['orientation']} unknown"
        else:
            name = info['name']
            if len(name) > 30:
                name = name[:27] + "..."
            label = f"正面/{c['orientation']} {name} ({info['score']:.2f})"

        cv2.putText(img, label, (c['center'][0] - 60, c['center'][1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

    # 反面：蓝粗线
    for c in back_cards:
        corners = c['corners'].astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(img, [corners], True, (255, 0, 0), 4)
        cv2.putText(img, f"反面/{c['orientation']}",
                    (c['center'][0] - 50, c['center'][1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

    # ---------- 保存结果 ----------
    base = os.path.splitext(os.path.basename(img_path))[0]
    out_path = f"{base}_result.png"
    cv2.imwrite(out_path, img)

    # ---------- 终端输出 ----------
    print(f"DRAW2 耗时: {t_draw:.3f}s（{len(draw_data)} 框 → 正面 {len(front_cards)}）")
    print(f"cardcaptor 耗时: {t_cap:.3f}s（{len(cap_data)} 框 → 反面 {len(back_cards)}）")
    print(f"总耗时: {t_draw + t_cap:.3f}s")
    print(f"结果已保存: {out_path}")

    if front_cards:
        print("\n识别到的正面卡：")
        for i, c in enumerate(front_cards):
            info = c['name_result']
            if info is None:
                print(f"  正面 {i+1} ({c['center']}): unknown")
            else:
                print(f"  正面 {i+1} ({c['center']}): "
                      f"[{info['card_id']}] {info['name']} "
                      f"(score={info['score']:.3f}, 识别耗时 {c['infer_time']*1000:.1f}ms)")

print("\n全部处理完成")