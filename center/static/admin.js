/* center 管理页面逻辑：读取/保存配置、预览、轮询状态 */
"use strict";

const form = document.getElementById("config-form");
const msg = document.getElementById("save-msg");
const previews = document.getElementById("previews");
const statusLine = document.getElementById("status-line");
const statusJson = document.getElementById("status-json");

let camIds = [];

function camIdsFor(mode) {
  return mode === "dual" ? ["cam1", "cam2"] : ["single"];
}

function renderPreviews(mode) {
  const ids = camIdsFor(mode);
  if (ids.join() === camIds.join()) return;
  camIds = ids;
  previews.innerHTML = "";
  for (const id of ids) {
    const box = document.createElement("div");
    box.className = "preview";
    const img = document.createElement("img");
    img.alt = id;
    img.src = `/frame/${id}?t=${Date.now()}`;
    const cap = document.createElement("div");
    cap.className = "cap";
    cap.textContent = id;
    box.append(img, cap);
    previews.append(box);
  }
}

async function loadConfig() {
  const cfg = await (await fetch("/api/config")).json();
  const set = (name, value) => {
    const el = form.elements[name];
    if (!el) return;
    if (el.type === "checkbox") el.checked = !!value;
    else el.value = value;
  };
  set("mode", cfg.mode);
  set("recognition_enabled", cfg.recognition_enabled);
  set("s_url", cfg.single.url);
  set("s_side", cfg.single.player1_side);
  set("d_swap", cfg.dual.swap);
  const cams = cfg.dual.cameras || [];
  set("d_url1", cams[0] ? cams[0].url : "");
  set("d_p1", cams[0] ? cams[0].player : 1);
  set("d_o1", cams[0] ? (cams[0].orientation || "horizontal") : "horizontal");
  set("d_url2", cams[1] ? cams[1].url : "");
  set("d_p2", cams[1] ? cams[1].player : 2);
  set("d_o2", cams[1] ? (cams[1].orientation || "horizontal") : "horizontal");
  set("front_conf", cfg.detect.front_conf);
  set("back_conf", cfg.detect.back_conf);
  set("name_thr", cfg.detect.name_thr);
  set("interval", cfg.detect.interval);
  set("min_side", cfg.detect.min_side);
  set("device", cfg.detect.device);
  set("track", cfg.detect.track);
  set("name_cache_ttl", cfg.detect.name_cache_ttl);
  set("cell_hold", cfg.detect.cell_hold);
  set("marker_drop_radius", cfg.detect.marker_drop_radius);
  set("m_yolo_front", cfg.models.yolo_front);
  set("m_yolo_back", cfg.models.yolo_back);
  set("m_name_onnx", cfg.models.name_onnx);
  set("m_names_json", cfg.models.names_json);
  renderPreviews(cfg.mode);
  ensureCalibUI(cfg);
  window.__cfg = cfg;
  restoreCalib();
  return cfg;
}

function collect() {
  const f = form.elements;
  const cfg = JSON.parse(JSON.stringify(window.__cfg || {}));
  cfg.mode = f.mode.value;
  cfg.recognition_enabled = f.recognition_enabled.checked;
  cfg.single = cfg.single || {};
  cfg.single.url = f.s_url.value.trim();
  cfg.single.player1_side = f.s_side.value;
  cfg.dual = cfg.dual || {};
  cfg.dual.swap = f.d_swap.checked;
  cfg.dual.cameras = [
    {
      url: f.d_url1.value.trim(),
      player: parseInt(f.d_p1.value, 10),
      orientation: f.d_o1.value,
    },
    {
      url: f.d_url2.value.trim(),
      player: parseInt(f.d_p2.value, 10),
      orientation: f.d_o2.value,
    },
  ];
  cfg.detect = cfg.detect || {};
  cfg.detect.front_conf = parseFloat(f.front_conf.value);
  cfg.detect.back_conf = parseFloat(f.back_conf.value);
  cfg.detect.name_thr = parseFloat(f.name_thr.value);
  cfg.detect.interval = parseFloat(f.interval.value);
  cfg.detect.min_side = parseInt(f.min_side.value, 10);
  const dev = f.device.value.trim();
  cfg.detect.device = dev === "cpu" ? "cpu" : (dev === "" ? 0 : parseInt(dev, 10));
  cfg.detect.track = f.track.checked;
  cfg.detect.name_cache_ttl = parseFloat(f.name_cache_ttl.value);
  cfg.detect.cell_hold = parseFloat(f.cell_hold.value);
  cfg.detect.marker_drop_radius = parseInt(f.marker_drop_radius.value, 10);
  cfg.models = cfg.models || {};
  cfg.models.yolo_front = f.m_yolo_front.value.trim();
  cfg.models.yolo_back = f.m_yolo_back.value.trim();
  cfg.models.name_onnx = f.m_name_onnx.value.trim();
  cfg.models.names_json = f.m_names_json.value.trim();
  return cfg;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.textContent = "保存中…";
  try {
    const r = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collect()),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.statusText);
    msg.textContent = "已保存";
    await loadConfig();
  } catch (err) {
    msg.textContent = "保存失败：" + err.message;
  }
});

