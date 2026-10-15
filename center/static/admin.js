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
