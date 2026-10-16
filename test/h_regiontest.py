# -*- coding: utf-8 -*-
"""
h_regiontest.py
识别【横向】Player1 玩家区，点击输出所属格子。

横板布局（7 列 × 3 行）：
             列1    列2    列3    列4    列5    列6    列7
    行1:     -      -     EX1     -     EX2     -      -
    行2:    场地   前场1  前场2  前场3  前场4  前场5  墓地
    行3:    额外   后场1  后场2  后场3  后场4  后场5  卡组

尺寸判断：按 ROI 宽度比例，不依赖绝对像素。
"""

import os
import sys

import cv2
import numpy as np

IMAGES = [r"dmh2.jpg"]
MAX_SIDE = 1920

# ============================================================
# 方块检测参数
# ============================================================
# 尺寸：占 ROI 宽度的比例（不依赖绝对像素）
SIDE_MIN_RATIO = 0.04        # 最小边长 = ROI 宽的 4%
SIDE_MAX_RATIO = 0.10        # 最大边长 = ROI 宽的 10%

SQUARE_MIN = 0.75
SQUARE_MAX = 1.35

# 白占比
WHITE_RATIO_MIN = 0.05
WHITE_RATIO_MAX = 0.85

# 内部黑（关闭）
INNER_BLACK_MIN = 0.0
INNER_MARGIN = 0.30

# 灰度 std
STD_MIN = 15

# HSV 阈值
WHITE_MIN_V = 120
WHITE_MAX_S = 160

# CLAHE / 腐蚀
CLAHE_CLIP = 4.0
ERODE_KERNEL = 5

# ============================================================
# 横板布局参数
# ============================================================
SRC_CORNER_RATIO = 0.043
PLAYER_AREA_W_H_RATIO = 2.2

GRID_ROWS = 3
GRID_COLS = 7


# ============================================================
# 横板格子定义
# ============================================================
H_LAYOUT = [
    # 行 1（EX 区）
    (1, 3, "EX", 1),
    (1, 5, "EX", 2),

    # 行 2（前场 + 场地 + 墓地）
    (2, 1, "场地魔法", None),
    (2, 2, "前场", 1),
    (2, 3, "前场", 2),
    (2, 4, "前场", 3),
    (2, 5, "前场", 4),
    (2, 6, "前场", 5),
    (2, 7, "墓地", None),

    # 行 3（后场 + 额外 + 卡组）
    (3, 1, "额外卡组", None),
    (3, 2, "后场", 1),
    (3, 3, "后场", 2),
    (3, 4, "后场", 3),
    (3, 5, "后场", 4),
    (3, 6, "后场", 5),
    (3, 7, "卡组", None),
]


def get_layout():
    return H_LAYOUT


# ============================================================
# 图像读取
# ============================================================

def load_image(path, max_side=MAX_SIDE):
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
    H, W = img_bgr.shape[:2]

    print("\n" + "=" * 70)
    print(">>> 框选【横向 Player1 玩家区】")
    print("=" * 70)
    win1 = f"SELECT Player1 (horizontal)  ({W}x{H})  ENTER=OK"
    cv2.namedWindow(win1, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win1, 1200, 700)
    x, y, w, h = cv2.selectROI(win1, img_bgr,
                                showCrosshair=True, fromCenter=False)
    cv2.destroyWindow(win1)
    if w == 0 or h == 0:
        return None
    rect = (int(x), int(y), int(x + w), int(y + h))
    print(f"  框选区域: {rect}  尺寸 {w}x{h}")
    return rect


# ============================================================
# 象限筛选
# ============================================================

def filter_by_quadrant(marks, rect):
    """每个象限只保留 1 个最靠角的方块。"""
    if len(marks) <= 4:
        return marks

    rx0, ry0, rx1, ry1 = rect
    mid_x = (rx0 + rx1) / 2
    mid_y = (ry0 + ry1) / 2

    quadrants = {'tl': [], 'tr': [], 'bl': [], 'br': []}
    for m in marks:
        cx = (m[0] + m[2]) / 2
        cy = (m[1] + m[3]) / 2
        if cx < mid_x and cy < mid_y:
            quadrants['tl'].append(m)
        elif cx >= mid_x and cy < mid_y:
            quadrants['tr'].append(m)
        elif cx < mid_x and cy >= mid_y:
            quadrants['bl'].append(m)
        else:
            quadrants['br'].append(m)

    corners_ref = {'tl': (rx0, ry0), 'tr': (rx1, ry0),
                   'bl': (rx0, ry1), 'br': (rx1, ry1)}
    picked = []
    for q in ('tl', 'tr', 'bl', 'br'):
        lst = quadrants[q]
        if not lst:
            continue
        qx, qy = corners_ref[q]
        best = min(lst, key=lambda m: ((m[0] + m[2]) / 2 - qx) ** 2 +
                                       ((m[1] + m[3]) / 2 - qy) ** 2)
        picked.append(best)
    return picked


