# -*- coding: utf-8 -*-
"""
calib.py
定位/校准：用 4 个「二维码角块」样式定位方块建立单应变换，把画面坐标映射到
「正空间」(0~1)，再在正空间里按布局查出 (玩家, 格子)。
- 纵向：移植自 test/regiontest.py（7 行 × 3 列，PARAMS_V）。
- 横向：移植自 test/h_regiontest.py（3 行 × 7 列，PARAMS_H）。
- 双摄像头每路可用 dual.cameras[i].orientation 单独设为 horizontal / vertical；
  单摄像头仍固定为纵向。

流程：
  1. 管理页手动框选玩家区域 ROI（one per player / per camera）。
  2. 在 ROI 内 find_markers_in_rect 检测定位方块（边长/宽高比/白占比/内部黑/灰度 std 等过滤）。
  3. assign_corners 把方块分配到 tl/tr/br/bl（2/3 点用平行四边形约束推算）。
  4. compute_homography 求「画面 → 正空间」的 H 与逆变换 inv_H。
  5. 正空间里按格子表切网格；卡牌中心坐标经 H 映射后查格子。

坐标约定：
  - 画面坐标用「像素」；正空间为 0~1。
  - 单应矩阵由像素角点算出，故 map_point 接收像素坐标。

仅内存保存：CalibrationStore 里的结果默认放内存；传入 path 时会读写 JSON，
因此 center 重启后不必重新框选。

依赖 cv2 / numpy，均为延迟导入（未安装时本模块仍可导入，只是无法校准与映射）。
"""

import threading

# ============================================================
# 定位方块检测参数
# ============================================================
# 纵向（单摄像头）：移植自 test/regiontest.py
PARAMS_V = {
    "side_min_ratio": 0.04, "side_max_ratio": 0.25,  # 边长占 ROI 宽的比例（自适应分辨率）
    "square_min": 0.75, "square_max": 1.35,  # 正方形
    "white_ratio_min": 0.05, "white_ratio_max": 0.90,
    "white_min_v": 120, "white_max_s": 160,  # HSV：低饱和 + 高亮度
    "inner_black_min": 0.01,                 # 内部黑像素占比下限
    "inner_margin": 0.30,
    "std_min": 15,                           # 灰度 std 下限（排除纯白反光）
    "clahe_clip": 4.0,                       # 压制屏幕反光过曝
    "erode_kernel": 3,                       # 腐蚀核（分离粘连）
    "area_w_h_ratio": 0.42,                  # 玩家区 宽/高 比（2 点推算用）
    "same_col_auto": True,                   # 2 点同列：按 ROI 左右判断往哪边推
}

# 横向（双摄像头可选）：移植自 test/h_regiontest.py
PARAMS_H = {
    "side_min_ratio": 0.04, "side_max_ratio": 0.10,  # 边长占 ROI 宽的比例
    "square_min": 0.75, "square_max": 1.35,
    "white_ratio_min": 0.05, "white_ratio_max": 0.85,   # 过滤反光块（纯白 wr > 0.85）
    "white_min_v": 120, "white_max_s": 160,
    "inner_black_min": 0.0,                  # 关闭内部黑约束
    "inner_margin": 0.30,
    "std_min": 15,
    "clahe_clip": 4.0,
    "erode_kernel": 5,
    "area_w_h_ratio": 2.2,
    "same_col_auto": False,                  # 2 点同列：假定为左列，往右推
}


ORIENTATION_H = "horizontal"
ORIENTATION_V = "vertical"


def normalize_orientation(value):
    """把配置里的方向统一成 horizontal / vertical，缺省为 horizontal。"""
    v = str(value).strip().lower()
    if v in ("vertical", "portrait", "v", "纵向", "竖向", "竖"):
        return ORIENTATION_V
    return ORIENTATION_H


def params_for(mode, orientation=ORIENTATION_H):
    """按模式与方向取检测参数：横向用 PARAMS_H，纵向用 PARAMS_V。"""
    if str(mode) == "dual" and normalize_orientation(orientation) == ORIENTATION_H:
        return PARAMS_H
    return PARAMS_V


def _cv2():
    import cv2
    return cv2