const blacklistText = document.getElementById("blacklist-text");
const blacklistMsg = document.getElementById("blacklist-msg");

async function loadBlacklist() {
  try {
    const data = await (await fetch("/api/blacklist")).json();
    blacklistText.value = data.text || "";
    blacklistMsg.textContent = `当前 ${data.ids ? data.ids.length : 0} 个`;
  } catch (err) {
    blacklistMsg.textContent = "读取失败：" + err.message;
  }
}

document.getElementById("blacklist-save").addEventListener("click", async () => {
  blacklistMsg.textContent = "保存中…";
  try {
    const r = await fetch("/api/blacklist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: blacklistText.value }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.statusText);
    blacklistText.value = data.text || "";
    blacklistMsg.textContent = `已保存（${data.ids.length} 个）`;
  } catch (err) {
    blacklistMsg.textContent = "保存失败：" + err.message;
  }
});

async function poll() {
  try {
    const st = await (await fetch("/api/status")).json();
    const cams = (st.cameras || [])
      .map((c) => `${c.id}:${c.connected ? "在线" : "离线"} ${c.fps}fps 识别${c.detections}${c.located === false ? " 未定位" : ""}${c.error ? " " + c.error : ""}`)
      .join(" | ");
    statusLine.textContent =
      `WS客户端 ${st.ws_clients} | 模型 ${st.models_ok ? "就绪" : "未就绪"}（${st.models_reason}）`
      + ` | 游戏 ${st.started ? "进行中" : "未开始（暂停识别）"}`
      + ` | 设备 ${st.device}${st.device_note ? "（" + st.device_note + "）" : ""} (${((st.active && st.active.length ? st.active : st.providers) || []).join("/") || "-"})`
      + (cams ? ` | ${cams}` : "");
    statusJson.textContent = JSON.stringify(st, null, 2);
  } catch (err) {
    statusLine.textContent = "状态获取失败：" + err.message;
  }
}

loadConfig().then(poll);
loadBlacklist();
setInterval(poll, 1500);

/* ---------------- 采集端 monitor ---------------- */

const monitorFpsEl = document.getElementById("monitor-fps");
const monitorFpsMsg = document.getElementById("monitor-fps-msg");
const monitorResEl = document.getElementById("monitor-res");
const monitorResMsg = document.getElementById("monitor-res-msg");

document.getElementById("monitor-fps-send").addEventListener("click", async () => {
  const fps = parseInt(monitorFpsEl.value, 10);
  if (!(fps >= 1)) { monitorFpsMsg.textContent = "帧率需 ≥ 1 的整数"; return; }
  monitorFpsMsg.textContent = "下发中…";
  try {
    const r = await fetch("/api/monitor_fps", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fps }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.statusText);
    if (data.ok) {
      monitorFpsMsg.textContent = `已下发 ${data.fps}fps → ${Object.keys(data.results).join(", ")}`;
    } else {
      const errs = Object.entries(data.errors || {}).map(([k, v]) => `${k}: ${v}`);
      const oks = Object.keys(data.results || {});
      monitorFpsMsg.textContent =
        `部分成功${oks.length ? "（" + oks.join(", ") + "）" : ""}；失败：${errs.join("；")}`;
    }
  } catch (err) {
    monitorFpsMsg.textContent = "失败：" + err.message;
  }
});