# ============================================================
# 方块检测
# ============================================================

def find_markers_in_rect(img_bgr, rect):
    """
    在 ROI 里找定位方块。
    尺寸判断用"占 ROI 宽度的比例"，不依赖绝对像素。
    """
    rx0, ry0, rx1, ry1 = rect
    sub = img_bgr[ry0:ry1, rx0:rx1]

    # ---------- 根据 ROI 宽度，算出实际像素范围 ----------
    roi_w = rx1 - rx0
    side_min = int(roi_w * SIDE_MIN_RATIO)
    side_max = int(roi_w * SIDE_MAX_RATIO)

    gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=(8, 8))
    gray_c = clahe.apply(gray)

    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    mask_hsv = cv2.inRange(hsv, (0, 0, WHITE_MIN_V), (180, WHITE_MAX_S, 255))
    _, mask_gray = cv2.threshold(gray_c, 180, 255, cv2.THRESH_BINARY)
    mask_white = cv2.bitwise_and(mask_hsv, mask_gray)

    kernel_close = np.ones((3, 3), np.uint8)
    mask_closed = cv2.morphologyEx(mask_white, cv2.MORPH_CLOSE,
                                   kernel_close, iterations=1)
    kernel_erode = np.ones((ERODE_KERNEL, ERODE_KERNEL), np.uint8)
    mask_closed = cv2.erode(mask_closed, kernel_erode, iterations=1)

    contours, _ = cv2.findContours(mask_closed, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)

    marks = []
    for c in contours:
        bx, by, bw, bh = cv2.boundingRect(c)

        # 过滤 1：边长（按比例）
        if not (side_min <= bw <= side_max and
                side_min <= bh <= side_max):
            continue
        # 过滤 2：宽高比 0.75~1.35
        ratio = bw / float(bh)
        if not (SQUARE_MIN <= ratio <= SQUARE_MAX):
            continue
        # 过滤 3：四边形 + 凸
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.05 * peri, True)
        if len(approx) != 4:
            continue
        if not cv2.isContourConvex(approx):
            continue
        # 过滤 4：白占比 0.05~0.85
        roi_w_mask = mask_white[by:by + bh, bx:bx + bw]
        total = bw * bh
        wr = cv2.countNonZero(roi_w_mask) / float(total)
        if wr < WHITE_RATIO_MIN or wr > WHITE_RATIO_MAX:
            continue
        # 过滤 5：内部黑（已关闭）
        if INNER_BLACK_MIN > 0.0:
            mx = int(bw * INNER_MARGIN)
            my = int(bh * INNER_MARGIN)
            ix0, iy0 = bx + mx, by + my
            ix1, iy1 = bx + bw - mx, by + bh - my
            if ix1 > ix0 and iy1 > iy0:
                roi_b_inner = cv2.inRange(gray_c, 0, 60)[iy0:iy1, ix0:ix1]
                inner_area = (ix1 - ix0) * (iy1 - iy0)
                inner_black = cv2.countNonZero(roi_b_inner) / float(inner_area)
                if inner_black < INNER_BLACK_MIN:
                    continue
        # 过滤 6：灰度 std ≥ 15
        roi_g = gray_c[by:by + bh, bx:bx + bw]
        std_val = float(np.std(roi_g))
        if std_val < STD_MIN:
            continue

        gx = rx0 + bx
        gy = ry0 + by
        marks.append((gx, gy, gx + bw - 1, gy + bh - 1, int(bw * bh)))

    # 象限筛选
    marks = filter_by_quadrant(marks, rect)
    return marks


# ============================================================
# 4 角分配
# ============================================================