def _np():
    import numpy as np
    return np


# ============================================================
# 布局参数
# ============================================================
# 定位方块在「正空间」里的内缩比例（方块中心 ≠ 玩家区边缘）
SRC_CORNER_RATIO = 0.043

# 单摄像头（纵向）每名玩家的网格：7 行 × 3 列
GRID_ROWS = 7
GRID_COLS = 3


# ============================================================
# 格子表
# ============================================================
# 每格 = (行, 列, zone, index)：
#   行/列从 1 开始；zone 用 center 的命名；index 为列表格子的下标，单格为 None。
# zone：back(魔陷) / front(怪兽) / ex(额外怪兽) / deck(卡组) /
#       grave(墓地) / exdeck(额外卡组) / field(场地魔法)

# 单摄像头 · 左侧玩家（纵向 7×3）
SINGLE_LEFT = [
    (1, 1, "exdeck", None), (1, 2, "field", None),
    (2, 1, "back", 0), (2, 2, "front", 0),
    (3, 1, "back", 1), (3, 2, "front", 1), (3, 3, "ex", 0),
    (4, 1, "back", 2), (4, 2, "front", 2),
    (5, 1, "back", 3), (5, 2, "front", 3), (5, 3, "ex", 1),
    (6, 1, "back", 4), (6, 2, "front", 4),
    (7, 1, "deck", None), (7, 2, "grave", None),
]

# 单摄像头 · 右侧玩家（纵向 7×3，左右镜像）
# ex 索引按「玩家自身左手侧=0、右手侧=1」；玩家2 面向相反方向，故与玩家1上下相反
SINGLE_RIGHT = [
    (1, 3, "deck", None), (1, 2, "grave", None),
    (2, 2, "front", 0), (2, 3, "back", 0),
    (3, 1, "ex", 1), (3, 2, "front", 1), (3, 3, "back", 1),
    (4, 2, "front", 2), (4, 3, "back", 2),
    (5, 1, "ex", 0), (5, 2, "front", 3), (5, 3, "back", 3),
    (6, 2, "front", 4), (6, 3, "back", 4),
    (7, 2, "field", None), (7, 3, "exdeck", None),
]

# 双摄像头 · 横向图：等于「player1 纵向布局逆时针旋转 90°」→ 3 行 × 7 列
# （旋转映射：新行 = 4 - 列，新列 = 行）；与 test/h_regiontest.py 的 H_LAYOUT 一致
DUAL = [
    # row 1
    (1, 3, "ex", 0), (1, 5, "ex", 1),
    # row 2
    (2, 1, "field", None), (2, 2, "front", 0), (2, 3, "front", 1),
    (2, 4, "front", 2), (2, 5, "front", 3), (2, 6, "front", 4),
    (2, 7, "grave", None),
    # row 3
    (3, 1, "exdeck", None), (3, 2, "back", 0), (3, 3, "back", 1),
    (3, 4, "back", 2), (3, 5, "back", 3), (3, 6, "back", 4),
    (3, 7, "deck", None),
]


TABLE_SINGLE = {"1": {"rows": GRID_ROWS, "cols": GRID_COLS, "cells": SINGLE_LEFT},
                "2": {"rows": GRID_ROWS, "cols": GRID_COLS, "cells": SINGLE_RIGHT}}
TABLE_DUAL = {"rows": 3, "cols": 7, "cells": DUAL}
# 双摄像头 · 竖向图：等于 player1 的纵向布局 → 7 行 × 3 列。
# 与横向 DUAL 一样，两路共用同一张绝对布局，不随 player / swap 改变。
TABLE_DUAL_V = {"rows": GRID_ROWS, "cols": GRID_COLS, "cells": SINGLE_LEFT}


def table_for(mode, player, orientation=ORIENTATION_H):
    """按模式、玩家与方向取格子表。dual 两路共用横向或竖向表。"""
    if str(mode) == "dual":
        if normalize_orientation(orientation) == ORIENTATION_V:
            return TABLE_DUAL_V
        return TABLE_DUAL
    return TABLE_SINGLE.get(str(player), TABLE_SINGLE["1"])


