# -*- coding: utf-8 -*-
"""
blacklist.py
卡名识别黑名单：命中这些 card_id 的卡名不按卡面处理。
文件默认在 center/blacklist.txt，一行一个 card_id，# 开头为注释。
"""

import os


DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blacklist.txt")


class BlacklistStore:
    def __init__(self, path=None):
        self.path = path or DEFAULT_PATH
        self._ids = set()
        self.load()

    @staticmethod
    def _parse(text):
        ids = set()
        for line in str(text or "").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            for part in line.replace(",", " ").split():
                try:
                    ids.add(int(part))
                except ValueError:
                    continue
        return ids

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._ids = self._parse(f.read())
        except OSError:
            self._ids = set()
        return self.ids()

    def _write(self, ids):
        lines = ["# 卡名识别黑名单：一行一个 card_id，# 开头为注释"]
        lines += [str(i) for i in sorted(ids)]
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def save(self, text):
        ids = self._parse(text)
        self._write(ids)
        self._ids = ids
        return self.ids()

    def text(self):
        return "\n".join(str(i) for i in self.ids())

    def ids(self):
        return sorted(self._ids)

    def __contains__(self, card_id):
        try:
            return int(card_id) in self._ids
        except (TypeError, ValueError):
            return False

    def __len__(self):
        return len(self._ids)