def assign_corners(marks, roi_x0=0, roi_x1=None):
    """
    4 角分配。
    4 个方块：按 x/y 中位数分四象限
    3 个方块：同上，缺 1 个
    2 个方块同行/同列：用 PLAYER_AREA_W_H_RATIO 推算
    2 个对角：无法推算
    """
    detail = {'items': [], 'assigned': {}, 'inferred': [], 'reason': ''}
    if len(marks) < 2:
        detail['reason'] = f'只检出 {len(marks)} 个方块'
        return None, 0, detail

    items = [{'cx': (m[0] + m[2]) / 2, 'cy': (m[1] + m[3]) / 2} for m in marks]
    detail['items'] = [(it['cx'], it['cy']) for it in items]

    xs = [it['cx'] for it in items]
    ys = [it['cy'] for it in items]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x
    height = max_y - min_y
    tol_x = max(width * 0.3, 15)
    tol_y = max(height * 0.3, 15)

    corners = {}

    if len(items) == 4:
        mid_x = (min_x + max_x) / 2
        mid_y = (min_y + max_y) / 2
        for it in items:
            left = it['cx'] < mid_x
            top = it['cy'] < mid_y
            if top and left:
                c = 'tl'
            elif top and not left:
                c = 'tr'
            elif not top and not left:
                c = 'br'
            else:
                c = 'bl'
            if c not in corners:
                corners[c] = it

    elif len(items) == 3:
        mid_x = (min_x + max_x) / 2
        mid_y = (min_y + max_y) / 2
        for it in items:
            left = it['cx'] < mid_x
            top = it['cy'] < mid_y
            if top and left:
                c = 'tl'
            elif top and not left:
                c = 'tr'
            elif not top and not left:
                c = 'br'
            else:
                c = 'bl'
            if c not in corners:
                corners[c] = it

    elif len(items) == 2:
        a, b = items[0], items[1]
        dx = abs(a['cx'] - b['cx'])
        dy = abs(a['cy'] - b['cy'])

        if dy < tol_y and dx > tol_x:
            # 2 点同行
            left_pt = a if a['cx'] < b['cx'] else b
            right_pt = b if a['cx'] < b['cx'] else a
            corners['tl'] = left_pt
            corners['tr'] = right_pt
            player_w = right_pt['cx'] - left_pt['cx']
            player_h = player_w / PLAYER_AREA_W_H_RATIO
            corners['bl'] = {'cx': left_pt['cx'],
                             'cy': left_pt['cy'] + player_h,
                             'inferred': True}
            corners['br'] = {'cx': right_pt['cx'],
                             'cy': right_pt['cy'] + player_h,
                             'inferred': True}
            detail['reason'] = f'2 点同行 → 往下推 (h={player_h:.0f})'
        elif dx < tol_x and dy > tol_y:
            # 2 点同列
            top_pt = a if a['cy'] < b['cy'] else b
            bot_pt = b if a['cy'] < b['cy'] else a
            corners['tl'] = top_pt
            corners['bl'] = bot_pt
            player_h = bot_pt['cy'] - top_pt['cy']
            player_w = player_h * PLAYER_AREA_W_H_RATIO
            corners['tr'] = {'cx': top_pt['cx'] + player_w,
                             'cy': top_pt['cy'], 'inferred': True}
            corners['br'] = {'cx': bot_pt['cx'] + player_w,
                             'cy': bot_pt['cy'], 'inferred': True}
            detail['reason'] = f'2 点同列 → 往右推 (w={player_w:.0f})'
        else:
            detail['reason'] = '2 点对角，无法推算'
            return None, 0, detail

    detail['assigned'] = {c: (corners[c]['cx'], corners[c]['cy'])
                          for c in corners if not corners[c].get('inferred')}
    for c in corners:
        if corners[c].get('inferred'):
            detail['inferred'].append((c, corners[c]['cx'], corners[c]['cy']))

    # 平行四边形约束推缺失
    for _ in range(3):
        if len(corners) == 4:
            break
        missing = [c for c in ('tl', 'tr', 'br', 'bl') if c not in corners]
        for c in missing:
            opposite = {'tl': 'br', 'tr': 'bl', 'br': 'tl', 'bl': 'tr'}[c]
            others = [x for x in ('tl', 'tr', 'bl', 'br')
                      if x != c and x != opposite]
            if opposite in corners and all(o in corners for o in others):
                p1 = np.array([corners[others[0]]['cx'],
                               corners[others[0]]['cy']])
                p2 = np.array([corners[others[1]]['cx'],
                               corners[others[1]]['cy']])
                po = np.array([corners[opposite]['cx'],
                               corners[opposite]['cy']])
                pc = p1 + p2 - po
                corners[c] = {'cx': pc[0], 'cy': pc[1], 'inferred': True}
                detail['inferred'].append((c, pc[0], pc[1]))

    if len(corners) < 4:
        detail['reason'] += f' | 仍缺 {4 - len(corners)} 个'
        return None, len(detail['assigned']), detail

    result = {c: (corners[c]['cx'], corners[c]['cy'])
              for c in ('tl', 'tr', 'br', 'bl')}
    return result, len(detail['assigned']), detail


