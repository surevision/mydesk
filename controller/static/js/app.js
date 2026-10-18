/**
 * app.js
 * ---------------------------------------------------------------------------
 * 控制端页面主逻辑：初始化、渲染、与 center 通信、按钮/弹窗事件绑定。
 */
import { MSG } from "./protocol.js";
import {
  makeBattlefield, normalizeBattlefield, normalizeCard,
  getCell, setCell, cloneBattlefield,
} from "./state.js";
import { buildBoard, renderBoard } from "./render.js";
import { initModals, openModal, closeModal, el, openConfigPanel, openLpPanel, openPhasePanel, openSummonPanel, openDestroyPanel, openAttackPanel, openRelatePanel, openBgmPanel, openSePanel, openDicePanel, openCoinPanel, openImportPanel, openCardPanel } from "./panels.js";
import { getConfig, saveConfig, uploadYdk } from "./api.js";
import { CenterClient } from "./center.js";

// ---- 全局状态 ----
let battle = makeBattlefield();
let config = { center_ip: "127.0.0.1", center_port: 8765 };
const center = new CenterClient();

// ---------------------------------------------------------------------------
// 启动
// ---------------------------------------------------------------------------
window.addEventListener("DOMContentLoaded", init);

async function init() {
  initModals(document.getElementById("modal-root"));
  buildBoard(document.getElementById("board"), onCellClick);
  renderBoard(battle);
  wireButtons();

  center.onStatus(updateStatus);
  center.onMessage(onCenterMessage);

  try {
    config = await getConfig();
  } catch (e) {
    toast("读取配置失败，使用默认地址", "danger");
  }
  connectCenter();
}

function connectCenter() {
  center.connect(config.center_ip, config.center_port);
}

// ---------------------------------------------------------------------------
// 与 center 通信
// ---------------------------------------------------------------------------
function sendMsg(type, payload = {}) {
  center.send({ type, ...payload });
}

/** 发送完整战场快照 */
function pushBattlefield() {
  center.send({ type: MSG.BATTLEFIELD, battlefield: JSON.stringify(cloneBattlefield(battle)) });
}

function onCenterMessage(data) {
  if (!data || !data.type) return;
  switch (data.type) {
    case MSG.BATTLEFIELD: {
      let bf = data.battlefield;
      if (typeof bf === "string") {
        try { bf = JSON.parse(bf); } catch (e) { console.warn("battlefield JSON 解析失败", e); return; }
      }
      battle = normalizeBattlefield(bf);
      renderBoard(battle);
      break;
    }
    case MSG.LP: {
      const p = String(Number(data.player));
      if (battle.players[p] && data.lp !== undefined) {
        battle.players[p].lp = Number(data.lp) || 0;
        renderBoard(battle);
      }
      break;
    }
    case MSG.PHASE: {
      if (typeof data.phase_index === "string") {
        battle.phase = data.phase_index;
        renderBoard(battle);
      }
      break;
    }
    default:
      console.log("[center] recv:", data);
  }
}

function updateStatus(status, url) {
  const dot = document.getElementById("conn-dot");
  const txt = document.getElementById("conn-status");
  if (!dot || !txt) return;
  dot.className = "conn-dot " + status;
  if (status === "connected") txt.textContent = `已连接 ${url}`;
  else if (status === "connecting") txt.textContent = `连接中 ${url} ...`;
  else txt.textContent = "未连接";
}

// ---------------------------------------------------------------------------
// 编辑动作（本地修改 + 下发）
// ---------------------------------------------------------------------------
function onCellClick(player, zone, index) {
  const card = getCell(battle, player, zone, index);
  const readonly = zone === "deck"; // deck 不支持手动设置
  openCardPanel(
    { player, zone, index, card, readonly },
    {
      onSave: (cardData) => {
        if (readonly) { toast("deck 区域不支持手动设置", "danger"); return; }
        setCard(player, zone, index, cardData);
      },
      onClear: () => clearCell(player, zone, index),
    }
  );
}

