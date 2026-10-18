/**
 * panels.js
 * ---------------------------------------------------------------------------
 * 弹窗（modal）基础设施 + 各类操作面板。
 * 每个面板都是「拼好表单 -> 回调返回数据」的形式，具体发送逻辑交给 app.js。
 */
import {
  PHASES, CELL_TYPES, SETTABLE_CELL_TYPES, DESTROY_CELL_TYPES,
  SUMMON_TYPES, ATTRIBUTES, RACES, MARKER_TYPES, ORIENTATIONS, COUNTER_TYPES, labelOf,
} from "./protocol.js";

let modalRoot = null;
export function initModals(el) {
  modalRoot = el;
}
export function closeModal() {
  if (modalRoot) modalRoot.innerHTML = "";
}

// ---------------------------------------------------------------------------
// 通用 DOM 小工具
// ---------------------------------------------------------------------------
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null) node.setAttribute(k, v);
  }
  (Array.isArray(children) ? children : [children]).forEach((c) => {
    if (c === null || c === undefined) return;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  });
  return node;
}

function fieldRow(label, control) {
  return el("label", { class: "form-row" }, [
    el("span", { class: "form-label", text: label }),
    control,
  ]);
}

function textInput(value = "", attrs = {}) {
  return el("input", Object.assign({ class: "cy-input", type: "text", value: String(value ?? "") }, attrs));
}
function numberInput(value = 0, attrs = {}) {
  return el("input", Object.assign({ class: "cy-input", type: "number", value: String(value ?? 0) }, attrs));
}
function select(options, value, attrs = {}) {
  const sel = el("select", attrs);
  options.forEach((o) => {
    const opt = el("option", { value: o.value });
    opt.textContent = o.label;
    if (String(o.value) === String(value)) opt.selected = true;
    sel.appendChild(opt);
  });
  return sel;
}
function optionsFromKeys(keys) {
  return keys.map((k) => ({ value: k, label: labelOf(CELL_TYPES, k) }));
}

// 坐标选择控件：player / cell_type / cell_index
function coordInput(defaults = {}, types = SETTABLE_CELL_TYPES) {
  const player = select([{ value: 1, label: "P1" }, { value: 2, label: "P2" }], defaults.player || 1);
  const type = select(optionsFromKeys(types), defaults.cell_type || types[0]);
  const index = numberInput(defaults.cell_index || 0, { min: 0, max: 9 });
  const indexRow = fieldRow("位置 index", index);

  const showIndex = () => {
    const t = type.value;
    indexRow.style.display = (t === "front" || t === "back" || t === "ex") ? "" : "none";
  };
  type.addEventListener("change", showIndex);
  showIndex();

  const wrap = el("div", { class: "coord" }, [
    fieldRow("玩家", player),
    fieldRow("区域", type),
    indexRow,
  ]);
  return {
    el: wrap,
    get: () => ({
      player: Number(player.value),
      cell_type: type.value,
      cell_index: Number(index.value) || 0,
    }),
  };
}

// ---------------------------------------------------------------------------
// Modal 基础
// ---------------------------------------------------------------------------
export function openModal({ title, badge, width, body, buttons = [] }) {
  closeModal();
  const mask = el("div", { class: "cy-modal-mask" });
  const closeBtn = el("div", { class: "cy-modal__close", text: "✕", onclick: closeModal });

  const bodyEl = el("div", { class: "cy-panel__bd" });
  if (typeof body === "string") bodyEl.innerHTML = body;
  else if (body) bodyEl.appendChild(body);

  if (buttons.length) {
    const foot = el("div", { class: "modal-foot" }, buttons.map((b) =>
      el("button", {
        class: `cy-btn ${b.class || ""}`,
        text: b.label,
        onclick: () => b.onClick && b.onClick(),
      })
    ));
    bodyEl.appendChild(foot);
  }

  const panel = el("div", { class: "cy-panel" }, [
    el("span", { class: "cy-bracket tl" }),
    el("span", { class: "cy-bracket tr" }),
    el("span", { class: "cy-bracket bl" }),
    el("span", { class: "cy-bracket br" }),
    el("div", { class: "cy-panel__hd", html: `${title || ""}${badge ? ` <span class="k">${badge}</span>` : ""}` }),
    bodyEl,
  ]);

  const modal = el("div", { class: "cy-modal" }, [closeBtn, panel]);
  if (width) modal.style.width = width;
  mask.appendChild(modal);
  mask.addEventListener("click", (e) => { if (e.target === mask) closeModal(); });
  modalRoot.appendChild(mask);
  return { mask, body: bodyEl, close: closeModal };
}

