from ultralytics import YOLO
import cv2
import numpy as np
import json
import onnxruntime as ort
import time


# ============================================================
# 手机摄像头 IP（改成你手机上 IP Webcam 显示的地址）
# ============================================================
PHONE_IP = "10.10.1.105"     # ← 改成你的手机 IP
PHONE_PORT = 8080             # IP Webcam 默认 8080
PHONE_URL = f"http://{PHONE_IP}:{PHONE_PORT}/video"

# 显示窗口初始大小
WIN_NAME = "YGO Real-time (Phone)"
WIN_W, WIN_H = 640, 480


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


def card_name(card_bgr, thr=0.1, topk=5):
    """对一张已裁好、正立的卡图做卡名识别"""
    if card_bgr is None or card_bgr.size == 0:
        return None

    card_rgb = cv2.cvtColor(card_bgr, cv2.COLOR_BGR2RGB)
    im = cv2.resize(card_rgb, (224, 224), interpolation=cv2.INTER_CUBIC)
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
    """对 OBB 框做透视矫正，返回 side / orientation / crop"""
    pts = corners.astype(np.float32)

    w_real = float(xywhr[2])
    h_real = float(xywhr[3])

    if w_real < 30 or h_real < 30:
        return None, "未知", None

    if w_real > h_real:
        orientation = "横向"
        W = int(round(h_real))
        H = int(round(w_real))
    else:
        orientation = "纵向"
        W = int(round(w_real))
        H = int(round(h_real))

    pts_sorted = pts[np.argsort(pts[:, 1])]
    top2 = pts_sorted[:2]
    bot2 = pts_sorted[2:]
    top2 = top2[np.argsort(top2[:, 0])]
    bot2 = bot2[np.argsort(bot2[:, 0])]
    ordered = np.array([top2[0], top2[1], bot2[1], bot2[0]],
                       dtype=np.float32)

    dst = np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]],
                   dtype=np.float32)
    M = cv2.getPerspectiveTransform(ordered, dst)
    crop = cv2.warpPerspective(img, M, (W, H))

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

    if center_dark_ratio > 0.6 and center_mean_v < 80:
        return "反面", orientation, crop
    elif h_var > 500:
        return "正面", orientation, crop

    return None, orientation, crop


# ============================================================
# 主流程
# ============================================================
print("\n加载 DRAW2 (ygo_yolo)...")
model_draw = YOLO("../src/models/ygo_yolo.pt")
print("加载 cardcaptor...")
model_cap = YOLO("../src/models/cardback_best.pt")

# ---------- 打开手机摄像头流 ----------
print(f"\n连接视频源: {PHONE_URL}")
cap = cv2.VideoCapture(PHONE_URL)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not cap.isOpened():
    print(f"[错误] 无法连接 {PHONE_URL}")
    print("排查：")
    print("  1. 手机和电脑是否连同一 WiFi？")
    print(f"  2. 浏览器打开 http://{PHONE_IP}:{PHONE_PORT} 能否看到画面？")
    print("  3. 手机 IP Webcam 是否已 Start server？")
    print("  4. 手机 IP 有没有变？在 App 里或路由器后台确认")
    print("  5. 电脑防火墙是否拦了出站？")
    exit(1)

print("已连接，按 Q 或 ESC 退出\n")

# ---------- 创建可缩放窗口，初始 640×480 ----------
cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WIN_NAME, WIN_W, WIN_H)

# ---------- 卡名缓存 ----------
card_name_cache = {}   # tid -> info dict or None
tid_last_seen = {}     # tid -> timestamp
CACHE_TTL = 3.0

# ---------- 主循环 ----------
frame_idx = 0
reconnect_count = 0