function setCard(player, zone, index, cardData) {
  setCell(battle, Number(player), zone, Number(index), normalizeCard(cardData));
  renderBoard(battle);
  pushBattlefield();
}

function clearCell(player, zone, index) {
  setCell(battle, Number(player), zone, Number(index), null);
  renderBoard(battle);
  pushBattlefield();
}

function setLp(player, lp) {
  battle.players[String(player)].lp = lp;
  renderBoard(battle);
  sendMsg(MSG.LP, { player, lp });
  pushBattlefield();
}

function setPhase(phase) {
  battle.phase = phase;
  renderBoard(battle);
  sendMsg(MSG.PHASE, { phase_index: phase });
  pushBattlefield();
}

// ---------------------------------------------------------------------------
// 按钮绑定
// ---------------------------------------------------------------------------
function wireButtons() {
  const on = (id, fn) => {
    const node = document.getElementById(id);
    if (node) node.addEventListener("click", fn);
  };

  on("btn-config", () => openConfigPanel(config, saveAndReconnect));
  on("btn-reconnect", connectCenter);

  on("btn-import-1", () => openImportPanel(1, (file) => importYdk(1, file)));
  on("btn-import-2", () => openImportPanel(2, (file) => importYdk(2, file)));

  on("btn-phase", () => openPhasePanel(battle.phase, setPhase));
  on("btn-summon", () => openSummonPanel((t) => sendMsg(MSG.SUMMON, { summon_type: t })));
  on("btn-destroy", () => openDestroyPanel((c) => sendMsg(MSG.DESTROY, c)));
  on("btn-attack", () => openAttackPanel((a) => sendMsg(MSG.ATTACK, a)));
  on("btn-relate", () => openRelatePanel((r) => sendMsg(MSG.RELATE, r)));
  on("btn-bgm", () => openBgmPanel((name) => sendMsg(MSG.BGM, { bgm_filename: name })));
  on("btn-se", () => openSePanel((name) => sendMsg(MSG.SE, { se_filename: name })));
  on("btn-dice", () => openDicePanel((d) => {
    battle.dice = { player: d.player, value: d.value, ts: Date.now() };
    renderBoard(battle);
    sendMsg(MSG.DICE, d);
  }));
  on("btn-coin", () => openCoinPanel((c) => {
    battle.coin = { player: c.player, value: c.value, ts: Date.now() };
    renderBoard(battle);
    sendMsg(MSG.COIN, c);
  }));

  // LP 变更：点击 LP 数字
  for (const p of [1, 2]) {
    const lpEl = document.getElementById(`lp-${p}`);
    if (lpEl) {
      lpEl.style.cursor = "pointer";
      lpEl.addEventListener("click", () => openLpPanel(p, battle.players[String(p)].lp, (lp) => setLp(p, lp)));
    }
  }
}

async function saveAndReconnect(cfg) {
  config = cfg;
  try {
    const res = await saveConfig(cfg);
    if (res && res.config) config = res.config;
    toast("配置已保存", "success");
  } catch (e) {
    toast("配置保存失败", "danger");
  }
  connectCenter();
}

async function importYdk(player, file) {
  try {
    const r = await uploadYdk(player, file);
    if (!r.ok) { toast(r.error || "ydk 解析失败", "danger"); return; }
    toast(`P${player} 导入 ${r.ids.length} 张卡`, "success");
    sendMsg(MSG.IMPORT_YDK, { player, ids: r.ids, main: r.main, extra: r.extra, side: r.side });
  } catch (e) {
    toast("ydk 上传失败", "danger");
  }
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------
function toast(msg, kind = "info") {
  const root = document.getElementById("toast-root");
  if (!root) return;
  const cls = kind === "success" ? "cy-toast--success" : kind === "danger" ? "cy-toast--danger" : "";
  const node = el("div", { class: `cy-toast ${cls}` }, [
    el("span", { class: "cy-toast__ic", text: kind === "success" ? "✓" : kind === "danger" ? "!" : "i" }),
    el("span", { text: msg }),
  ]);
  root.appendChild(node);
  setTimeout(() => node.remove(), 2600);
}