def build_regions(table):
    """把格子表转成正空间里的矩形列表 [{zone,index,x0,y0,x1,y1}]。"""
    r = SRC_CORNER_RATIO
    rows = int(table["rows"])
    cols = int(table["cols"])
    span = 1.0 - 2.0 * r
    cw = span / cols
    ch = span / rows
    regions = []
    for (row, col, zone, index) in table["cells"]:
        x0 = r + (col - 1) * cw
        y0 = r + (row - 1) * ch
        regions.append({"zone": zone, "index": index,
                        "x0": x0, "y0": y0, "x1": x0 + cw, "y1": y0 + ch})
    return regions


# ============================================================
# 定位方块检测（移植自 test/regiontest.py）
# ============================================================

def filter_by_quadrant(marks, rect):
    """每个象限只保留 1 个最靠角的方块，保证共 4 个。"""
    if len(marks) <= 4:
        return marks
    rx0, ry0, rx1, ry1 = rect
    mid_x = (rx0 + rx1) / 2.0
    mid_y = (ry0 + ry1) / 2.0
    quadrants = {"tl": [], "tr": [], "bl": [], "br": []}
    for m in marks:
        cx = (m[0] + m[2]) / 2.0
        cy = (m[1] + m[3]) / 2.0
        if cx < mid_x and cy < mid_y:
            quadrants["tl"].append(m)
        elif cx >= mid_x and cy < mid_y:
            quadrants["tr"].append(m)
        elif cx < mid_x and cy >= mid_y:
            quadrants["bl"].append(m)
        else:
            quadrants["br"].append(m)
    corners_ref = {"tl": (rx0, ry0), "tr": (rx1, ry0),
                   "bl": (rx0, ry1), "br": (rx1, ry1)}
    picked = []
    for q in ("tl", "tr", "bl", "br"):
        lst = quadrants[q]
        if not lst:
            continue
        qx, qy = corners_ref[q]
        best = min(lst, key=lambda m: (((m[0] + m[2]) / 2.0 - qx) ** 2 +
                                       ((m[1] + m[3]) / 2.0 - qy) ** 2))
        picked.append(best)
    return picked