while True:
    ok, frame = cap.read()
    if not ok:
        reconnect_count += 1
        print(f"[警告] 读帧失败，尝试重连 ({reconnect_count})...")
        cap.release()
        time.sleep(0.5)
        cap = cv2.VideoCapture(PHONE_URL)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if reconnect_count > 5:
            print("[错误] 连续重连失败，退出")
            break
        continue
    reconnect_count = 0

    frame_idx += 1
    t_frame_start = time.time()

    # 两个模型吃同一帧
    r_draw = model_draw.predict(frame, conf=0.1, verbose=False)[0]
    r_cap = model_cap.predict(frame, conf=0.5, verbose=False)[0]

    img = frame.copy()

    # ---------- 收集 OBB 数据 ----------
    draw_data = []
    if r_draw.obb is not None and len(r_draw.obb) > 0:
        pts = r_draw.obb.xyxyxyxy.cpu().numpy()
        xywhr = r_draw.obb.xywhr.cpu().numpy()
        ids = (r_draw.obb.id.cpu().numpy().astype(int)
               if r_draw.obb.id is not None else np.arange(len(pts)))
        for i, (c, b, tid) in enumerate(zip(pts, xywhr, ids)):
            draw_data.append({
                'corners': c.copy(),
                'xywhr': b.copy(),
                'center': (int(b[0]), int(b[1])),
                'index': i + 1,
                'tid': int(tid),
            })

    cap_data = []
    if r_cap.obb is not None and len(r_cap.obb) > 0:
        pts = r_cap.obb.xyxyxyxy.cpu().numpy()
        xywhr = r_cap.obb.xywhr.cpu().numpy()
        ids = (r_cap.obb.id.cpu().numpy().astype(int)
               if r_cap.obb.id is not None else np.arange(len(pts)) + 10000)
        for i, (c, b, tid) in enumerate(zip(pts, xywhr, ids)):
            cap_data.append({
                'corners': c.copy(),
                'xywhr': b.copy(),
                'center': (int(b[0]), int(b[1])),
                'index': i + 1,
                'tid': int(tid),
            })

    # ---------- 判定 + 卡名识别 ----------
    front_cards = []
    back_cards = []
    now = time.time()

    for d in draw_data:
        side, orientation, crop = analyze_card(d['corners'], d['xywhr'], img)
        if side != "正面":
            continue

        tid = d['tid']
        tid_last_seen[tid] = now

        if tid in card_name_cache:
            info = card_name_cache[tid]
        else:
            info = card_name(crop, thr=0.1)
            card_name_cache[tid] = info

        front_cards.append({
            'corners': d['corners'],
            'center': d['center'],
            'orientation': orientation,
            'crop': crop,
            'name_result': info,
            'tid': tid,
        })

    for d in cap_data:
        side, orientation, crop = analyze_card(d['corners'], d['xywhr'], img)
        if side != "反面":
            continue
        dup = any(abs(f['center'][0] - d['center'][0]) < 30 and
                  abs(f['center'][1] - d['center'][1]) < 30
                  for f in front_cards)
        if not dup:
            back_cards.append({
                'corners': d['corners'],
                'center': d['center'],
                'orientation': orientation,
                'tid': d['tid'],
            })
            tid_last_seen[d['tid']] = now

    # 清理过期缓存
    expired = [tid for tid, t in tid_last_seen.items()
               if now - t > CACHE_TTL]
    for tid in expired:
        tid_last_seen.pop(tid, None)
        card_name_cache.pop(tid, None)

    # ---------- 绘制（画在原始 img 上）----------
    for d in draw_data:
        corners = d['corners'].astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(img, [corners], True, (0, 0, 255), 2)
    for d in cap_data:
        corners = d['corners'].astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(img, [corners], True, (255, 0, 255), 2)

    for c in front_cards:
        corners = c['corners'].astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(img, [corners], True, (0, 255, 0), 3)

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

    for c in back_cards:
        corners = c['corners'].astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(img, [corners], True, (255, 0, 0), 3)
        cv2.putText(img, f"反面/{c['orientation']}",
                    (c['center'][0] - 50, c['center'][1]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

    # ---------- FPS ----------
    fps = 1.0 / max(time.time() - t_frame_start, 1e-6)
    cv2.putText(img, f"FPS: {fps:.1f}  frame: {frame_idx}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

    # ---------- 等比缩放到 640 宽再显示 ----------
    h, w = img.shape[:2]
    if w > WIN_W:
        scale = WIN_W / w
        show_img = cv2.resize(img, (WIN_W, int(h * scale)),
                              interpolation=cv2.INTER_AREA)
    else:
        show_img = img

    cv2.imshow(WIN_NAME, show_img)
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q') or key == 27:
        break

cap.release()
cv2.destroyAllWindows()
print("\n已退出")