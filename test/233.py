# -*- coding: utf-8 -*-
"""
regiontest.py
识别 single（单摄像头）画面里左右两名玩家的完整区域。

流程：
    1. 读图
    2. 弹窗让用户分别框选"左玩家区"和"右玩家区"
    3. 在每个矩形里找"二维码角块"样式的定位方块
    4. 4 个定位方块的外包围矩形 = 玩家区域

用法：
    python regiontest.py [图片...]
"""

import os
import sys
import time

import cv2
import numpy as np

IMAGES = [r"dm5.jpg"]
MAX_SIDE = 1920

# ============================================================
# 方块检测参数
# ============================================================
WHITE_MIN_V = 120        # HSV 亮度下限
WHITE_MAX_S = 140        # HSV 饱和度上限

SIDE_MIN = 30            # 方块边长下限
SIDE_MAX = 120           # 方块边长上限

SQUARE_MIN = 0.70        # 宽高比下限
SQUARE_MAX = 1.40        # 宽高比上限

# 白占比：二维码角块约 0.55~0.75，空心框只有 0.05~0.15
WHITE_RATIO_MIN = 0.40
WHITE_RATIO_MAX = 0.90

# 黑占比：二维码角块有黑心
BLACK_RATIO_MIN = 0.03

PER_SIDE = 4             # 每侧方块数


# ============================================================
# 图像读取
# ============================================================

def load_image(path, max_side=MAX_SIDE):
    """读图，处理 EXIF 方向，缩放到合理尺寸。"""
    img = cv2.imread(path)
    if img is None:
        return None
    try:
        from PIL import Image
        pil = Image.open(path)
        exif = pil.getexif()
        orientation = exif.get(274, 1)
        if orientation == 3:
            img = cv2.rotate(img, cv2.ROTATE_180)
        elif orientation == 6:
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        elif orientation == 8:
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    except Exception:
        pass
    h, w = img.shape[:2]
    long_side = max(h, w)
    if long_side > max_side:
        scale = max_side / long_side
        img = cv2.resize(img, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_AREA)
    return img


# ============================================================
# 用户交互
# ============================================================

def ask_user_roi(img_bgr):
    """弹窗让用户分别框选左右玩家区。"""
    H, W = img_bgr.shape[:2]

    print("\n" + "=" * 70)
    print(">>> 第 1 步：框选【左侧玩家区】")
    print("  操作：拖动鼠标画框 → 按 Enter 确认")
    print("=" * 70)

    win1 = f"STEP 1/2 LEFT ({W}x{H})  ENTER=OK"
    cv2.namedWindow(win1, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win1, 1200, 700)
    lx, ly, lw, lh = cv2.selectROI(win1, img_bgr,
                                    showCrosshair=True,
                                    fromCenter=False)
    cv2.destroyWindow(win1)
    if lw == 0 or lh == 0:
        return None, None
    left_rect = (int(lx), int(ly), int(lx + lw), int(ly + lh))
    print(f"  左侧 ROI: ({lx},{ly})-({lx+lw},{ly+lh})  {lw}x{lh}")

    preview = img_bgr.copy()
    cv2.rectangle(preview, (lx, ly), (lx + lw, ly + lh), (0, 255, 0), 3)

    print("\n" + "=" * 70)
    print(">>> 第 2 步：框选【右侧玩家区】")
    print("=" * 70)

    win2 = f"STEP 2/2 RIGHT ({W}x{H})  ENTER=OK"
    cv2.namedWindow(win2, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win2, 1200, 700)
    rx, ry, rw, rh = cv2.selectROI(win2, preview,
                                    showCrosshair=True,
                                    fromCenter=False)
    cv2.destroyWindow(win2)
    if rw == 0 or rh == 0:
        return None, None
    right_rect = (int(rx), int(ry), int(rx + rw), int(ry + rh))
    print(f"  右侧 ROI: ({rx},{ry})-({rx+rw},{ry+rh})  {rw}x{rh}")

    return left_rect, right_rect


# ============================================================
# 方块检测
# ============================================================

def find_markers_in_rect(img_bgr, rect):
    """在 rect 里找二维码角块，返回全图坐标的方块列表。"""
    rx0, ry0, rx1, ry1 = rect
    sub = img_bgr[ry0:ry1, rx0:rx1]

    gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray_c = clahe.apply(gray)

    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    mask_hsv = cv2.inRange(hsv, (0, 0, WHITE_MIN_V), (180, WHITE_MAX_S, 255))
    _, mask_gray = cv2.threshold(gray_c, 180, 255, cv2.THRESH_BINARY)
    mask_white = cv2.bitwise_and(mask_hsv, mask_gray)

    # 闭运算：3x3 迭代 1 —— 够连"外白框 + 内白点"，不粘相邻方块
    kernel_close = np.ones((3, 3), np.uint8)
    mask_closed = cv2.morphologyEx(mask_white, cv2.MORPH_CLOSE,
                                   kernel_close, iterations=1)

    mask_black = cv2.inRange(gray_c, 0, 60)

    contours, _ = cv2.findContours(mask_closed, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)

    marks = []
    for c in contours:
        bx, by, bw, bh = cv2.boundingRect(c)

        if not (SIDE_MIN <= bw <= SIDE_MAX and SIDE_MIN <= bh <= SIDE_MAX):
            continue
        ratio = bw / float(bh)
        if not (SQUARE_MIN <= ratio <= SQUARE_MAX):
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.05 * peri, True)
        if len(approx) != 4:
            continue
        if not cv2.isContourConvex(approx):
            continue

        roi_w = mask_white[by:by + bh, bx:bx + bw]
        roi_b = mask_black[by:by + bh, bx:bx + bw]
        total = bw * bh
        wr = cv2.countNonZero(roi_w) / float(total)
        br = cv2.countNonZero(roi_b) / float(total)
        if not (WHITE_RATIO_MIN <= wr <= WHITE_RATIO_MAX):
            continue
        if br < BLACK_RATIO_MIN:
            continue

        gx = rx0 + bx
        gy = ry0 + by
        marks.append((gx, gy, gx + bw - 1, gy + bh - 1, int(bw * bh)))

    return marks