# ============================================================
# 透视变换
# ============================================================

def compute_homography(corners):
    if corners is None:
        return None, None
    src = np.float32([corners['tl'], corners['tr'],
                      corners['br'], corners['bl']])
    r = SRC_CORNER_RATIO
    dst = np.float32([[r, r], [1 - r, r], [1 - r, 1 - r], [r, 1 - r]])
    H = cv2.getPerspectiveTransform(src, dst)
    inv_H = cv2.getPerspectiveTransform(dst, src)
    return H, inv_H


def map_to_normalized(H, px, py):
    if H is None:
        return None
    pt = np.array([[[px, py]]], dtype=np.float32)
    mapped = cv2.perspectiveTransform(pt, H)[0, 0]
    return float(mapped[0]), float(mapped[1])


def map_to_image(inv_H, nx, ny):
    if inv_H is None:
        return None
    pt = np.array([[[nx, ny]]], dtype=np.float32)
    mapped = cv2.perspectiveTransform(pt, inv_H)[0, 0]
    return float(mapped[0]), float(mapped[1])


# ============================================================
# 正空间区域
# ============================================================

def build_regions():
    r = SRC_CORNER_RATIO
    x0, x1 = r, 1.0 - r
    y0, y1 = r, 1.0 - r
    grid_w = x1 - x0
    grid_h = y1 - y0
    cell_w = grid_w / GRID_COLS
    cell_h = grid_h / GRID_ROWS

    regions = []
    for (row, col, ctype, index) in get_layout():
        if ctype is None:
            continue
        cx0 = x0 + (col - 1) * cell_w
        cy0 = y0 + (row - 1) * cell_h
        regions.append({
            'type': ctype, 'row': row, 'col': col, 'index': index,
            'x0': cx0, 'y0': cy0, 'x1': cx0 + cell_w, 'y1': cy0 + cell_h,
        })
    return regions


def hit_test_normalized(regions, nx, ny):
    if nx < 0 or nx > 1 or ny < 0 or ny > 1:
        return None
    for r in regions:
        if r['x0'] <= nx <= r['x1'] and r['y0'] <= ny <= r['y1']:
            return r
    return None


def region_to_image_polygon(region, inv_H):
    corners = [
        (region['x0'], region['y0']),
        (region['x1'], region['y0']),
        (region['x1'], region['y1']),
        (region['x0'], region['y1']),
    ]
    pts = []
    for (nx, ny) in corners:
        p = map_to_image(inv_H, nx, ny)
        if p is None:
            return None
        pts.append(p)
    return np.array(pts, dtype=np.float32)


# ============================================================
# 主流程
# ============================================================

WIN = "Click to query  |  ESC or Q to quit"