// ---------------------------------------------------------------------------
// 基础信息表单（卡牌详情用）
// ---------------------------------------------------------------------------
function attributeControl(value) {
  const datalist = el("datalist", { id: "attr-list" }, ATTRIBUTES.map((a) => el("option", { value: a })));
  const input = textInput(value || "", { list: "attr-list", placeholder: "光/暗/地..." });
  const wrap = el("div", {}, [datalist, input]);
  wrap._get = () => input.value;
  return wrap;
}
function raceControl(value) {
  const datalist = el("datalist", { id: "race-list" }, RACES.map((r) => el("option", { value: r })));
  const input = textInput(value || "", { list: "race-list", placeholder: "龙族/魔法师族..." });
  const wrap = el("div", {}, [datalist, input]);
  wrap._get = () => input.value;
  return wrap;
}

/**
 * 卡牌详情 / 编辑面板。
 * @param {object} info { player, zone, index, card (或 null) }
 * @param {object} cb { onSave(card, {setPlaceholder}), onClear(), onToggleFace(), onMarkers(card) }
 */
export function openCardPanel(info, cb) {
  const { player, zone, index, card } = info;
  const c = card || { id: -1, name: "", atk: 0, def: 0, level: 0, rank: 0, attribute: "", race: "", arrows: [], face_up: true, orientation: "vertical", markers: [], counters: [], extra: {} };

  const idIn = numberInput(c.id);
  const nameIn = textInput(c.name, { placeholder: "卡名（后续可按名搜索 cdb）" });
  const atkIn = numberInput(c.atk);
  const defIn = numberInput(c.def);
  const levelIn = numberInput(c.level, { min: 0, max: 13 });
  const rankIn = numberInput(c.rank, { min: 0, max: 13 });
  const attrCtl = attributeControl(c.attribute);
  const raceCtl = raceControl(c.race);
  const arrowsIn = textInput(Array.isArray(c.arrows) ? c.arrows.join(",") : "", { placeholder: "（功能暂不做，留空）", disabled: "true" });
  const faceIn = el("input", { type: "checkbox" });
  faceIn.checked = !!c.face_up;
  const orientIn = select(ORIENTATIONS.map((o) => ({ value: o.key, label: o.label })), c.orientation);

  // 标记
  const markerBoxes = {};
  const markersWrap = el("div", { class: "marker-select" }, MARKER_TYPES.map((m) => {
    const cbx = el("input", { type: "checkbox" });
    cbx.checked = c.markers.includes(m.key);
    markerBoxes[m.key] = cbx;
    return el("label", { class: "marker-opt" }, [
      cbx, el("img", { src: m.img, alt: m.label }), el("span", { text: m.label }),
    ]);
  }));

  // 指示物（种类用 datalist 提供游戏王真实 Counter 类型，也可自由输入）
  const counterDatalist = el("datalist", { id: "counter-types" },
    COUNTER_TYPES.map((t) => el("option", { value: t.en, label: `${t.cn} (${t.en})` })));
  const countersWrap = el("div", { class: "counters-edit" }, [counterDatalist]);
  const addCounterRow = (kind = "", count = 1) => {
    const kindIn = textInput(kind, { placeholder: "种类", list: "counter-types" });
    const countIn = numberInput(count, { min: 0 });
    const row = el("div", { class: "counter-row" }, [
      kindIn, countIn,
      el("button", { class: "cy-btn cy-btn--danger cy-btn--sm", text: "✕", onclick: () => row.remove() }),
    ]);
    countersWrap.appendChild(row);
  };
  (c.counters || []).forEach((x) => addCounterRow(x.kind, x.count));

  const form = el("div", { class: "form" }, [
    fieldRow("卡号 id", idIn),
    fieldRow("卡名", nameIn),
    fieldRow("攻击力", atkIn),
    fieldRow("守备力", defIn),
    fieldRow("星 level", levelIn),
    fieldRow("阶 rank", rankIn),
    fieldRow("属性", attrCtl),
    fieldRow("种族", raceCtl),
    fieldRow("箭头", arrowsIn),
    fieldRow("正面", faceIn),
    fieldRow("朝向", orientIn),
    fieldRow("标记", markersWrap),
    el("div", { class: "form-row" }, [
      el("span", { class: "form-label", text: "指示物" }),
      el("div", {}, [
        countersWrap,
        el("button", { class: "cy-btn cy-btn--sm", text: "+ 指示物", onclick: () => addCounterRow() }),
      ]),
    ]),
  ]);

  const collect = () => {
    const markers = Object.entries(markerBoxes).filter(([, b]) => b.checked).map(([k]) => k);
    const counters = [...countersWrap.querySelectorAll(".counter-row")].map((row) => {
      const [kindI, countI] = row.querySelectorAll("input");
      return { kind: kindI.value, count: Number(countI.value) || 0 };
    }).filter((x) => x.kind || x.count);
    return {
      id: Number(idIn.value),
      name: nameIn.value,
      atk: Number(atkIn.value) || 0,
      def: Number(defIn.value) || 0,
      level: Number(levelIn.value) || 0,
      rank: Number(rankIn.value) || 0,
      attribute: attrCtl._get(),
      race: raceCtl._get(),
      arrows: [],
      face_up: faceIn.checked,
      orientation: orientIn.value,
      markers,
      counters,
      extra: c.extra || {},
    };
  };

  const zoneText = `${labelOf(CELL_TYPES, zone)} ${player}-${index}`;
  let buttons;
  if (info.readonly) {
    // 只读（如 deck 区域）
    form.querySelectorAll("input,select,textarea,button").forEach((n) => { n.disabled = true; });
    buttons = [{ label: "关闭", class: "cy-btn--ghost", onClick: closeModal }];
  } else {
    buttons = [
      { label: "保存", class: "cy-btn--exec", onClick: () => { cb.onSave(collect()); closeModal(); } },
      { label: "设为占位卡(-1)", class: "cy-btn--ghost", onClick: () => { cb.onSave({ ...collect(), id: -1 }); closeModal(); } },
      { label: card ? "清除此格" : "关闭", class: "cy-btn--danger", onClick: () => { if (card && cb.onClear) cb.onClear(); closeModal(); } },
    ];
  }
  openModal({
    title: `卡牌详情 · ${zoneText}`,
    badge: "// CARD",
    width: "min(460px,94vw)",
    body: form,
    buttons,
  });
}