async function loadMonitorStatus() {
  try {
    const r = await fetch("/api/monitor_status");
    const data = await r.json();
    const cams = [];
    for (const list of Object.values(data.results || {})) {
      if (Array.isArray(list)) cams.push(...list);
    }
    if (!cams.length) {
      const errs = Object.values(data.errors || {}).join("；");
      if (errs) monitorResMsg.textContent = "读取失败：" + errs;
      return;
    }
    const first = cams[0];
    if (!first.width || !first.height) {
      monitorResMsg.textContent = "采集端未返回分辨率";
      return;
    }
    const value = `${first.width}x${first.height}`;
    if (![...monitorResEl.options].some((o) => o.value === value)) {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = `${first.width}×${first.height}（当前）`;
      monitorResEl.appendChild(opt);
    }
    monitorResEl.value = value;
    const parts = cams.map((c, i) => {
      const set = c.width && c.height ? `${c.width}×${c.height}` : "?";
      const act = c.frame_width && c.frame_height
        ? `（实际 ${c.frame_width}×${c.frame_height}）` : "";
      return `#${i} ${set}${act}`;
    });
    monitorResMsg.textContent = "当前 " + parts.join("；");
  } catch (err) {
    monitorResMsg.textContent = "读取失败：" + err.message;
  }
}

document.getElementById("monitor-res-send").addEventListener("click", async () => {
  const [width, height] = monitorResEl.value.split("x").map(Number);
  if (!(width > 0 && height > 0)) {
    monitorResMsg.textContent = "分辨率无效";
    return;
  }
  monitorResMsg.textContent = "下发中…";
  try {
    const r = await fetch("/api/monitor_resolution", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ width, height }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.statusText);
    if (data.ok) {
      monitorResMsg.textContent =
        `已下发 ${data.width}×${data.height} → ${Object.keys(data.results).join(", ")}`;
      setTimeout(loadMonitorStatus, 1500);
    } else {
      const errs = Object.entries(data.errors || {}).map(([k, v]) => `${k}: ${v}`);
      const oks = Object.keys(data.results || {});
      monitorResMsg.textContent =
        `部分成功${oks.length ? "（" + oks.join(", ") + "）" : ""}；失败：${errs.join("；")}`;
    }
  } catch (err) {
    monitorResMsg.textContent = "失败：" + err.message;
  }
});

loadMonitorStatus();

/* ---------------- 定位 / 校准 ---------------- */

const calibPreviews = document.getElementById("calib-previews");
const calibMsg = document.getElementById("calib-msg");
const calibHint = document.getElementById("calib-hint");
const calibModeEl = document.getElementById("calib-mode");

const calib = { key: null, targets: [] };
// 顺时针：左上 → 右上 → 右下 → 左下
const CORNERS = ["tl", "tr", "br", "bl"];
const CORNER_MARK = { tl: "①", tr: "②", br: "③", bl: "④" };
let calibRestored = false;

// 把后端已保存的校准恢复成框选/标记（页面刷新、center 重启后不用重框）
async function restoreCalib() {
  if (calibRestored || !calib.targets.length) return;
  let data;
  try {
    data = await (await fetch("/api/calib")).json();
  } catch (err) {
    return;
  }
  calibRestored = true;
  const mode = (window.__cfg || {}).mode;
  const list = (data.calibrations || []).filter((it) => !mode || it.mode === mode);
  if (!list.length) return;
  for (const t of calib.targets) {
    const mine = list.filter((it) => it.cam_id === t.cam_id);
    for (const it of mine) {
      const pi = t.players.indexOf(String(it.player));
      if (pi < 0) continue;
      if (it.roi && it.roi.length === 4 && !t.boxes[pi]) {
        t.boxes[pi] = { x0: it.roi[0], y0: it.roi[1], x1: it.roi[2], y1: it.roi[3] };
      }
    }
    // 手动标定：按 玩家 → 角 的顺序恢复成小方块，序号与后续点击一致
    for (const p of t.players) {
      const it = mine.find((x) => String(x.player) === p && x.source === "manual");
      if (!it || !it.corners) continue;
      for (const c of CORNERS) {
        if (t.marks.some((m) => m.player === p && m.corner === c)) continue;
        const pt = it.corners[c];
        if (!pt) continue;
        const r = 8;
        t.marks.push({
          player: p, corner: c,
          x0: pt[0] - r, y0: pt[1] - r, x1: pt[0] + r, y1: pt[1] + r,
          cx: pt[0], cy: pt[1],
        });
      }
    }
    drawBoxes(t);
  }
  calibMsg.textContent = "已恢复上次的框选/标定";
}

