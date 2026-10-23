/**
 * app.js
 * ---------------------------------------------------------------------------
 * 控制端页面主逻辑：初始化、渲染、与 center 通信、按钮/弹窗事件绑定。
 */
import { MSG } from "./protocol.js";
import {
  makeBattlefield, normalizeBattlefield, normalizeCard,
  getCell, setCell, cloneBattlefield, zoneSize, ZONE_LABEL,
} from "./state.js";
import { buildBoard, renderBoard, setSelection, setSwapped } from "./render.js";
import { initModals, openModal, closeModal, el, openConfigPanel, openLpPanel, openPhasePanel, openSummonPanel, openAttackPanel, openRelatePanel, openBgmPanel, openSePanel, openDicePanel, openCoinPanel, openImportPanel, openCardPanel, openCardActionPanel, openRollResultPanel, openResetPanel, rollTargetLabel } from "./panels.js";
import { getConfig, saveConfig, uploadYdk } from "./api.js";
import { CenterClient } from "./center.js";

// ---- 全局状态 ----
let battle = makeBattlefield();
let config = { center_ip: "127.0.0.1", center_port: 4560, dice_coin_choose_player: false };
const center = new CenterClient();

// 攻击 / 被攻击：点击卡片后记录，二者都可被后续选择覆盖
let attacker = null; // { player, zone, index }
let target = null;   // { player, zone, index }

// 仅前端视觉：是否交换 P1 / P2 的上下显示位置（不影响发送数据里的玩家编号）
let swapped = false;

// display 当前是否静音（由 center 广播同步）
let muted = false;

// 已导入卡组：{ "1": [id...], "2": [id...] }（供卡号「选择」弹窗使用）
const decks = { "1": [], "2": [] };

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

/**
 * center 通常与 controller 部署在同一台机器上：
 * 把默认占位地址（空 / 127.0.0.1 / localhost）解析为“打开本页所用的主机”，
 * 这样用局域网 IP 打开 controller 时，会自动连到同一 IP 上的 center。
 */
function resolveCenterIp(ip) {
  if (!ip || ip === "127.0.0.1" || ip === "localhost") {
    const host = location.hostname || ip;
    return host.includes(":") && !host.startsWith("[") ? `[${host}]` : host;
  }
  return ip;
}

function connectCenter() {
  center.connect(resolveCenterIp(config.center_ip), config.center_port);
}

// ---------------------------------------------------------------------------
// 与 center 通信
// ---------------------------------------------------------------------------
function sendMsg(type, payload = {}) {
  center.send({ type, ...payload });
}

function showDuelGate() {
  const gate = document.getElementById("duel-gate");
  if (gate) gate.classList.remove("hidden");
}

function hideDuelGate() {
  const gate = document.getElementById("duel-gate");
  if (gate) gate.classList.add("hidden");
}

// 「是否开始」：开始则隐藏决斗界面、结束则显示（未开始时 center 不做识别）
function applyStarted(started) {
  battle.started = !!started;
  if (battle.started) hideDuelGate();
  else { showDuelGate(); applyResetLocal(); }
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
      applyStarted(battle.started);
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
    case MSG.MUTE: {
      muted = !!data.mute;
      break;
    }
    case MSG.RESET: {
      applyStarted(false);
      break;
    }
    case MSG.START: {
      applyStarted(true);
      break;
    }
    default:
      console.log("[center] recv:", data);
  }
}

function updateStatus(status, url) {
  let label = "未连接";
  if (status === "connected") {
    label = "已连接";
    // 断线重连后补发已上传的卡组，供 center 限制卡名识别范围。
    for (const p of ["1", "2"]) {
      if (decks[p] && decks[p].length) {
        sendMsg(MSG.IMPORT_YDK, { player: Number(p), ids: decks[p] });
      }
    }
  } else if (status === "connecting") label = "连接中…";

  // 顶栏与「决斗」界面各有一份连接指示
  for (const [dotId, txtId] of [["conn-dot", "conn-status"], ["gate-conn-dot", "gate-conn-status"]]) {
    const dot = document.getElementById(dotId);
    const txt = document.getElementById(txtId);
    if (dot) dot.className = "conn-dot " + status;
    if (txt) { txt.textContent = label; txt.title = url || ""; }
  }
}