def find_markers_in_rect(img_bgr, rect, params=None):
    """
    在 ROI 内找定位方块，返回 [(x0, y0, x1, y1, area), ...]。
    流程：灰度+CLAHE → 白掩膜 → 闭运算 → 腐蚀 → 轮廓六重过滤 → 象限筛选。
    params 决定各阈值（纵向用 PARAMS_V，横向用 PARAMS_H）。
    """
    cv2 = _cv2()
    np = _np()
    p = params or PARAMS_V
    rx0, ry0, rx1, ry1 = [int(v) for v in rect]
    sub = img_bgr[ry0:ry1, rx0:rx1]
    if sub.size == 0:
        return []

    # 按当前 ROI 宽度换算边长范围（比例，任意分辨率/缩放都适用）
    roi_w = rx1 - rx0
    side_min = int(roi_w * p["side_min_ratio"])
    side_max = int(roi_w * p["side_max_ratio"])

    # ① 灰度化 + CLAHE
    gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=p["clahe_clip"], tileGridSize=(8, 8))
    gray_c = clahe.apply(gray)

    # ② 白色掩膜：HSV 低饱和高亮 ∩ 灰度亮
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    mask_hsv = cv2.inRange(hsv, (0, 0, p["white_min_v"]), (180, p["white_max_s"], 255))
    _, mask_gray = cv2.threshold(gray_c, 180, 255, cv2.THRESH_BINARY)
    mask_white = cv2.bitwise_and(mask_hsv, mask_gray)

    # ③ 闭运算：连接外白框与内白点
    kernel_close = np.ones((3, 3), np.uint8)
    mask_closed = cv2.morphologyEx(mask_white, cv2.MORPH_CLOSE,
                                   kernel_close, iterations=1)

    # ④ 腐蚀：分离粘连
    kernel_erode = np.ones((p["erode_kernel"], p["erode_kernel"]), np.uint8)
    mask_closed = cv2.erode(mask_closed, kernel_erode, iterations=1)

    mask_black = cv2.inRange(gray_c, 0, 60)

    # ⑤ 找轮廓 + 六重过滤
    contours, _ = cv2.findContours(mask_closed, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    marks = []
    for c in contours:
        bx, by, bw, bh = cv2.boundingRect(c)

        if not (side_min <= bw <= side_max
                and side_min <= bh <= side_max):
            continue
        ratio = bw / float(bh)
        if not (p["square_min"] <= ratio <= p["square_max"]):
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.05 * peri, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        roi_w = mask_white[by:by + bh, bx:bx + bw]
        wr = cv2.countNonZero(roi_w) / float(bw * bh)
        if wr < p["white_ratio_min"] or wr > p["white_ratio_max"]:
            continue
        # 内部黑（横向参数关闭：inner_black_min = 0.0）
        if p["inner_black_min"] > 0.0:
            mx = int(bw * p["inner_margin"])
            my = int(bh * p["inner_margin"])
            ix0, iy0 = bx + mx, by + my
            ix1, iy1 = bx + bw - mx, by + bh - my
            if ix1 > ix0 and iy1 > iy0:
                roi_b_inner = mask_black[iy0:iy1, ix0:ix1]
                inner_black = cv2.countNonZero(roi_b_inner) / float((ix1 - ix0) * (iy1 - iy0))
                if inner_black < p["inner_black_min"]:
                    continue
        roi_g = gray_c[by:by + bh, bx:bx + bw]
        if float(np.std(roi_g)) < p["std_min"]:
            continue

        gx = rx0 + bx
        gy = ry0 + by
        marks.append((gx, gy, gx + bw - 1, gy + bh - 1, int(bw * bh)))

    # ⑥ 象限筛选
    return filter_by_quadrant(marks, rect)


# ============================================================
# 4 角分配
# ============================================================

def assign_corners(marks, roi_x0=0, roi_x1=None, params=None):
    """
    把方块分配到 tl/tr/br/bl，返回 (corners, real_count, detail)。
    corners: {角: (cx, cy)} 或 None；real_count: 实际（非推算）角数。
    params 决定 2 点推算用的「玩家区宽高比」与同列的推列方向。
    """
    np = _np()
    p = params or PARAMS_V
    detail = {"items": [], "assigned": {}, "inferred": [], "reason": ""}
    if len(marks) < 2:
        detail["reason"] = "只检出 %d 个方块" % len(marks)
        return None, 0, detail

    items = [{"cx": (m[0] + m[2]) / 2.0, "cy": (m[1] + m[3]) / 2.0} for m in marks]
    detail["items"] = [(it["cx"], it["cy"]) for it in items]

    xs = [it["cx"] for it in items]
    ys = [it["cy"] for it in items]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x
    height = max_y - min_y
    tol_x = max(width * 0.3, 15)
    tol_y = max(height * 0.3, 15)

    corners = {}

    def _quadrant(it, mx, my):
        left = it["cx"] < mx
        top = it["cy"] < my
        if top and left:
            return "tl"
        if top and not left:
            return "tr"
        if not top and not left:
            return "br"
        return "bl"

    if len(items) == 4:
        mid_x = (min_x + max_x) / 2.0
        mid_y = (min_y + max_y) / 2.0
        for it in items:
            c = _quadrant(it, mid_x, mid_y)
            if c not in corners:
                corners[c] = it

    elif len(items) == 3:
        mid_x = (min_x + max_x) / 2.0
        mid_y = (min_y + max_y) / 2.0
        for it in items:
            c = _quadrant(it, mid_x, mid_y)
            if c not in corners:
                corners[c] = it

    elif len(items) == 2:
        a, b = items[0], items[1]
        dx = abs(a["cx"] - b["cx"])
        dy = abs(a["cy"] - b["cy"])
        ratio = p["area_w_h_ratio"]
        if dx < tol_x and dy > tol_y:               # 同列
            top_pt = a if a["cy"] < b["cy"] else b
            bot_pt = b if a["cy"] < b["cy"] else a
            player_h = bot_pt["cy"] - top_pt["cy"]
            player_w = player_h * ratio
            if p["same_col_auto"]:
                # 纵向：按 ROI 左右判断这一列在哪半 → 往另一边推
                col_x = (top_pt["cx"] + bot_pt["cx"]) / 2.0
                is_right_col = col_x > (roi_x0 + roi_x1) / 2.0 if roi_x1 is not None else False
            else:
                # 横向：假定检出的是左列 → 一律往右推
                is_right_col = False
            if is_right_col:
                corners["tr"] = top_pt
                corners["br"] = bot_pt
                corners["tl"] = {"cx": top_pt["cx"] - player_w, "cy": top_pt["cy"], "inferred": True}
                corners["bl"] = {"cx": bot_pt["cx"] - player_w, "cy": bot_pt["cy"], "inferred": True}
                detail["reason"] = "2 点同列 → 右列（往左推）"
            else:
                corners["tl"] = top_pt
                corners["bl"] = bot_pt
                corners["tr"] = {"cx": top_pt["cx"] + player_w, "cy": top_pt["cy"], "inferred": True}
                corners["br"] = {"cx": bot_pt["cx"] + player_w, "cy": bot_pt["cy"], "inferred": True}
                detail["reason"] = "2 点同列 → 左列（往右推）"
        elif dy < tol_y and dx > tol_x:             # 同行
            left_pt = a if a["cx"] < b["cx"] else b
            right_pt = b if a["cx"] < b["cx"] else a
            corners["tl"] = left_pt
            corners["tr"] = right_pt
            player_w = right_pt["cx"] - left_pt["cx"]
            player_h = player_w / ratio
            corners["bl"] = {"cx": left_pt["cx"], "cy": left_pt["cy"] + player_h, "inferred": True}
            corners["br"] = {"cx": right_pt["cx"], "cy": right_pt["cy"] + player_h, "inferred": True}
            detail["reason"] = "2 点同行 → 假设上排"
        else:
            detail["reason"] = "2 点对角，无法推算"
            return None, 0, detail

    detail["assigned"] = {c: (corners[c]["cx"], corners[c]["cy"])
                          for c in corners if not corners[c].get("inferred")}
    for c in corners:
        if corners[c].get("inferred"):
            detail["inferred"].append((c, corners[c]["cx"], corners[c]["cy"]))

    # 平行四边形约束推缺失角：缺角 = 相邻两角之和 - 对角
    for _ in range(3):
        if len(corners) == 4:
            break
        missing = [c for c in ("tl", "tr", "br", "bl") if c not in corners]
        for c in missing:
            opposite = {"tl": "br", "tr": "bl", "br": "tl", "bl": "tr"}[c]
            others = [x for x in ("tl", "tr", "br", "bl") if x != c and x != opposite]
            if opposite in corners and all(o in corners for o in others):
                p1 = np.array([corners[others[0]]["cx"], corners[others[0]]["cy"]])
                p2 = np.array([corners[others[1]]["cx"], corners[others[1]]["cy"]])
                po = np.array([corners[opposite]["cx"], corners[opposite]["cy"]])
                pc = p1 + p2 - po
                corners[c] = {"cx": float(pc[0]), "cy": float(pc[1]), "inferred": True}
                detail["inferred"].append((c, float(pc[0]), float(pc[1])))

    if len(corners) < 4:
        detail["reason"] += " | 仍缺 %d 个" % (4 - len(corners))
        return None, len(detail["assigned"]), detail

    result = {c: (corners[c]["cx"], corners[c]["cy"]) for c in ("tl", "tr", "br", "bl")}
    return result, len(detail["assigned"]), detail


# ============================================================
# 透视变换
# ============================================================

def compute_homography(corners):
    """4 角 → 正空间（0~1）的单应 H 与逆变换 inv_H。"""
    cv2 = _cv2()
    np = _np()
    if corners is None:
        return None, None
    src = np.float32([corners["tl"], corners["tr"], corners["br"], corners["bl"]])
    r = SRC_CORNER_RATIO
    dst = np.float32([[r, r], [1 - r, r], [1 - r, 1 - r], [r, 1 - r]])
    H = cv2.getPerspectiveTransform(src, dst)
    inv_H = cv2.getPerspectiveTransform(dst, src)
    return H, inv_H


# ============================================================
# 玩家校准结果
# ============================================================

CORNERS = ("tl", "tr", "br", "bl")


class PlayerCalib:
    """某摄像头 · 某玩家的校准结果：单应矩阵 + 正空间格子表。"""

    def __init__(self, cam_id, player, mode, roi, corners, H, inv_H, frame_size,
                 orientation=ORIENTATION_H, source="auto"):
        self.cam_id = cam_id
        self.player = str(player)
        self.mode = mode
        self.orientation = normalize_orientation(orientation)
        self.roi = tuple(int(v) for v in roi)
        self.corners = {c: (float(corners[c][0]), float(corners[c][1])) for c in CORNERS}
        self.H = H
        self.inv_H = inv_H
        self.frame_size = tuple(int(v) for v in frame_size)   # (W, H)
        self.source = source            # "auto"（拖框） / "manual"（点 4 个方块）
        self.regions = build_regions(table_for(mode, self.player, self.orientation))

    def map_point(self, px, py):
        """画面像素坐标 → (zone, index)；不在任何格子内返回 None。"""
        cv2 = _cv2()
        np = _np()
        if self.H is None:
            return None
        pt = np.array([[[float(px), float(py)]]], dtype=np.float32)
        m = cv2.perspectiveTransform(pt, self.H)[0, 0]
        nx, ny = float(m[0]), float(m[1])
        if nx < 0.0 or nx > 1.0 or ny < 0.0 or ny > 1.0:
            return None
        for r in self.regions:
            if r["x0"] <= nx <= r["x1"] and r["y0"] <= ny <= r["y1"]:
                return (r["zone"], r["index"])
        return None

    def polygons(self):
        """每个格子映射回画面的 4 个角：[(zone, index, [(x,y)*4]), ...]。"""
        cv2 = _cv2()
        np = _np()
        if self.inv_H is None:
            return []
        out = []
        for r in self.regions:
            pts = np.float32([[[r["x0"], r["y0"]], [r["x1"], r["y0"]],
                               [r["x1"], r["y1"]], [r["x0"], r["y1"]]]])
            m = cv2.perspectiveTransform(pts, self.inv_H)[0]
            poly = [(float(p[0]), float(p[1])) for p in m]
            out.append((r["zone"], r["index"], poly))
        return out

    def quad(self):
        """4 个定位方块中心（画面像素）按 tl/tr/br/bl 顺序。"""
        return [self.corners[c] for c in CORNERS]

    def status(self):
        return {
            "cam_id": self.cam_id, "player": self.player, "mode": self.mode,
            "orientation": self.orientation, "source": self.source,
            "roi": list(self.roi),
            "corners": {c: [int(round(self.corners[c][0])), int(round(self.corners[c][1]))]
                        for c in CORNERS},
            "frame_size": list(self.frame_size),
        }

    def to_dict(self):
        """可 JSON 序列化（用于保存，重启后重建）。"""
        return {
            "cam_id": self.cam_id, "player": self.player, "mode": self.mode,
            "orientation": self.orientation, "source": self.source,
            "roi": list(self.roi),
            "corners": {c: [self.corners[c][0], self.corners[c][1]] for c in CORNERS},
            "frame_size": list(self.frame_size),
        }

    @classmethod
    def from_dict(cls, d):
        corners = {c: (float(d["corners"][c][0]), float(d["corners"][c][1]))
                   for c in CORNERS}
        H, inv_H = compute_homography(corners)
        return cls(d["cam_id"], d["player"], d.get("mode", "single"),
                   d.get("roi") or (0, 0, 1, 1), corners,
                   H, inv_H, d.get("frame_size") or (0, 0),
                   d.get("orientation", ORIENTATION_H), d.get("source", "auto"))


def calibrate_player(img_bgr, roi, cam_id, player, mode, orientation=ORIENTATION_H):
    """
    在 ROI 内检测定位方块并建立校准。
    orientation：dual 每路的画面方向（horizontal / vertical），单摄像头忽略。
    成功返回 PlayerCalib；失败抛 ValueError（消息给管理页显示）。
    """
    cv2 = _cv2()
    roi = [int(v) for v in roi]
    h, w = img_bgr.shape[:2]
    orientation = normalize_orientation(orientation)
    params = params_for(mode, orientation)
    marks = find_markers_in_rect(img_bgr, roi, params)
    corners, real_count, detail = assign_corners(marks, roi_x0=roi[0], roi_x1=roi[2],
                                                 params=params)
    if corners is None:
        raise ValueError("未定位到 4 个定位方块：检出 %d 个，%s"
                         % (len(marks), detail.get("reason") or "无法分配 4 角"))
    H, inv_H = compute_homography(corners)
    return PlayerCalib(cam_id, player, mode, roi, corners, H, inv_H, (w, h),
                       orientation, source="auto")


def calibrate_player_manual(corners_pixels, cam_id, player, mode, frame_size,
                            orientation=ORIENTATION_H):
    """
    手动校准：直接使用用户框选的 4 个定位标识位置（画面像素），不再做自动检测。

    corners_pixels 顺序：tl → tr → br → bl（从左上角开始顺时针）。
    框选的每个小方格取其中心作为定位标识位置。
    """
    pts = [(float(p[0]), float(p[1])) for p in corners_pixels]
    if len(pts) != 4:
        raise ValueError("需要 4 个定位标识位置（tl→tr→br→bl 顺时针）")
    orientation = normalize_orientation(orientation)

    corners = {c: pts[i] for i, c in enumerate(CORNERS)}
    tl, tr, br, bl = corners["tl"], corners["tr"], corners["br"], corners["bl"]
    # 退化检查：面积过小说明四点过近/共线，单应矩阵不可靠
    area = abs((tr[0] - tl[0]) * (bl[1] - tl[1]) - (bl[0] - tl[0]) * (tr[1] - tl[1]))
    if area < 25.0:
        raise ValueError("4 个定位标识位置过近或共线，无法建立校准")

    H, inv_H = compute_homography(corners)
    if H is None:
        raise ValueError("无法计算单应矩阵")

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    roi = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
    return PlayerCalib(cam_id, player, mode, roi, corners, H, inv_H, frame_size,
                       orientation, source="manual")


# ============================================================
# 校准存储（内存 + 可选 JSON 持久化）
# ============================================================

class CalibrationStore:
    """保存所有校准结果（cam_id, player）→ PlayerCalib。

    传入 path 时会把结果写成 JSON，启动时自动读回 —— 管理页刷新 / center
    重启都不必重新框选；不传 path 则只放内存（旧行为）。
    """

    def __init__(self, path=None):
        self._lock = threading.RLock()
        self._items = {}
        self.path = path
        if path:
            self._load()

    def _load(self):
        import json
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        items = data.get("players") if isinstance(data, dict) else None
        for d in items or []:
            try:
                pc = PlayerCalib.from_dict(d)
            except (KeyError, TypeError, ValueError):
                continue
            self._items[(pc.cam_id, pc.player)] = pc

    def _save(self):
        if not self.path:
            return
        import json
        import os
        items = [pc.to_dict() for pc in self._items.values()]
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"players": items}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def set(self, calib):
        with self._lock:
            self._items[(calib.cam_id, calib.player)] = calib
            self._save()

    def get(self, cam_id, player):
        with self._lock:
            return self._items.get((cam_id, str(player)))

    def clear(self, cam_id=None, player=None):
        with self._lock:
            if cam_id is None:
                self._items.clear()
                self._save()
                return
            if player is None:
                for k in [k for k in self._items if k[0] == cam_id]:
                    self._items.pop(k, None)
                self._save()
                return
            self._items.pop((cam_id, str(player)), None)
            self._save()

    def quads(self):
        """所有定位方块的画面坐标，供 display 画定位方块：{cam_id: {player: [[x,y]*4]}}。"""
        with self._lock:
            items = list(self._items.values())
        out = {}
        for pc in items:
            out.setdefault(pc.cam_id, {})[pc.player] = \
                [[int(round(x)), int(round(y))] for (x, y) in pc.quad()]
        return out

    def status(self):
        with self._lock:
            items = list(self._items.values())
        return [pc.status() for pc in items]
