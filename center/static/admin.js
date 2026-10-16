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
  set("d_url2", cams[1] ? cams[1].url : "");
  set("d_p2", cams[1] ? cams[1].player : 2);
  set("front_conf", cfg.detect.front_conf);
  set("back_conf", cfg.detect.back_conf);
  set("name_thr", cfg.detect.name_thr);
  set("interval", cfg.detect.interval);
  set("min_side", cfg.detect.min_side);
  set("device", cfg.detect.device);
  set("track", cfg.detect.track);
  set("name_cache_ttl", cfg.detect.name_cache_ttl);
  set("m_yolo_front", cfg.models.yolo_front);
  set("m_yolo_back", cfg.models.yolo_back);
  set("m_name_onnx", cfg.models.name_onnx);
  set("m_names_json", cfg.models.names_json);
  renderPreviews(cfg.mode);
  ensureCalibUI(cfg);
  window.__cfg = cfg;
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
    { url: f.d_url1.value.trim(), player: parseInt(f.d_p1.value, 10) },
    { url: f.d_url2.value.trim(), player: parseInt(f.d_p2.value, 10) },
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

async function poll() {
  try {
    const st = await (await fetch("/api/status")).json();
    const cams = (st.cameras || [])
      .map((c) => `${c.id}:${c.connected ? "在线" : "离线"} ${c.fps}fps 识别${c.detections}${c.error ? " " + c.error : ""}`)
      .join(" | ");
    statusLine.textContent =
      `WS客户端 ${st.ws_clients} | 模型 ${st.models_ok ? "就绪" : "未就绪"}（${st.models_reason}）`
      + ` | 设备 ${st.device} (${(st.providers || []).join("/") || "-"})`
      + (cams ? ` | ${cams}` : "");
    statusJson.textContent = JSON.stringify(st, null, 2);
  } catch (err) {
    statusLine.textContent = "状态获取失败：" + err.message;
  }
}

loadConfig().then(poll);
setInterval(poll, 1500);

/* ---------------- 定位 / 校准 ---------------- */

const calibPreviews = document.getElementById("calib-previews");
const calibMsg = document.getElementById("calib-msg");

const calib = { key: null, targets: [] };

// 计算需要框选的「摄像头 → 玩家」目标（与后端 worker 的玩家归属一致）
function calibTargets(cfg) {
  if (cfg.mode === "dual") {
    const swap = !!cfg.dual.swap;
    const cams = cfg.dual.cameras || [];
    const out = [];
    for (let i = 0; i < cams.length; i++) {
      let p = cams[i].player || (i + 1);
      if (swap) p = String(p) === "1" ? 2 : 1;
      out.push({ cam_id: `cam${i + 1}`, players: [String(p)] });
    }
    return out.length ? out : [{ cam_id: "cam1", players: ["1"] }];
  }
  return [{ cam_id: "single", players: ["1", "2"] }];
}

function ensureCalibUI(cfg) {
  const targets = calibTargets(cfg);
  const key = JSON.stringify(targets.map((t) => [t.cam_id, t.players]));
  if (key === calib.key) return;   // 结构未变则不重建，保留已有框选
  calib.key = key;
  calib.targets = targets;
  calibPreviews.innerHTML = "";
  for (const t of targets) {
    t.boxes = t.players.map(() => null);
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
    cap.textContent = `${t.cam_id} → 玩家 ${t.players.join(", ")}（需框选 ${t.players.length} 个区域）`;
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
    if (rect.x1 - rect.x0 < 10 || rect.y1 - rect.y0 < 10) { drawBoxes(t); return; }
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

async function runCalibration() {
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
  for (const t of calib.targets) t.boxes = t.players.map(() => null);
  for (const t of calib.targets) drawBoxes(t);
  calibMsg.textContent = "";
});
document.getElementById("guide-show").addEventListener("click", () => sendGuide(true));
document.getElementById("guide-hide").addEventListener("click", () => sendGuide(false));