def bbox(marks):
    """外包围矩形。"""
    x0 = min(m[0] for m in marks)
    y0 = min(m[1] for m in marks)
    x1 = max(m[2] for m in marks)
    y1 = max(m[3] for m in marks)
    return x0, y0, x1, y1


def pick_4_corners(marks):
    """从一堆方块里挑 4 个最靠近角落的。"""
    if len(marks) <= 4:
        return marks

    def cx(m):
        return (m[0] + m[2]) / 2

    def cy(m):
        return (m[1] + m[3]) / 2

    tl = min(marks, key=lambda m: cx(m) + cy(m))       # 左上
    br = max(marks, key=lambda m: cx(m) + cy(m))       # 右下
    tr = max(marks, key=lambda m: cx(m) - cy(m))       # 右上
    bl = max(marks, key=lambda m: cy(m) - cx(m))       # 左下

    picked = []
    for m in (tl, tr, br, bl):
        if m not in picked:
            picked.append(m)
    return picked


# ============================================================
# 主流程
# ============================================================

def run(path):
    if not os.path.exists(path):
        print(f"[跳过] 文件不存在: {path}")
        return

    t0 = time.time()
    img = load_image(path)
    if img is None:
        print(f"[跳过] 无法读取: {path}")
        return

    H, W = img.shape[:2]
    print(f"\n{'=' * 70}")
    print(f"处理: {path}  ({W}x{H})")
    print("=" * 70)

    # ---------- 弹窗框选 ----------
    left_rect, right_rect = ask_user_roi(img)
    if left_rect is None or right_rect is None:
        print("[取消] 用户没有选择区域")
        return

    # ---------- 检测 ----------
    t_detect = time.time()
    left_marks_raw = find_markers_in_rect(img, left_rect)
    right_marks_raw = find_markers_in_rect(img, right_rect)
    t_detect = time.time() - t_detect

    print(f"\n[检出] 左 {len(left_marks_raw)} / 右 {len(right_marks_raw)}")

    left_marks = pick_4_corners(left_marks_raw)
    right_marks = pick_4_corners(right_marks_raw)

    regions = {}
    if len(left_marks) >= 3:
        regions["Player1(左)"] = bbox(left_marks)
    if len(right_marks) >= 3:
        regions["Player2(右)"] = bbox(right_marks)

    print(f"\n[区域结果]")
    for name, (x0, y0, x1, y1) in regions.items():
        print(f"  {name}  x{x0}-{x1} y{y0}-{y1}  ({x1-x0+1}x{y1-y0+1})  "
              f"归一化 x{x0/W:.4f}-{x1/W:.4f} y{y0/H:.4f}-{y1/H:.4f}")

    if len(left_marks) != PER_SIDE or len(right_marks) != PER_SIDE:
        print(f"\n[警告] 每侧应有 {PER_SIDE} 个，实际 左 {len(left_marks)} / 右 {len(right_marks)}")

    # ---------- 绘制结果 ----------
    # 用户 ROI（紫色）
    for rect, label in ((left_rect, "ROI-L"), (right_rect, "ROI-R")):
        x0, y0, x1, y1 = rect
        cv2.rectangle(img, (x0, y0), (x1, y1), (255, 0, 255), 3)
        cv2.putText(img, label, (x0 + 5, y0 + 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 255), 2)

    # 所有检出（黄）
    for m in left_marks_raw + right_marks_raw:
        cv2.rectangle(img, (m[0], m[1]), (m[2], m[3]), (0, 255, 255), 2)

    # 4 角（绿）
    for m in left_marks + right_marks:
        cv2.rectangle(img, (m[0], m[1]), (m[2], m[3]), (0, 255, 0), 4)

    # 玩家区域（红/蓝）
    colors = {"Player1(左)": (255, 60, 120), "Player2(右)": (255, 220, 60)}
    for name, (x0, y0, x1, y1) in regions.items():
        cv2.rectangle(img, (x0, y0), (x1, y1), colors[name], 5)
        cv2.putText(img, f"{name} {x1-x0+1}x{y1-y0+1}",
                    (x0, max(0, y0 - 12)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9, colors[name], 2)

    base = os.path.splitext(os.path.basename(path))[0]
    out_path = f"{base}_region.png"
    cv2.imwrite(out_path, img)

    print(f"\n识别耗时: {t_detect * 1000:.1f}ms")
    print(f"总耗时: {(time.time() - t0) * 1000:.1f}ms")
    print(f"结果已保存: {out_path}")

    # ---------- 显示结果，按任意键关闭 ----------
    win = "Result  |  press any key to close"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, 1200, 700)
    cv2.imshow(win, img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    targets = sys.argv[1:] or IMAGES
    for p in targets:
        run(p)
    print("\n全部处理完成")