/**
 * render.js
 * ---------------------------------------------------------------------------
 * 战场渲染。buildBoard 构建骨架，renderBoard 更新内容。
 * 卡牌用色块图片占位：背面=card_back.svg，未识别/占位=card_placeholder.svg，
 * 已知 id 时尝试加载 assets/cards/<id>.png（失败回退占位图）。
 */
import { zoneSize, ZONE_LABEL, getCell, isArrayZone } from "./state.js";
import { MARKER_TYPES, PHASES, labelOf, counterLabel } from "./protocol.js";

// 单格堆叠区域（垂直排列用）
const STACK_ZONES = ["exdeck", "deck", "grave", "field"];
// 数组区域（水平排列用）
const ROW_ZONES = ["front", "back", "ex"];

// ---- 攻击 / 被攻击 选中态（由「点击卡片 -> 操作面板」记录，用于棋盘高亮）----
let selection = { attackFrom: null, attackTo: null };

/**
 * 设置当前选中的攻击者 / 被攻击者，用于在棋盘上高亮。
 * @param {object} sel { attackFrom, attackTo }（每项为 {player, zone, index} 或 null）
 */
export function setSelection(sel) {
  selection = Object.assign({ attackFrom: null, attackTo: null }, sel || {});
}

function isSelected(sel, player, zone, index) {
  return !!sel && Number(sel.player) === player && sel.zone === zone && Number(sel.index) === index;
}

/**
 * 构建战场骨架
 * @param {HTMLElement} rootEl
 * @param {(player:number, zone:string, index:number)=>void} onCellClick
 */
export function buildBoard(rootEl, onCellClick) {
  rootEl.innerHTML = "";

  const p2 = buildSide(2, onCellClick, /*exFirst*/ false);
  const mid = buildMiddle();
  const p1 = buildSide(1, onCellClick, /*exFirst*/ true);

  rootEl.appendChild(p2);
  rootEl.appendChild(mid);
  rootEl.appendChild(p1);
}

function buildSide(player, onCellClick, exFirst) {
  const side = document.createElement("section");
  side.className = `side side-p${player}`;
  side.dataset.player = player;

  // 顶部信息条：玩家名 / LP / 按钮
  const head = document.createElement("div");
  head.className = "side-head";
  head.innerHTML = `
    <span class="side-name">PLAYER ${player}</span>
    <span class="side-lp">LP <b id="lp-${player}">8000</b></span>
    <span class="side-turn" id="turn-${player}">TURN</span>
  `;
  side.appendChild(head);

  const grid = document.createElement("div");
  grid.className = "board-grid";

  const rowBack = makeRow();
  const rowFront = makeRow();
  const rowEx = makeRow();
  rowEx.classList.add("row-ex");

  // 角堆叠的左右位置：两方朝向相反，上方玩家镜像
  //   下方 p1(exFirst)：field/exdeck 在左，grave/deck 在右
  //   上方 p2：         grave/deck  在左，field/exdeck 在右
  const frontLeft = exFirst ? "field" : "grave";
  const frontRight = exFirst ? "grave" : "field";
  const backLeft = exFirst ? "exdeck" : "deck";
  const backRight = exFirst ? "deck" : "exdeck";

  // back 行：卡组/额外卡组 | back1..5 | 额外卡组/卡组
  rowBack.appendChild(makeStack(player, backLeft, onCellClick));
  rowBack.appendChild(makeRowCells(player, "back", onCellClick));
  rowBack.appendChild(makeStack(player, backRight, onCellClick));

  // front 行：场地/墓地 | front1..5 | 墓地/场地
  rowFront.appendChild(makeStack(player, frontLeft, onCellClick));
  rowFront.appendChild(makeRowCells(player, "front", onCellClick));
  rowFront.appendChild(makeStack(player, frontRight, onCellClick));

  // ex 行：占满 7 列，额外怪兽区落在第 3、5 列（对齐 front 的第 2、4 格）
  rowEx.appendChild(makeExCells(player, onCellClick, exFirst));

  // 由靠近中场向外：ex 行 → front 行 → back 行
  if (exFirst) {
    grid.appendChild(rowEx);
    grid.appendChild(rowFront);
    grid.appendChild(rowBack);
  } else {
    grid.appendChild(rowBack);
    grid.appendChild(rowFront);
    grid.appendChild(rowEx);
  }

  side.appendChild(grid);
  return side;
}

function makeRow() {
  const row = document.createElement("div");
  row.className = "row";
  return row;
}

// 单格堆叠区域（exdeck/deck/grave/field）
function makeStack(player, zone, onCellClick) {
  const wrap = document.createElement("div");
  wrap.className = "zone stack";
  wrap.dataset.zone = zone;
  wrap.appendChild(makeCell(player, zone, 0, onCellClick));
  return wrap;
}

// 数组区域（front/back/ex）
function makeRowCells(player, zone, onCellClick) {
  const wrap = document.createElement("div");
  wrap.className = `zone cells cells-${zone}`;
  wrap.dataset.zone = zone;
  const n = zoneSize(zone);
  for (let i = 0; i < n; i++) {
    wrap.appendChild(makeCell(player, zone, i, onCellClick));
  }
  return wrap;
}