def run(path):
    if not os.path.exists(path):
        print(f"[跳过] 文件不存在: {path}")
        return
    img = load_image(path)
    if img is None:
        print(f"[跳过] 无法读取: {path}")
        return

    H_img, W_img = img.shape[:2]
    print(f"\n{'=' * 70}")
    print(f"处理: {path}  ({W_img}x{H_img})")
    print(f"横板模式：只识别 Player1")
    print("=" * 70)

    rect = ask_user_roi(img)
    if rect is None:
        print("[取消]")
        return

    print(f"\n--- Player1 处理 ---")
    marks = find_markers_in_rect(img, rect)
    print(f"  检出方块: {len(marks)} 个")
    for i, m in enumerate(sorted(marks, key=lambda v: (v[1], v[0]))):
        cx = (m[0] + m[2]) // 2
        cy = (m[1] + m[3]) // 2
        print(f"    P1-{i}: 中心=({cx},{cy})  "
              f"边长={m[2]-m[0]+1}x{m[3]-m[1]+1}")

    corners, real_count, detail = assign_corners(
        marks, roi_x0=rect[0], roi_x1=rect[2])

    print(f"  --- 4 角分配 ---")
    for c in ('tl', 'tr', 'br', 'bl'):
        if c in detail['assigned']:
            x, y = detail['assigned'][c]
            print(f"    {c}: ({x:.0f}, {y:.0f})  ✅ 实际")
    for (c, x, y) in detail['inferred']:
        print(f"    {c}: ({x:.0f}, {y:.0f})  ⚠ 推算")
    if detail['reason']:
        print(f"  说明: {detail['reason']}")

    if corners is None:
        print(f"\n[错误] Player1 无法定位 4 个角")
        return

    H, inv_H = compute_homography(corners)
    regions = build_regions()
    print(f"  网格: {len(regions)} 个格子（7 列 × 3 行）")

    vis = img.copy()
    cv2.rectangle(vis, (rect[0], rect[1]), (rect[2], rect[3]),
                  (255, 0, 255), 2)
    cv2.putText(vis, "ROI-P1", (rect[0] + 5, rect[1] + 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 255), 2)

    for c in ('tl', 'tr', 'br', 'bl'):
        x, y = corners[c]
        cv2.circle(vis, (int(x), int(y)), 10, (0, 255, 0), -1)

    def draw_regions(regions, inv_H, color):
        for r in regions:
            poly = region_to_image_polygon(r, inv_H)
            if poly is None:
                continue
            pts = poly.astype(np.int32).reshape((-1, 1, 2))
            cv2.polylines(vis, [pts], True, color, 1)
            cx_norm = (r['x0'] + r['x1']) / 2
            cy_norm = (r['y0'] + r['y1']) / 2
            p = map_to_image(inv_H, cx_norm, cy_norm)
            if p:
                label_en = {
                    '前场': 'MON', '后场': 'BACK', 'EX': 'EX',
                    '卡组': 'DECK', '墓地': 'GY',
                    '额外卡组': 'ED', '场地魔法': 'FIELD',
                }.get(r['type'], r['type'])
                if r['index'] is not None:
                    label = f"{label_en}{r['index']}"
                else:
                    label = label_en
                cv2.putText(vis, label, (int(p[0] - 15), int(p[1])),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

    draw_regions(regions, inv_H, (255, 60, 120))

    def on_click(event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        norm = map_to_normalized(H, x, y)
        result = None
        if norm is not None:
            result = hit_test_normalized(regions, norm[0], norm[1])

        if result is None:
            print(f"\n[点击] ({x},{y}) → 不在 Player1 任何格子内")
        else:
            if result['index'] is not None:
                print(f"\n[点击] ({x},{y}) → Player1 | "
                      f"{result['type']} | 第 {result['index']} 号 "
                      f"(行 {result['row']} 列 {result['col']})")
            else:
                print(f"\n[点击] ({x},{y}) → Player1 | {result['type']} "
                      f"(行 {result['row']} 列 {result['col']})")

        vis2 = vis.copy()
        cv2.circle(vis2, (x, y), 8, (0, 255, 255), 2)
        if result is not None:
            poly = region_to_image_polygon(result, inv_H)
            if poly is not None:
                pts = poly.astype(np.int32).reshape((-1, 1, 2))
                cv2.polylines(vis2, [pts], True, (0, 255, 255), 3)
        cv2.imshow(WIN, vis2)

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 1200, 700)
    cv2.setMouseCallback(WIN, on_click)
    cv2.imshow(WIN, vis)

    print("\n" + "=" * 70)
    print(">>> 点击画面任意位置查询（只识别 Player1）")
    print("    ESC/Q 退出")
    print("=" * 70)

    while True:
        key = cv2.waitKey(20) & 0xFF
        if key in (27, ord('q'), ord('Q')):
            break

    cv2.destroyAllWindows()
    print("\n完成")


if __name__ == "__main__":
    targets = sys.argv[1:] or IMAGES
    for p in targets:
        run(p)
    print("\n全部处理完成")