// ---------------------------------------------------------------------------
// 各控制面板
// ---------------------------------------------------------------------------
export function openConfigPanel(current, onSave) {
  const ipIn = textInput(current.center_ip || "127.0.0.1");
  const portIn = numberInput(current.center_port || 8765, { min: 1, max: 65535 });
  openModal({
    title: "连接配置",
    badge: "// CENTER",
    body: el("div", { class: "form" }, [
      fieldRow("center IP", ipIn),
      fieldRow("center 端口", portIn),
    ]),
    buttons: [
      { label: "保存并重连", class: "cy-btn--exec", onClick: () => { onSave({ center_ip: ipIn.value, center_port: Number(portIn.value) || 8765 }); closeModal(); } },
    ],
  });
}

export function openLpPanel(player, lp, onApply) {
  const lpIn = numberInput(lp);
  const quick = [8000, 4000, 2000, 0];
  openModal({
    title: `变更 LP · P${player}`,
    badge: "// LP",
    body: el("div", { class: "form" }, [
      fieldRow("新 LP", lpIn),
      el("div", { class: "quick-row" }, quick.map((v) =>
        el("button", { class: "cy-btn cy-btn--ghost cy-btn--sm", text: String(v), onclick: () => { lpIn.value = v; } })
      )),
    ]),
    buttons: [
      { label: "应用", class: "cy-btn--exec", onClick: () => { onApply(Number(lpIn.value) || 0); closeModal(); } },
    ],
  });
}

export function openPhasePanel(current, onApply) {
  const grid = el("div", { class: "quick-grid" }, PHASES.map((p) =>
    el("button", { class: "cy-btn cy-btn--sm" + (p.key === current ? " cy-btn--exec" : ""), text: p.label, onclick: () => { onApply(p.key); closeModal(); } })
  ));
  openModal({ title: "切换阶段", badge: "// PHASE", body: grid });
}

export function openSummonPanel(onApply) {
  const grid = el("div", { class: "quick-grid" }, SUMMON_TYPES.map((s) =>
    el("button", { class: "cy-btn cy-btn--sm", text: s.label, onclick: () => { onApply(s.key); closeModal(); } })
  ));
  openModal({ title: "播放召唤动画", badge: "// SUMMON", body: grid });
}

export function openDestroyPanel(onApply) {
  const coord = coordInput({ cell_type: "front" }, DESTROY_CELL_TYPES);
  openModal({
    title: "播放破坏动画",
    badge: "// DESTROY",
    body: coord.el,
    buttons: [{ label: "播放", class: "cy-btn--exec", onClick: () => { onApply(coord.get()); closeModal(); } }],
  });
}