// ---------------------------------------------------------------------------
// 编辑动作（本地修改 + 下发）
// ---------------------------------------------------------------------------
function onCellClick(player, zone, index) {
  const card = getCell(battle, player, zone, index);
  openCardActionPanel(
    { player, zone, index, card },
    {
      onDetail: () => openCardDetailPanel(player, zone, index),
      onDirect: () => selectDirectAttack(player, zone, index),
      onAttack: () => selectAttacker(player, zone, index),
      onDefend: () => selectTarget(player, zone, index),
      // 破坏：只下发消息，不修改本地卡牌
      onDestroy: () => sendMsg(MSG.DESTROY, {
        player: Number(player), cell_type: zone, cell_index: Number(index),
      }),
    },
    { attacker, target }
  );
}

// 卡牌详情 / 编辑面板（原点击卡片直接打开的面板）
function openCardDetailPanel(player, zone, index) {
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
      getDeckIds: () => decks,
    }
  );
}

// 选择「直接攻击」：该卡直接攻击对方玩家，立即推送 on_attack_anim（is_direct=true），不记录攻击者
function selectDirectAttack(player, zone, index) {
  const from = { player: Number(player), zone, index: Number(index) };
  sendMsg(MSG.ATTACK, {
    ...cellPayload(from, "from"),
    to_player: 0,
    to_cell_type: "",
    to_cell_index: 0,
    is_direct: true,
  });
  toast(`直接攻击：P${from.player} ${cellLabel(from)} → 对方玩家`, "success");
  attacker = null;
  target = null;
  syncSelection();
}

// 选择「攻击」：记录攻击者（可被后续选择覆盖）
function selectAttacker(player, zone, index) {
  attacker = { player: Number(player), zone, index: Number(index) };
  syncSelection();
  toast(`攻击者：P${player} ${cellLabel(attacker)}`, "success");
}

// 选择「被攻击」：记录被攻击者；若已选攻击者，则推送 on_attack_anim 给 center，
// 发送后清空攻击者/被攻击者，等待下次选择
function selectTarget(player, zone, index) {
  target = { player: Number(player), zone, index: Number(index) };
  syncSelection();
  if (!attacker) {
    toast(`被攻击者：P${player} ${cellLabel(target)}（尚未选择攻击者）`, "info");
    return;
  }
  sendMsg(MSG.ATTACK, {
    ...cellPayload(attacker, "from"),
    ...cellPayload(target, "to"),
    is_direct: false,
  });
  toast(`攻击：P${attacker.player} ${cellLabel(attacker)} → P${target.player} ${cellLabel(target)}`, "success");
  attacker = null;
  target = null;
  syncSelection();
}

// 刷新棋盘上的攻击/被攻击高亮
function syncSelection() {
  setSelection({ attackFrom: attacker, attackTo: target });
  renderBoard(battle);
}

// 把 {player, zone, index} 转成协议字段（from_/to_ 前缀）
function cellPayload(cell, p) {
  return {
    [`${p}_player`]: cell.player,
    [`${p}_cell_type`]: cell.zone,
    [`${p}_cell_index`]: cell.index,
  };
}

