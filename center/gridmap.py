# -*- coding: utf-8 -*-
"""
gridmap.py
把「画面坐标」映射到「玩家 + 格子」。

区域划分：
- single（单摄像头）：画面左半 / 右半各属一名玩家，方向由 player1_side 决定。
- dual（双摄像头）：整个画面就是该摄像头对应玩家的一方区域。

每名玩家区域内部，按 layout 里各格子的归一化矩形判断卡片落在哪一格。
"""

# 判定格子的顺序：先中间的怪兽/魔陷/额外怪兽区，再周边单格
_LIST_ZONES = ("front", "back", "ex")
_SINGLE_ZONES = ("field", "grave", "deck", "exdeck")


def player_area(mode, player1_side, player, swap=False):
    """
    返回该玩家在画面中的区域 (x0, y0, x1, y1)，归一化 0-1。
    """
    if mode == "dual":
        return (0.0, 0.0, 1.0, 1.0)
    # single：左右各半
    p1_left = (player1_side != "right")
    if swap:
        p1_left = not p1_left
    is_p1 = str(player) == "1"
    left_is_p1 = p1_left
    if is_p1 == left_is_p1:
        return (0.0, 0.0, 0.5, 1.0)
    return (0.5, 0.0, 1.0, 1.0)


def _rect_hit(rect, nx, ny):
    return (rect["x"] <= nx < rect["x"] + rect["w"]
            and rect["y"] <= ny < rect["y"] + rect["h"])


def map_point(layout, px, py, area):
    """
    把画面归一化坐标 (px, py) 映射到 (zone, index)。
    area 为该玩家区域 (x0,y0,x1,y1)。命中不到返回 None。
    index：列表格子返回 0..n-1；单格返回 None。
    """
    x0, y0, x1, y1 = area
    if x1 <= x0 or y1 <= y0:
        return None
    nx = (px - x0) / (x1 - x0)
    ny = (py - y0) / (y1 - y0)
    if not (0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0):
        return None

    for zone in _LIST_ZONES:
        rects = layout.get(zone) or []
        for i, r in enumerate(rects):
            if _rect_hit(r, nx, ny):
                return (zone, i)
    for zone in _SINGLE_ZONES:
        r = layout.get(zone)
        if r and _rect_hit(r, nx, ny):
            return (zone, None)
    return None


def layout_overlay(layout):
    """给管理页面预览叠加用：返回 [(zone, index, x, y, w, h)]（归一化）。"""
    out = []
    for zone in _LIST_ZONES:
        for i, r in enumerate(layout.get(zone) or []):
            out.append((zone, i, r["x"], r["y"], r["w"], r["h"]))
    for zone in _SINGLE_ZONES:
        r = layout.get(zone)
        if r:
            out.append((zone, None, r["x"], r["y"], r["w"], r["h"]))
    return out