export function openAttackPanel(onApply) {
  const from = coordInput({ player: 1, cell_type: "front" });
  const to = coordInput({ player: 2, cell_type: "front" });
  const directIn = el("input", { type: "checkbox" });
  const directRow = el("label", { class: "form-row" }, [
    el("span", { class: "form-label", text: "直接攻击" }), directIn,
  ]);
  openModal({
    title: "攻击指令",
    badge: "// ATTACK",
    width: "min(440px,94vw)",
    body: el("div", { class: "coord-group" }, [
      el("div", { class: "coord-title", text: "FROM" }), from.el,
      el("div", { class: "coord-title", text: "TO" }), to.el,
      directRow,
    ]),
    buttons: [{
      label: "执行", class: "cy-btn--exec", onClick: () => {
        const f = from.get();
        const t = directIn.checked ? { player: 0, cell_type: "", cell_index: 0 } : to.get();
        onApply({ ...prefix(f, "from"), ...prefix(t, "to"), is_direct: directIn.checked });
        closeModal();
      },
    }],
  });
}

export function openRelatePanel(onApply) {
  const from = coordInput({ player: 1, cell_type: "front" });
  const to = coordInput({ player: 2, cell_type: "front" });
  openModal({
    title: "卡片关联",
    badge: "// RELATE",
    width: "min(440px,94vw)",
    body: el("div", { class: "coord-group" }, [
      el("div", { class: "coord-title", text: "FROM" }), from.el,
      el("div", { class: "coord-title", text: "TO" }), to.el,
    ]),
    buttons: [{
      label: "执行", class: "cy-btn--exec", onClick: () => {
        const f = from.get();
        const t = to.get();
        onApply({ ...prefix(f, "from"), ...prefix(t, "to") });
        closeModal();
      },
    }],
  });
}

export function openBgmPanel(onApply) {
  const nameIn = textInput("", { placeholder: "bgm 文件名" });
  openModal({
    title: "播放 BGM", badge: "// BGM",
    body: el("div", { class: "form" }, [fieldRow("文件名", nameIn)]),
    buttons: [{ label: "播放", class: "cy-btn--exec", onClick: () => { onApply(nameIn.value); closeModal(); } }],
  });
}

export function openSePanel(onApply) {
  const nameIn = textInput("", { placeholder: "音效文件名" });
  openModal({
    title: "播放音效", badge: "// SE",
    body: el("div", { class: "form" }, [fieldRow("文件名", nameIn)]),
    buttons: [{ label: "播放", class: "cy-btn--exec", onClick: () => { onApply(nameIn.value); closeModal(); } }],
  });
}

export function openDicePanel(onApply) {
  const player = select([{ value: 0, label: "公用" }, { value: 1, label: "P1" }, { value: 2, label: "P2" }], 0);
  openModal({
    title: "掷骰子（1-6）", badge: "// DICE",
    body: el("div", { class: "form" }, [fieldRow("所属", player)]),
    buttons: [{
      label: "ROLL", class: "cy-btn--exec", onClick: () => {
        const value = 1 + Math.floor(Math.random() * 6);
        onApply({ player: Number(player.value), value });
        closeModal();
      },
    }],
  });
}

export function openCoinPanel(onApply) {
  const player = select([{ value: 0, label: "公用" }, { value: 1, label: "P1" }, { value: 2, label: "P2" }], 0);
  openModal({
    title: "投硬币", badge: "// COIN",
    body: el("div", { class: "form" }, [
      fieldRow("所属", player),
      el("p", { class: "hint", text: "正面 = heads，反面 = tails" }),
    ]),
    buttons: [{
      label: "TOSS", class: "cy-btn--exec", onClick: () => {
        const value = Math.random() < 0.5 ? 1 : 0; // 1=正面，0=反面
        onApply({ player: Number(player.value), value });
        closeModal();
      },
    }],
  });
}

export function openImportPanel(player, onPick) {
  const fileIn = el("input", { type: "file", accept: ".ydk,.txt", class: "cy-input" });
  openModal({
    title: `导入卡组 · P${player}`, badge: "// YDK",
    body: el("div", { class: "form" }, [
      el("p", { class: "hint", text: "选择该玩家的 .ydk 文件，解析出卡号列表后发送给 center。" }),
      fieldRow("ydk 文件", fileIn),
    ]),
    buttons: [{
      label: "上传并发送", class: "cy-btn--exec", onClick: () => {
        const f = fileIn.files && fileIn.files[0];
        if (!f) return;
        onPick(f);
        closeModal();
      },
    }],
  });
}

// 把 {player,cell_type,cell_index} 加上前缀
function prefix(obj, p) {
  const out = {};
  for (const [k, v] of Object.entries(obj)) out[`${p}_${k}`] = v;
  return out;
}