function isManual() { return calibModeEl.value === "manual"; }

function updateCalibHint() {
  calibHint.textContent = isManual()
    ? "手动标记：在每个玩家区域按【左上 → 右上 → 右下 → 左下】顺时针依次框选 4 个定位标识（小方格）。单摄像头共 8 个（P1 4 + P2 4），双摄像头每路 4 个。画面方向由上方双摄像头配置决定（横向 3×7 / 竖向 7×3）。"
    : "自动检测：在每路画面上拖拽框选玩家区域（单摄像头需框两次：player1、player2；双摄像头每路框一次），再由 center 自动找 4 个定位方块。画面方向由上方双摄像头配置决定（横向 3×7 / 竖向 7×3）。";
}

// 计算需要框选的「摄像头 → 玩家」目标（与后端 worker 的玩家归属一致）
function calibTargets(cfg) {
  if (cfg.mode === "dual") {
    const swap = !!cfg.dual.swap;
    const cams = cfg.dual.cameras || [];
    const out = [];
    for (let i = 0; i < cams.length; i++) {
      let p = cams[i].player || (i + 1);
      if (swap) p = String(p) === "1" ? 2 : 1;
      out.push({
        cam_id: `cam${i + 1}`,
        players: [String(p)],
        orientation: cams[i].orientation || "horizontal",
      });
    }
    return out.length
      ? out
      : [{ cam_id: "cam1", players: ["1"], orientation: "horizontal" }];
  }
  return [{ cam_id: "single", players: ["1", "2"], orientation: "vertical" }];
}

function ensureCalibUI(cfg) {
  const targets = calibTargets(cfg);
  const key = JSON.stringify(targets.map((t) => [t.cam_id, t.players, t.orientation]));
  if (key === calib.key) return;   // 结构未变则不重建，保留已有框选
  calib.key = key;
  calib.targets = targets;
  calibRestored = false;           // 重建后重新从后端恢复框选
  calibPreviews.innerHTML = "";
  for (const t of targets) {
    t.boxes = t.players.map(() => null);
    t.marks = [];
    const box = document.createElement("div");
    box.className = "preview calib-preview";
    const wrap = document.createElement("div");
    wrap.className = "calib-canvas-wrap";
    const img = document.createElement("img");
    img.alt = t.cam_id;
    img.src = `/raw/${t.cam_id}?t=${Date.now()}`;
    const canvas = document.createElement("canvas");
    wrap.append(img, canvas);
    const cap = document.createElement("div");
    cap.className = "cap";
    const grid = t.orientation === "vertical" ? "竖向 7×3" : "横向 3×7";
    cap.textContent = `${t.cam_id} → 玩家 ${t.players.join(", ")}（${grid}，需框选 ${t.players.length} 个区域）`;
    box.append(wrap, cap);
    calibPreviews.append(box);
    t.img = img;
    t.canvas = canvas;
    t.ctx = canvas.getContext("2d");
    setupDraw(t);
    t.syncTimer = setInterval(() => {
      if (!img.naturalWidth) return;
      if (canvas.width !== img.naturalWidth || canvas.height !== img.naturalHeight) {
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
      }
      drawBoxes(t);
    }, 400);
  }
}