function cellLabel(cell) {
  const n = zoneSize(cell.zone) > 1 ? cell.index + 1 : "";
  return `${ZONE_LABEL[cell.zone] || cell.zone}${n}`;
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

  on("btn-duel", () => {
    applyStarted(true);
    sendMsg(MSG.START);
  });
  on("btn-config", openConfig);
  on("gate-btn-config", openConfig);
  on("btn-reconnect", connectCenter);

  // 竖屏：点「操作」展开/收起顶部操作按钮（横屏由 CSS 直接显示，按钮不出现）
  const menuBtn = document.getElementById("btn-menu");
  const topbar = document.querySelector(".topbar");
  if (menuBtn && topbar) {
    menuBtn.addEventListener("click", () => topbar.classList.toggle("menu-open"));
  }

  on("btn-phase", () => openPhasePanel(battle.phase, setPhase));
  on("btn-summon", () => openSummonPanel((t) => sendMsg(MSG.SUMMON, { summon_type: t })));
  on("btn-attack", () => openAttackPanel((a) => sendMsg(MSG.ATTACK, a)));
  on("btn-relate", () => openRelatePanel((r) => sendMsg(MSG.RELATE, r)));
  on("btn-bgm", () => openBgmPanel((name) => sendMsg(MSG.BGM, { bgm_filename: name })));
  on("btn-se", () => openSePanel((name) => sendMsg(MSG.SE, { se_filename: name })));

  on("btn-dice", () => {
    if (config.dice_coin_choose_player) {
      openDicePanel(commitDice);
    } else {
      commitDice({ player: 0, value: 1 + Math.floor(Math.random() * 6) });
    }
  });
  on("btn-coin", () => {
    if (config.dice_coin_choose_player) {
      openCoinPanel(commitCoin);
    } else {
      commitCoin({ player: 0, value: Math.random() < 0.5 ? 1 : 0 });
    }
  });
  on("btn-reset", () => openResetPanel(resetGame));

  // LP 变更：点击 LP 数字（事件委托，交换位置重建棋盘后依然有效）
  const boardEl = document.getElementById("board");
  if (boardEl) {
    boardEl.addEventListener("click", (e) => {
      const lpEl = e.target.closest("[id^='lp-']");
      if (!lpEl) return;
      const p = Number(lpEl.id.slice(3));
      if (!battle.players[String(p)]) return;
      openLpPanel(p, battle.players[String(p)].lp, (lp) => setLp(p, lp));
    });
  }
}

// 打开配置面板（含「导入卡组」快捷操作，用于赛前上传卡组）
function openConfig() {
  openConfigPanel({ ...config, muted }, saveAndReconnect, {
    onImport: (p) => openImportPanel(p, (file) => importYdk(p, file)),
    onSwap: toggleSwap,
    onGuide: setGuide,
    onMute: setMuted,
    onLight: setLight,
  });
}

function setLight(on) {
  sendMsg(MSG.LIGHT, { on: !!on });
  toast(on ? "已发送：开启照明" : "已发送：关闭照明", "success");
}

function commitDice({ player, value }) {
  battle.dice = { player, value, ts: Date.now() };
  renderBoard(battle);
  sendMsg(MSG.DICE, { player, value });
  openRollResultPanel("骰子结果", "// DICE", String(value),
    `点数 ${value} · ${rollTargetLabel(player)}`);
}

function commitCoin({ player, value }) {
  battle.coin = { player, value, ts: Date.now() };
  renderBoard(battle);
  sendMsg(MSG.COIN, { player, value });
  openRollResultPanel("硬币结果", "// COIN", value === 1 ? "正" : "反",
    `${value === 1 ? "正面 (heads)" : "反面 (tails)"} · ${rollTargetLabel(player)}`);
}

function applyResetLocal() {
  battle = makeBattlefield();
  attacker = null;
  target = null;
  setSelection({ attackFrom: null, attackTo: null });
  renderBoard(battle);
}

function resetGame() {
  applyStarted(false);
  sendMsg(MSG.RESET);
}

function toggleSwap() {
  swapped = !swapped;
  setSwapped(swapped);
  renderBoard(battle);
  toast(swapped ? "已交换玩家显示位置（仅显示）" : "已恢复默认显示位置");
}

function setGuide(show) {
  sendMsg(MSG.GUIDE, { show });
  toast(show ? "已显示定位" : "已隐藏定位", "success");
}

function setMuted(value) {
  muted = !!value;
  sendMsg(MSG.MUTE, { mute: muted });
  toast(muted ? "已静音" : "已取消静音", "success");
}

async function saveAndReconnect(cfg) {
  const prev = config;
  config = cfg;
  try {
    const res = await saveConfig(cfg);
    if (res && res.config) config = res.config;
    toast("配置已保存", "success");
  } catch (e) {
    toast("配置保存失败", "danger");
  }
  if (prev.center_ip !== config.center_ip
    || Number(prev.center_port) !== Number(config.center_port)) {
    connectCenter();
  }
}

async function importYdk(player, file) {
  try {
    const r = await uploadYdk(player, file);
    if (!r.ok) { toast(r.error || "ydk 解析失败", "danger"); return; }
    // 记录去重后的卡号，供卡号「选择」弹窗使用
    decks[String(player)] = [...new Set(r.ids.map(Number))];
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
