# -*- coding: utf-8 -*-
"""
recognize.py
摄像头识别：读取视频流 → YOLO(OBB) 检测卡牌 → 透视矫正/正反面/朝向 → 卡名识别
→ 由卡牌中心坐标映射到 (玩家, 格子) → 写入 BattlefieldStore。

参考 test/videotest.py（实时）与 test/yolotest.py（图片）：
- OBB 结果同时给 corners 与 xywhr，朝向/尺寸用 xywhr 判断（更稳）。
- 使用 OBB 跟踪 id + 卡名缓存（TTL）避免每帧重跑 ONNX。
- 卡名识别用 onnxruntime，优先 CUDA( GPU ) 提供者。
- YOLO 推理走 GPU（device 可配置）。

依赖 cv2 / numpy / ultralytics / onnxruntime，均为延迟导入，未装时仅预览。
"""

import json
import os
import threading
import time

import gridmap
from state import empty_card


def _log(*a):
    print("[recog]", *a)


class Models:
    """共享的模型容器；加载一次，所有摄像头复用。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.cv2 = None
        self.np = None
        self.front = None
        self.back = None
        self.sess = None
        self.iname = None
        self.oname = None
        self.names = None
        self.providers = []
        self.ok = False          # 完整识别链路可用
        self.ready = False       # 至少 cv2 可用（能取流预览）
        self.reason = "未加载"
        self._frame = None
        self._cache = {}         # tid -> info | None
        self._seen = {}          # tid -> 最近出现时间

    def load(self):
        try:
            import cv2
            import numpy as np
        except Exception as e:  # noqa: BLE001
            self.reason = f"缺少 cv2/numpy，识别与预览不可用: {e}"
            _log(self.reason)
            return False
        self.cv2, self.np = cv2, np
        self.ready = True

        m = self.cfg["models"]
        missing = [k for k, p in m.items() if not os.path.exists(p)]
        if missing:
            self.reason = f"模型文件缺失（仅预览）: {', '.join(missing)}"
            _log(self.reason)
            return False
        try:
            from ultralytics import YOLO
            import onnxruntime as ort
        except Exception as e:  # noqa: BLE001
            self.reason = f"缺少 ultralytics/onnxruntime（仅预览）: {e}"
            _log(self.reason)
            return False
        try:
            self.front = YOLO(m["yolo_front"])
            self.back = YOLO(m["yolo_back"])
            # onnxruntime 优先 GPU（CUDA），否则回退 CPU
            avail = ort.get_available_providers()
            self.providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider")
                              if p in avail]
            self.sess = ort.InferenceSession(m["name_onnx"], providers=self.providers or None)
            self.iname = self.sess.get_inputs()[0].name
            self.oname = self.sess.get_outputs()[0].name
            with open(m["names_json"], "r", encoding="utf-8") as f:
                self.names = json.load(f)
        except Exception as e:  # noqa: BLE001
            self.reason = f"模型加载失败（仅预览）: {e}"
            _log(self.reason)
            return False
        self.ok = True
        used = self.sess.get_providers()
        self.reason = f"已加载（卡名库 {len(self.names)} 张，ONNX: {'/'.join(used)}）"
        _log(self.reason)
        return True

    # ---- 卡名识别（带缓存）------------------------------------------------
    def _card_name(self, card_bgr, thr):
        cv2, np = self.cv2, self.np
        if card_bgr is None or card_bgr.size == 0:
            return None
        rgb = cv2.cvtColor(card_bgr, cv2.COLOR_BGR2RGB)
        im = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_CUBIC)
        x = ((im.astype(np.float32) / 255.0 - 0.5) / 0.5).transpose(2, 0, 1)[None]
        logits = self.sess.run([self.oname], {self.iname: x})[0][0]
        e = np.exp(logits - logits.max())
        prob = e / e.sum()
        idx = int(np.argmax(prob))
        if float(prob[idx]) < thr:
            return None
        info = self.names[str(idx)]
        return {"card_id": info.get("card_id", -1), "name": info.get("EN", ""),
                "score": float(prob[idx])}

    def name_for(self, tid, crop, thr):
        if tid in self._cache:
            return self._cache[tid]
        info = self._card_name(crop, thr)
        self._cache[tid] = info
        return info

    # ---- 透视矫正 + 正反面 + 朝向（参考 videotest.py）---------------------
    def analyze_card(self, corners, xywhr):
        cv2, np = self.cv2, self.np
        w_real = float(xywhr[2])
        h_real = float(xywhr[3])
        if w_real < 30 or h_real < 30:
            return None, "未知", None
        if w_real > h_real:
            orientation = "横向"
            W, H = int(round(h_real)), int(round(w_real))
        else:
            orientation = "纵向"
            W, H = int(round(w_real)), int(round(h_real))

        pts = corners.astype(np.float32)
        order = np.argsort(pts[:, 1])
        top2 = pts[order[:2]]
        bot2 = pts[order[2:]]
        top2 = top2[np.argsort(top2[:, 0])]
        bot2 = bot2[np.argsort(bot2[:, 0])]
        ordered = np.array([top2[0], top2[1], bot2[1], bot2[0]], dtype=np.float32)

        dst = np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], dtype=np.float32)
        M = cv2.getPerspectiveTransform(ordered, dst)
        crop = cv2.warpPerspective(self._frame, M, (W, H))
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        h_ch, _s, v_ch = cv2.split(hsv)
        cx0, cx1 = int(W * 0.25), int(W * 0.75)
        cy0, cy1 = int(H * 0.25), int(H * 0.75)
        center_v = v_ch[cy0:cy1, cx0:cx1]
        dark = float(np.sum(center_v < 60) / center_v.size) if center_v.size else 0
        mean_v = float(np.mean(center_v)) if center_v.size else 0
        h_var = float(np.var(h_ch))
        if dark > 0.6 and mean_v < 80:
            return "反面", orientation, crop
        if h_var > 500:
            return "正面", orientation, crop
        return None, orientation, crop

    # ---- 检测 -------------------------------------------------------------
    def detect(self, frame):
        self._frame = frame
        cfg = self.cfg["detect"]
        np = self.np
        out = []
        front = self._infer(self.front, frame, cfg["front_conf"], 0)
        back = self._infer(self.back, frame, cfg["back_conf"], 100000)
        now = time.time()
        for d in front:
            side, ori, crop = self.analyze_card(d["corners"], d["xywhr"])
            if side != "正面":
                continue
            self._seen[d["tid"]] = now
            info = self.name_for(d["tid"], crop, cfg["name_thr"])
            out.append(self._make(d, "front", ori, info, np))
        for d in back:
            side, ori, crop = self.analyze_card(d["corners"], d["xywhr"])
            if side != "反面":
                continue
            if any(abs(o["cx"] - d["cx"]) < 30 and abs(o["cy"] - d["cy"]) < 30 for o in out):
                continue
            self._seen[d["tid"]] = now
            out.append(self._make(d, "back", ori, None, np))
        # 清理过期缓存
        ttl = float(cfg.get("name_cache_ttl", 3.0))
        for tid in [t for t, ts in self._seen.items() if now - ts > ttl]:
            self._seen.pop(tid, None)
            self._cache.pop(tid, None)
        return out

    def _infer(self, model, frame, conf, id_offset):
        cfg = self.cfg["detect"]
        device = cfg.get("device", 0)
        use_track = bool(cfg.get("track", True))
        try:
            if use_track:
                r = model.track(frame, persist=True, conf=conf, device=device, verbose=False)[0]
            else:
                r = model.predict(frame, conf=conf, device=device, verbose=False)[0]
        except Exception as e:  # noqa: BLE001
            _log(f"推理失败: {e}")
            return []
        if r.obb is None or len(r.obb) == 0:
            return []
        pts = r.obb.xyxyxyxy.cpu().numpy()
        xywhr = r.obb.xywhr.cpu().numpy()
        if r.obb.id is not None:
            ids = r.obb.id.cpu().numpy().astype(int)
        else:
            ids = self.np.arange(len(pts)) + id_offset
        return [{"corners": c.copy(), "xywhr": b.copy(), "tid": int(t)}
                for c, b, t in zip(pts, xywhr, ids)]

    def _make(self, d, side, ori, info, np):
        cx, cy = float(d["xywhr"][0]), float(d["xywhr"][1])
        return {
            "corners": d["corners"], "xywhr": d["xywhr"],
            "cx": cx, "cy": cy, "side": side,
            "orientation": "vertical" if ori == "纵向" else "horizontal",
            "info": info,
        }

    def device_info(self):
        return {"providers": self.providers, "device": self.cfg["detect"].get("device", 0)}


class CameraWorker(threading.Thread):
    def __init__(self, cam_id, url, players, store, models, cfg, frames):
        super().__init__(name=f"cam-{cam_id}", daemon=True)
        self.cam_id = cam_id
        self.url = url
        self.players = players           # 该摄像头负责的玩家列表 [1] 或 [1,2]
        self.store = store
        self.models = models
        self.cfg = cfg
        self.frames = frames            # {cam_id: jpeg bytes}
        self._stop = threading.Event()
        self.connected = False
        self.fps = 0.0
        self.detections = 0
        self.error = ""

    def stop(self):
        self._stop.set()

    def _open(self):
        cv2 = self.models.cv2
        src = int(self.url) if str(self.url).isdigit() else self.url
        cap = cv2.VideoCapture(src)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:  # noqa: BLE001
            pass
        return cap

    def run(self):
        cv2 = self.models.cv2
        if cv2 is None:
            self.error = self.models.reason
            return
        cap = self._open()
        if not cap.isOpened():
            self.error = f"无法打开视频源: {self.url}"
            _log(self.error)
            return
        self.connected = True
        self.error = ""
        interval = max(0.05, float(self.cfg["detect"]["interval"]))
        last_detect = 0.0
        count = 0
        t0 = time.time()
        retries = 0
        while not self._stop.is_set():
            ret, frame = cap.read()
            if not ret or frame is None:
                self.connected = False
                retries += 1
                cap.release()
                if retries > 5:
                    self.error = "连续读帧失败，已停止重连"
                    break
                time.sleep(0.5)
                cap = self._open()
                self.connected = cap.isOpened()
                continue
            retries = 0
            self.connected = True
            now = time.time()
            count += 1
            if now - t0 >= 2.0:
                self.fps = count / (now - t0)
                count = 0
                t0 = now
            result = None
            if self.models.ok and self.cfg.get("recognition_enabled", True) and \
                    now - last_detect >= interval:
                last_detect = now
                try:
                    result = self._process(frame)
                except Exception as e:  # noqa: BLE001
                    self.error = f"识别异常: {e}"
                    _log(self.error)
            self._publish(frame, result)
        cap.release()
        self.connected = False

    def _process(self, frame):
        dets = self.models.detect(frame)
        by_player = {p: {} for p in self.players}
        layout = self.cfg["layout"]
        mode = self.cfg["mode"]
        p1_side = self.cfg["single"]["player1_side"]
        swap = self.cfg["dual"].get("swap", False)
        h, w = frame.shape[:2]
        for d in dets:
            nx, ny = d["cx"] / w, d["cy"] / h
            hit = None
            for p in self.players:
                area = gridmap.player_area(mode, p1_side, p, swap)
                cell = gridmap.map_point(layout, nx, ny, area)
                if cell:
                    hit = (p, cell)
                    break
            if not hit:
                continue
            p, (zone, index) = hit
            card = empty_card(
                face_up=(d["side"] == "front"), orientation=d["orientation"])
            if d["info"]:
                card["id"] = d["info"]["card_id"]
                card["name"] = d["info"]["name"]
                card["extra"] = {"score": d["info"]["score"]}
            by_player[p][(zone, index)] = card
        for p in self.players:
            self.store.apply_recognition(p, by_player[p])
        self.detections = sum(len(v) for v in by_player.values())
        return dets

    def _publish(self, frame, dets):
        cv2 = self.models.cv2
        img = frame.copy()
        if self.cfg.get("_overlay", True):
            self._draw_layout(img)
        if dets:
            for d in dets:
                color = (0, 255, 0) if d["side"] == "front" else (255, 0, 0)
                pts = d["corners"].astype(int).reshape((-1, 1, 2))
                cv2.polylines(img, [pts], True, color, 2)
                label = d["side"]
                if d["info"]:
                    label = f"{d['info']['name'][:24]} {d['info']['score']:.2f}"
                cv2.putText(img, label, (int(d["cx"]) - 40, int(d["cy"])),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if ok:
            self.frames[self.cam_id] = buf.tobytes()

    def _draw_layout(self, img):
        cv2 = self.models.cv2
        h, w = img.shape[:2]
        layout = self.cfg["layout"]
        mode = self.cfg["mode"]
        p1_side = self.cfg["single"]["player1_side"]
        swap = self.cfg["dual"].get("swap", False)
        for p in self.players:
            x0, y0, x1, y1 = gridmap.player_area(mode, p1_side, p, swap)
            ax, ay = x0 * w, y0 * h
            aw, ah = (x1 - x0) * w, (y1 - y0) * h
            for zone, index, rx, ry, rw, rh in gridmap.layout_overlay(layout):
                px = int(ax + rx * aw)
                py = int(ay + ry * ah)
                pw = int(rw * aw)
                ph = int(rh * ah)
                cv2.rectangle(img, (px, py), (px + pw, py + ph), (0, 255, 255), 1)
                cv2.putText(img, f"{zone}{index if index is not None else ''}",
                            (px + 2, py + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

    def status(self):
        return {
            "id": self.cam_id, "url": self.url, "players": self.players,
            "connected": self.connected, "fps": round(self.fps, 1),
            "detections": self.detections, "error": self.error,
        }


class RecognitionManager:
    def __init__(self, store, cfg):
        self.store = store
        self.cfg = cfg
        self.models = Models(cfg)
        self.workers = []
        self.frames = {}
        self._lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._load_and_run, name="model-load", daemon=True).start()

    def _load_and_run(self):
        self.models.load()
        self.restart()

    def restart(self):
        with self._lock:
            for w in self.workers:
                w.stop()
            self.workers = []
            mode = self.cfg["mode"]
            if mode == "dual":
                swap = bool(self.cfg["dual"].get("swap", False))
                for i, cam in enumerate(self.cfg["dual"]["cameras"]):
                    player = cam.get("player", i + 1)
                    if swap:
                        player = 2 if str(player) == "1" else 1
                    self.workers.append(CameraWorker(
                        f"cam{i+1}", cam["url"], [player], self.store, self.models, self.cfg, self.frames))
            else:
                self.workers.append(CameraWorker(
                    "single", self.cfg["single"]["url"], [1, 2], self.store, self.models, self.cfg, self.frames))
            for w in self.workers:
                w.start()

    def stop(self):
        with self._lock:
            for w in self.workers:
                w.stop()
            self.workers = []

    def get_frame(self, cam_id):
        return self.frames.get(cam_id)

    def status(self):
        with self._lock:
            workers = [w.status() for w in self.workers]
        st = {
            "mode": self.cfg["mode"],
            "models_ok": self.models.ok,
            "models_ready": self.models.ready,
            "models_reason": self.models.reason,
            "cameras": workers,
        }
        st.update(self.models.device_info())
        return st