function canvasPos(t, e) {
  const r = t.canvas.getBoundingClientRect();
  const sx = t.canvas.width / (r.width || 1);
  const sy = t.canvas.height / (r.height || 1);
  return { x: Math.round((e.clientX - r.left) * sx), y: Math.round((e.clientY - r.top) * sy) };
}

function drawBoxes(t, preview) {
  const ctx = t.ctx;
  if (!ctx || !t.canvas.width) return;
  ctx.clearRect(0, 0, t.canvas.width, t.canvas.height);
  const lw = Math.max(2, t.canvas.width / 640);
  ctx.lineWidth = lw;
  ctx.font = `${Math.max(14, Math.round(t.canvas.width / 48))}px sans-serif`;
  t.boxes.forEach((b, i) => {
    if (!b) return;
    ctx.strokeStyle = "#22c55e";
    ctx.strokeRect(b.x0, b.y0, b.x1 - b.x0, b.y1 - b.y0);
    ctx.fillStyle = "#22c55e";
    ctx.fillText(`P${t.players[i]}`, b.x0 + 6, b.y0 + 22);
  });

  // 手动定位标识：框选的小方格 + 中心点
  if (t.marks && t.marks.length) {
    t.marks.forEach((m) => {
      ctx.strokeStyle = "#22d3ee";
      ctx.strokeRect(m.x0, m.y0, m.x1 - m.x0, m.y1 - m.y0);
      ctx.fillStyle = "#22d3ee";
      ctx.fillText(`P${m.player}${CORNER_MARK[m.corner]}`,
                   m.x0 + 2, Math.max(14, m.y0 - 4));
      ctx.beginPath();
      ctx.arc(m.cx, m.cy, 3, 0, Math.PI * 2);
      ctx.fill();
    });
    // 每位玩家的 4 个中心按 tl→tr→br→bl 连成四边形
    for (const p of t.players) {
      const pts = CORNERS
        .map((c) => t.marks.find((m) => m.player === p && m.corner === c))
        .filter(Boolean);
      if (pts.length >= 2) {
        ctx.strokeStyle = "#f472b6";
        ctx.beginPath();
        pts.forEach((m, i) => (i ? ctx.lineTo(m.cx, m.cy) : ctx.moveTo(m.cx, m.cy)));
        if (pts.length === 4) ctx.closePath();
        ctx.stroke();
      }
    }
  }

  if (preview) {
    const x0 = Math.min(preview.x0, preview.x1);
    const y0 = Math.min(preview.y0, preview.y1);
    ctx.strokeStyle = "#facc15";
    ctx.setLineDash([8, 6]);
    ctx.strokeRect(x0, y0, Math.abs(preview.x1 - preview.x0), Math.abs(preview.y1 - preview.y0));
    ctx.setLineDash([]);
  }
}

function setupDraw(t) {
  let start = null;
  t.canvas.addEventListener("mousedown", (e) => { start = canvasPos(t, e); });
  t.canvas.addEventListener("mousemove", (e) => {
    if (!start) return;
    const cur = canvasPos(t, e);
    drawBoxes(t, { x0: start.x, y0: start.y, x1: cur.x, y1: cur.y });
  });
  const finish = (e) => {
    if (!start) return;
    const cur = canvasPos(t, e);
    const s = start;
    start = null;
    const rect = {
      x0: Math.min(s.x, cur.x), y0: Math.min(s.y, cur.y),
      x1: Math.max(s.x, cur.x), y1: Math.max(s.y, cur.y),
    };
    const minSide = isManual() ? 4 : 10;
    if (rect.x1 - rect.x0 < minSide || rect.y1 - rect.y0 < minSide) { drawBoxes(t); return; }

    if (isManual()) {
      addManualMark(t, rect);
      return;
    }
    const slot = t.boxes.findIndex((b) => b === null);
    if (slot >= 0) t.boxes[slot] = rect;
    else { t.boxes.shift(); t.boxes.push(rect); }
    drawBoxes(t);
    const total = t.boxes.filter(Boolean).length;
    calibMsg.textContent = `${t.cam_id}: 已框选 ${total}/${t.players.length}`;
  };
  t.canvas.addEventListener("mouseup", finish);
  t.canvas.addEventListener("mouseleave", (e) => { if (start) finish(e); });
}

