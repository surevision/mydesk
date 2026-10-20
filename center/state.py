# -*- coding: utf-8 -*-
"""
state.py
center 保存的「当前战场」权威状态。

- controller 发来的完整快照：整体替换，并记录哪些格子是「人工」设置的。
- 摄像头识别结果：只更新非人工格子（人工设置优先，便于容错）。
- 任何变化通过 on_change(kind, data) 通知上层（用于广播给 display / controller）。
"""

import copy
import json
import threading

LIST_ZONES = ("front", "back", "ex")
SINGLE_ZONES = ("field", "grave", "deck", "exdeck")


def empty_card(face_up=True, orientation="vertical"):
    return {
        "id": -1, "name": "", "atk": 0, "def": 0,
        "level": 0, "rank": 0, "attribute": "", "race": "",
        "arrows": [], "face_up": face_up, "orientation": orientation,
        "markers": [], "counters": [], "extra": {},
    }


def empty_player():
    return {
        "lp": 8000, "exdeck": None, "deck": None, "grave": None, "field": None,
        "front": [None] * 5, "back": [None] * 5, "ex": [None] * 2,
    }


def empty_battlefield():
    return {
        "phase": "draw", "turn_player": 0, "dice": None, "coin": None,
        "players": {"1": empty_player(), "2": empty_player()},
    }


def _cells(player_dict):
    for z in LIST_ZONES:
        for i in range(len(player_dict[z])):
            yield z, i
    for z in SINGLE_ZONES:
        yield z, None


def _eq(a, b):
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == \
           json.dumps(b, sort_keys=True, ensure_ascii=False)


class BattlefieldStore:
    def __init__(self, layout=None, on_change=None):
        self._lock = threading.RLock()
        self._bf = empty_battlefield()
        self._source = {}          # (player, zone, index) -> "manual" | "recog" | ""
        self._version = 0
        self.on_change = on_change  # callable(kind, data)

    # ---- 读取 -------------------------------------------------------------
    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._bf)

    @property
    def version(self):
        return self._version

    # ---- 写入 -------------------------------------------------------------
    def set_from_controller(self, bf):
        """整体替换战场；发生变化的格子标记为人工设置。"""
        with self._lock:
            mine = self._bf
            changed = False
            for pkey in ("1", "2"):
                src = bf.get("players", {}).get(pkey)
                if not isinstance(src, dict):
                    continue
                for z, i in _cells(mine["players"][pkey]):
                    new = _get_cell(src, z, i)
                    cur = _get_cell(mine["players"][pkey], z, i)
                    if not _eq(new, cur):
                        _set_cell(mine["players"][pkey], z, i, copy.deepcopy(new))
                        self._source[(pkey, z, i)] = "manual"
                        changed = True
            if bf.get("phase") is not None and bf.get("phase") != mine["phase"]:
                mine["phase"] = bf["phase"]
                changed = True
            if bf.get("turn_player") is not None and bf.get("turn_player") != mine["turn_player"]:
                mine["turn_player"] = bf["turn_player"]
                changed = True
            if "dice" in bf and not _eq(bf.get("dice"), mine.get("dice")):
                mine["dice"] = bf.get("dice")
                changed = True
            if "coin" in bf and not _eq(bf.get("coin"), mine.get("coin")):
                mine["coin"] = bf.get("coin")
                changed = True
            if changed:
                self._bump()
        if changed:
            self._emit("battlefield")

    def rebroadcast(self):
        """重新广播当前战场快照（状态不变），用于重新定位后刷新各端。"""
        self._emit("battlefield")

    def set_lp(self, player, lp):
        with self._lock:
            p = self._bf["players"].get(str(player))
            if p is None or p["lp"] == lp:
                return
            p["lp"] = lp
            self._bump()
        self._emit("lp", {"player": player, "lp": lp})

    def set_phase(self, phase_or_index):
        phase = phase_or_index if isinstance(phase_or_index, str) else _phase_by_index(phase_or_index)
        with self._lock:
            if phase is None or self._bf["phase"] == phase:
                return
            self._bf["phase"] = phase
            self._bump()
        self._emit("phase", {"phase": phase})

    def apply_recognition(self, player, cells):
        """
        cells: {(zone, index): card}  该玩家本帧识别到的全部卡片。
        只覆盖非 manual 的格子；未识别到的识别格会被清空。
        """ 
        pkey = str(player)
        changed = False
        with self._lock:
            pd = self._bf["players"].get(pkey)
            if pd is None:
                return
            for z, i in _cells(pd):
                key = (pkey, z, i)
                if self._source.get(key) == "manual":
                    continue
                new = cells.get((z, i))
                cur = _get_cell(pd, z, i)
                if not _eq(new, cur):
                    _set_cell(pd, z, i, copy.deepcopy(new))
                    self._source[key] = "recog" if new is not None else ""
                    changed = True
        if changed:
            self._bump()
            self._emit("battlefield")

    # ---- 内部 -------------------------------------------------------------
    def _bump(self):
        self._version += 1

    def _emit(self, kind, data=None):
        cb = self.on_change
        if cb is None:
            return
        payload = copy.deepcopy(self._bf) if kind == "battlefield" else data
        try:
            cb(kind, payload)
        except Exception as e:  # 广播失败不影响状态
            print(f"[state] on_change 出错: {e}")


class DeckStore:
    """
    保存各玩家已导入卡组的卡号（ydk passcode）。
    卡名识别时用其并集作为候选约束（借鉴 draw2 的 --deck-list 优化）：
    分类器 top-k 候选中只接受 id 落在已导入卡组里的那一个，从而抑制相近卡混淆。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._decks = {}          # "1"/"2" -> set[int]

    def set(self, player, ids):
        try:
            cleaned = {int(x) for x in (ids or [])}
        except (TypeError, ValueError):
            cleaned = set()
        with self._lock:
            self._decks[str(player)] = cleaned
        return len(cleaned)

    def clear(self, player=None):
        with self._lock:
            if player is None:
                self._decks.clear()
            else:
                self._decks.pop(str(player), None)

    def all_ids(self):
        """所有玩家卡号的并集（无卡组时返回空集合）。"""
        with self._lock:
            out = set()
            for s in self._decks.values():
                out |= s
            return out

    def summary(self):
        with self._lock:
            return {p: len(s) for p, s in self._decks.items()}


def _get_cell(pd, z, i):
    return pd[z][i] if i is not None else pd[z]


def _set_cell(pd, z, i, val):
    if i is not None:
        pd[z][i] = val
    else:
        pd[z] = val


_PHASE_KEYS = ["draw", "standby", "main1", "battle", "main2", "end"]


def _phase_by_index(idx):
    try:
        idx = int(idx)
        if 0 <= idx < len(_PHASE_KEYS):
            return _PHASE_KEYS[idx]
    except (TypeError, ValueError):
        pass
    return None