// 额外怪兽区：每方 2 格，占满 7 列、放在第 3、5 列（对齐 front 的第 2、4 格）
function makeExCells(player, onCellClick, exFirst) {
  const wrap = document.createElement("div");
  wrap.className = "zone cells cells-ex";
  wrap.dataset.zone = "ex";
  // 下方 p1：左=ex1、右=ex2；上方 p2 镜像
  const leftEx = exFirst ? 0 : 1;
  const rightEx = exFirst ? 1 : 0;
  [null, null, leftEx, null, rightEx, null, null].forEach((idx) => {
    if (idx === null) {
      const ghost = document.createElement("div");
      ghost.className = "cell cell-ghost";
      wrap.appendChild(ghost);
    } else {
      wrap.appendChild(makeCell(player, "ex", idx, onCellClick));
    }
  });
  return wrap;
}

function makeCell(player, zone, index, onCellClick) {
  const cell = document.createElement("div");
  cell.className = "cell";
  cell.dataset.player = player;
  cell.dataset.zone = zone;
  cell.dataset.index = index;
  cell.innerHTML = `<span class="cell-zone">${ZONE_LABEL[zone] || zone}${index > 0 || zoneSize(zone) > 1 ? index + 1 : ""}</span>`;
  cell.addEventListener("click", () => {
    if (onCellClick) onCellClick(player, zone, index);
  });
  return cell;
}

function buildMiddle() {
  const mid = document.createElement("div");
  mid.className = "mid";
  mid.innerHTML = `
    <div class="mid-phase">
      <span class="mid-label">PHASE</span>
      <b id="phase-name">抽卡</b>
    </div>
    <div class="mid-info">
      <span class="mid-label">TURN</span>
      <b id="turn-name">P1</b>
    </div>
    <div class="mid-info">
      <span class="mid-label">DICE</span>
      <b id="dice-name">-</b>
    </div>
    <div class="mid-info">
      <span class="mid-label">COIN</span>
      <b id="coin-name">-</b>
    </div>
  `;
  return mid;
}

/**
 * 用战场数据刷新整个战场
 * @param {object} bf
 */
export function renderBoard(bf) {
  document.querySelectorAll(".cell").forEach((cell) => {
    const player = Number(cell.dataset.player);
    const zone = cell.dataset.zone;
    const index = Number(cell.dataset.index);
    const card = getCell(bf, player, zone, index);
    renderCell(cell, card);
    cell.classList.toggle("sel-attack-from", isSelected(selection.attackFrom, player, zone, index));
    cell.classList.toggle("sel-attack-to", isSelected(selection.attackTo, player, zone, index));
  });

  // HUD
  for (const p of [1, 2]) {
    const lpEl = document.getElementById(`lp-${p}`);
    if (lpEl) lpEl.textContent = bf.players[String(p)].lp;
    const turnEl = document.getElementById(`turn-${p}`);
    if (turnEl) turnEl.classList.toggle("active", bf.turn_player === p);
  }
  const phaseEl = document.getElementById("phase-name");
  if (phaseEl) phaseEl.textContent = labelOf(PHASES, bf.phase);
  const turnName = document.getElementById("turn-name");
  if (turnName) turnName.textContent = bf.turn_player ? `P${bf.turn_player}` : "-";
  const diceName = document.getElementById("dice-name");
  if (diceName) diceName.textContent = bf.dice ? `${bf.dice.value}` : "-";
  const coinName = document.getElementById("coin-name");
  if (coinName) coinName.textContent = bf.coin ? (Number(bf.coin.value) === 1 ? "正" : "反") : "-";
}

function renderCell(cell, card) {
  cell.classList.toggle("empty", !card);
  cell.querySelector(".cell-inner")?.remove();
  if (!card) return;

  const inner = document.createElement("div");
  inner.className = "cell-inner";

  // 卡图
  const img = document.createElement("img");
  img.className = "card-img";
  img.alt = card.name || (card.id >= 0 ? String(card.id) : "card");
  img.draggable = false;
  img.src = cardImageSrc(card);
  img.onerror = () => {
    img.onerror = null;
    img.src = "assets/card_placeholder.svg";
  };
  if (card.orientation === "horizontal") inner.classList.add("horizontal");
  inner.appendChild(img);

  // 名称/编号
  const name = document.createElement("span");
  name.className = "cell-name";
  name.textContent = displayName(card);
  inner.appendChild(name);

  // 标记（可多个）
  if (card.markers && card.markers.length) {
    const mk = document.createElement("div");
    mk.className = "cell-markers";
    card.markers.forEach((key) => {
      const def = MARKER_TYPES.find((m) => m.key === key);
      if (!def) return;
      const mi = document.createElement("img");
      mi.src = def.img;
      mi.title = def.label;
      mi.alt = def.label;
      mk.appendChild(mi);
    });
    inner.appendChild(mk);
  }

  // 指示物（可多个种类）
  if (card.counters && card.counters.length) {
    const total = card.counters.reduce((s, c) => s + (Number(c.count) || 0), 0);
    const badge = document.createElement("span");
    badge.className = "cell-counters";
    badge.textContent = total;
    badge.title = card.counters.map((c) => `${counterLabel(c.kind)}:${c.count}`).join("  ");
    inner.appendChild(badge);
  }

  // 正/背面角标
  if (!card.face_up) {
    const tag = document.createElement("span");
    tag.className = "cell-facetag";
    tag.textContent = "SET";
    inner.appendChild(tag);
  }

  cell.appendChild(inner);
}

function displayName(card) {
  if (card.name) return card.name;
  if (!card.face_up) return "";
  if (card.id >= 0) return `#${card.id}`;
  return "未知";
}

function cardImageSrc(card) {
  if (!card.face_up) return "assets/card_back.svg";
  if (card.id >= 0) return `assets/cards/${card.id}.jpg`;
  return "assets/card_placeholder.svg";
}