function addManualMark(t, rect) {
  const total = t.players.length * 4;
  if (t.marks.length >= total) {
    calibMsg.textContent = `${t.cam_id}: 已标记 ${total} 个，如需重标请先「清除框选」`;
    drawBoxes(t);
    return;
  }
  const idx = t.marks.length;
  const player = t.players[Math.floor(idx / 4)];
  const corner = CORNERS[idx % 4];
  t.marks.push({
    player, corner,
    x0: rect.x0, y0: rect.y0, x1: rect.x1, y1: rect.y1,
    cx: (rect.x0 + rect.x1) / 2, cy: (rect.y0 + rect.y1) / 2,
  });
  drawBoxes(t);
  const n = t.marks.filter((m) => m.player === player).length;
  calibMsg.textContent = `${t.cam_id}: 标记 P${player} ${n}/4（${CORNER_MARK[corner]}）`;
}

async function runCalibration() {
  if (isManual()) return runManualCalibration();
  calibMsg.textContent = "定位中…";
  const lines = [];
  for (const t of calib.targets) {
    const rois = {};
    let missing = false;
    t.players.forEach((p, i) => {
      if (!t.boxes[i]) missing = true;
      else rois[p] = [t.boxes[i].x0, t.boxes[i].y0, t.boxes[i].x1, t.boxes[i].y1];
    });
    if (missing) { lines.push(`${t.cam_id}: 请先框选全部玩家区域`); continue; }
    try {
      const r = await fetch("/api/calibrate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cam_id: t.cam_id, rois }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || r.statusText);
      if (data.ok) lines.push(`${t.cam_id}: 定位成功`);
      else {
        for (const [p, m] of Object.entries(data.errors || {})) {
          lines.push(`${t.cam_id} 玩家${p}: ${m}`);
        }
      }
    } catch (err) {
      lines.push(`${t.cam_id}: ${err.message}`);
    }
  }
  calibMsg.textContent = lines.join("；");
  poll();
}

async function runManualCalibration() {
  calibMsg.textContent = "手动定位中…";
  const lines = [];
  for (const t of calib.targets) {
    for (const p of t.players) {
      const marks = CORNERS
        .map((c) => (t.marks || []).find((m) => m.player === p && m.corner === c))
        .filter(Boolean);
      if (marks.length !== 4) {
        lines.push(`${t.cam_id} 玩家${p}: 需顺时针框选 4 个定位标识（当前 ${marks.length}）`);
        continue;
      }
      const corners = marks.map((m) => [Math.round(m.cx), Math.round(m.cy)]);
      try {
        const r = await fetch("/api/calibrate_manual", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cam_id: t.cam_id, player: p, corners }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || r.statusText);
        lines.push(`${t.cam_id} 玩家${p}: 手动定位成功`);
      } catch (err) {
        lines.push(`${t.cam_id} 玩家${p}: ${err.message}`);
      }
    }
  }
  calibMsg.textContent = lines.join("；");
  poll();
}

async function sendGuide(show) {
  try {
    const r = await fetch("/api/guide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ show }),
    });
    const data = await r.json();
    calibMsg.textContent = show ? "已通知 display 显示定位方块" : "已通知 display 隐藏定位方块";
  } catch (err) {
    calibMsg.textContent = "发送失败：" + err.message;
  }
}

document.getElementById("calib-run").addEventListener("click", runCalibration);
document.getElementById("calib-clear").addEventListener("click", () => {
  for (const t of calib.targets) {
    t.boxes = t.players.map(() => null);
    t.marks = [];
    drawBoxes(t);
  }
  calibMsg.textContent = "";
});
document.getElementById("guide-show").addEventListener("click", () => sendGuide(true));
document.getElementById("guide-hide").addEventListener("click", () => sendGuide(false));

calibModeEl.addEventListener("change", () => {
  for (const t of calib.targets) {
    t.boxes = t.players.map(() => null);
    t.marks = [];
    drawBoxes(t);
  }
  calibMsg.textContent = "";
  updateCalibHint();
});
updateCalibHint();