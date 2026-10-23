/**
 * panels.js
 * ---------------------------------------------------------------------------
 * 弹窗（modal）基础设施 + 各类操作面板。
 * 每个面板都是「拼好表单 -> 回调返回数据」的形式，具体发送逻辑交给 app.js。
 */
import {
  PHASES, CELL_TYPES, SETTABLE_CELL_TYPES,
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
export function openModal({ title, badge, width, body, buttons = [], stack = false }) {
  if (!stack) closeModal();          // 叠加弹窗（stack）不清理下层弹窗
  const closeThis = stack ? () => mask.remove() : closeModal;
  const mask = el("div", { class: "cy-modal-mask" + (stack ? " cy-modal-mask--stack" : "") });
  const closeBtn = el("div", { class: "cy-modal__close", text: "✕", onclick: closeThis });

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
  mask.addEventListener("click", (e) => { if (e.target === mask) closeThis(); });
  modalRoot.appendChild(mask);
  return { mask, body: bodyEl, close: closeThis };
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

  const markerRow = fieldRow("标记", markersWrap);
  markerRow.classList.add("form-row--wide");

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

  // 卡号 id + 「选择」：从已导入的 P1/P2 卡组中按图片挑选
  const idPick = el("button", {
    class: "cy-btn cy-btn--sm cy-btn--ghost", type: "button", text: "选择",
    onclick: () => {
      const decks = (cb.getDeckIds && cb.getDeckIds()) || {};
      openCardPicker(
        ["1", "2"].map((p) => ({ player: p, ids: decks[p] || [] })),
        (id) => { idIn.value = id; },
      );
    },
  });
  const idRow = el("div", { class: "id-row" }, [idIn, idPick]);

  const form = el("div", { class: "form form--2col" }, [
    fieldRow("卡号 id", idRow),
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
    markerRow,
    el("div", { class: "form-row form-row--wide" }, [
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

/**
 * 卡号「选择」弹窗：按已导入卡组的卡号列出卡图（assets/cards/<id>.jpg）。
 * 找不到图片的卡号显示占位块。叠加在卡牌详情之上，选中后回填 id。
 * @param {Array<{player:string, ids:number[]}>} groups
 * @param {(id:number)=>void} onPick
 */
export function openCardPicker(groups, onPick) {
  let closePicker = () => {};

  const thumb = (id) => {
    const img = el("img", {
      class: "card-thumb__img", src: `assets/cards/${id}.jpg`,
      alt: String(id), loading: "lazy",
    });
    const ph = el("div", { class: "card-thumb__ph", text: String(id) });
    const btn = el("button", {
      class: "card-thumb", type: "button", title: `卡号 ${id}`,
      onclick: () => { onPick(id); closePicker(); },
    }, [img, ph]);
    img.addEventListener("error", () => btn.classList.add("is-missing"));
    return btn;
  };

  const body = el("div", { class: "card-picker" }, groups.map((g) => {
    const grid = g.ids.length
      ? el("div", { class: "card-grid" }, g.ids.map(thumb))
      : el("p", { class: "hint", text: `P${g.player} 尚未导入卡组` });
    return el("div", { class: "card-group" }, [
      el("div", { class: "card-group__hd" }, [
        el("span", { text: `P${g.player} 卡组` }),
        el("span", { class: "k", text: `// ${g.ids.length}` }),
      ]),
      grid,
    ]);
  }));

  const modal = openModal({
    title: "选择卡牌",
    badge: "// CARD PICK",
    width: "min(760px,96vw)",
    stack: true,
    body,
  });
  closePicker = modal.close;
}

/**
 * 点击卡片的「操作选择」面板（在打开卡牌详情之前弹出）。
 * 记录攻击者 / 被攻击者在 app.js 中完成，这里只负责选择动作。
 * @param {object} info { player, zone, index, card }
 * @param {object} cb { onDetail(), onDirect(), onAttack(), onDefend(), onDestroy() }
 * @param {object} sel 已选记录 { attacker, target }（用于提示，可空）
 */
export function openCardActionPanel(info, cb, sel = {}) {
  const { player, zone, index } = info;
  const zoneText = `${labelOf(CELL_TYPES, zone)} ${player}-${index}`;

  const cellText = (c) =>
    c ? `P${c.player} · ${labelOf(CELL_TYPES, c.zone)} ${c.index + 1}` : "未选择";

  const actions = el("div", { class: "action-grid" }, [
    el("button", {
      class: "cy-btn cy-btn--exec", text: "详情",
      onclick: () => { closeModal(); cb.onDetail && cb.onDetail(); },
    }),
    el("button", {
      class: "cy-btn", text: "直接攻击",
      onclick: () => { closeModal(); cb.onDirect && cb.onDirect(); },
    }),
    el("button", {
      class: "cy-btn", text: "攻击",
      onclick: () => { closeModal(); cb.onAttack && cb.onAttack(); },
    }),
    el("button", {
      class: "cy-btn cy-btn--danger", text: "被攻击",
      onclick: () => { closeModal(); cb.onDefend && cb.onDefend(); },
    }),
    el("button", {
      class: "cy-btn cy-btn--danger", text: "破坏",
      onclick: () => { closeModal(); cb.onDestroy && cb.onDestroy(); },
    }),
  ]);

  const hint = el("div", { class: "action-hint" }, [
    el("div", {}, [el("span", { class: "form-label", text: "攻击者" }), el("b", { text: cellText(sel.attacker) })]),
    el("div", {}, [el("span", { class: "form-label", text: "被攻击者" }), el("b", { text: cellText(sel.target) })]),
  ]);

  openModal({
    title: `卡牌操作 · ${zoneText}`,
    badge: "// ACTION",
    width: "min(380px,92vw)",
    body: el("div", {}, [actions, hint]),
  });
}

// ---------------------------------------------------------------------------
// 各控制面板
// ---------------------------------------------------------------------------
export function openConfigPanel(current, onSave, actions = {}) {
  const ipIn = textInput(current.center_ip || "127.0.0.1");
  const portIn = numberInput(current.center_port || 4560, { min: 1, max: 65535 });
  const chooseIn = el("input", { type: "checkbox" });
  chooseIn.checked = !!current.dice_coin_choose_player;

  let muted = !!current.muted;
  const muteIn = el("input", { class: "cy-checkbox", type: "checkbox" });
  muteIn.checked = muted;
  muteIn.addEventListener("change", () => {
    muted = muteIn.checked;
    if (actions.onMute) actions.onMute(muted);
  });

  const quick = el("div", { class: "quick-grid" }, [
    el("button", {
      class: "cy-btn cy-btn--sm", text: "导入卡组 player1", type: "button",
      onclick: () => actions.onImport && actions.onImport(1),
    }),
    el("button", {
      class: "cy-btn cy-btn--sm", text: "导入卡组 player2", type: "button",
      onclick: () => actions.onImport && actions.onImport(2),
    }),
    el("button", {
      class: "cy-btn cy-btn--sm", text: "交换位置", type: "button",
      onclick: () => actions.onSwap && actions.onSwap(),
    }),
    el("button", {
      class: "cy-btn cy-btn--sm", text: "显示定位", type: "button",
      onclick: () => actions.onGuide && actions.onGuide(true),
    }),
    el("button", {
      class: "cy-btn cy-btn--sm cy-btn--ghost", text: "隐藏定位", type: "button",
      onclick: () => actions.onGuide && actions.onGuide(false),
    }),
  ]);

  const modal = openModal({
    title: "配置",
    badge: "// SETUP",
    width: "min(480px,94vw)",
    body: el("div", { class: "form" }, [
      fieldRow("center IP", ipIn),
      fieldRow("center 端口", portIn),
      el("p", { class: "hint", text: "留空或填 127.0.0.1 / localhost 时，自动使用当前打开本页的地址。" }),
      fieldRow("骰子、硬币指定玩家", chooseIn),
      el("p", { class: "hint", text: "勾选后先选择 player1 / player2；不勾选则直接按“全部”投掷并显示结果。" }),
      fieldRow("静音", muteIn),
      el("p", { class: "hint", text: "勾选后 display 端立即静音；取消勾选恢复播放。" }),
      el("div", { class: "coord-title", text: "快捷操作" }),
      quick,
    ]),
    buttons: [
      {
        label: "保存", class: "cy-btn--exec", onClick: () => {
          onSave({
            center_ip: ipIn.value,
            center_port: Number(portIn.value) || 4560,
            dice_coin_choose_player: chooseIn.checked,
          });
          modal.close();
        },
      },
    ],
  });
}

export function openLpPanel(player, lp, onApply) {
  const start = Number(lp) || 0;

  let acc = start;        // 运算符左侧的累积值
  let pendingOp = null;   // "+" | "-"
  let fresh = true;       // 下一次数字输入是否替换显示值

  const display = el("input", {
    class: "lp-calc__display",
    type: "text",
    inputmode: "numeric",
    autocomplete: "off",
    value: String(start),
  });
  const hint = el("div", { class: "lp-calc__hint" });

  const num = () => Number(display.value) || 0;
  const setDisplay = (v) => { display.value = String(v); };
  const renderHint = () => {
    hint.textContent = pendingOp
      ? `P${player} · ${acc} ${pendingOp === "+" ? "+" : "−"}`
      : `P${player} · 当前 LP ${start}`;
  };

  const pressDigit = (d) => {
    if (fresh) {
      setDisplay(d);
      fresh = false;
    } else {
      const cur = display.value === "0" ? "" : display.value;
      setDisplay((cur + d).slice(0, 9) || "0");
    }
    renderHint();
  };

  const pressDoubleZero = () => {
    if (fresh) {
      setDisplay("0");
      fresh = false;
    } else {
      const cur = display.value === "0" ? "" : display.value;
      setDisplay((cur + "00").slice(0, 9) || "0");
    }
    renderHint();
  };

  const pressBack = () => {
    const v = display.value.slice(0, -1);
    setDisplay(v === "" ? "0" : v);
    fresh = false;
    renderHint();
  };

  const pressClear = () => {
    acc = 0;
    pendingOp = null;
    fresh = true;
    setDisplay("0");
    renderHint();
  };

  const pressOp = (op) => {
    if (pendingOp && !fresh) {
      acc = pendingOp === "+" ? acc + num() : acc - num();
    } else if (!pendingOp) {
      acc = num();
    }
    pendingOp = op;
    setDisplay(acc);
    fresh = true;
    renderHint();
  };

  const apply = () => {
    let v;
    if (pendingOp) {
      v = fresh ? acc : (pendingOp === "+" ? acc + num() : acc - num());
    } else {
      v = num();
    }
    onApply(Math.max(0, Math.round(v)));
    closeModal();
  };

  // 直接键盘输入：只保留数字
  display.addEventListener("input", () => {
    display.value = display.value.replace(/\D/g, "").slice(0, 9);
    fresh = false;
    renderHint();
  });
  display.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); apply(); }
    else if (e.key === "+") { e.preventDefault(); pressOp("+"); }
    else if (e.key === "-") { e.preventDefault(); pressOp("-"); }
  });

  const key = (label, cls, onclick) =>
    el("button", { class: `cy-btn cy-btn--sm lp-calc__key ${cls || ""}`, text: label, onclick });

  const keys = el("div", { class: "lp-calc__keys" }, [
    key("7", "", () => pressDigit("7")),
    key("8", "", () => pressDigit("8")),
    key("9", "", () => pressDigit("9")),
    key("⌫", "cy-btn--ghost", pressBack),

    key("4", "", () => pressDigit("4")),
    key("5", "", () => pressDigit("5")),
    key("6", "", () => pressDigit("6")),
    key("C", "cy-btn--danger", pressClear),

    key("1", "", () => pressDigit("1")),
    key("2", "", () => pressDigit("2")),
    key("3", "", () => pressDigit("3")),
    key("−", "lp-calc__key--op", () => pressOp("-")),

    key("0", "", () => pressDigit("0")),
    key("00", "", pressDoubleZero),
    key("+", "lp-calc__key--op", () => pressOp("+")),
    key("=", "cy-btn--exec", apply),
  ]);

  const body = el("div", { class: "lp-calc" }, [
    el("div", { class: "lp-calc__view" }, [hint, display]),
    keys,
  ]);

  renderHint();
  openModal({
    title: `变更 LP · P${player}`,
    badge: "// LP",
    width: "min(360px,92vw)",
    body,
    buttons: [
      { label: "应用", class: "cy-btn--exec", onClick: apply },
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

const ROLL_TARGETS = [
  { value: 0, label: "全部" },
  { value: 1, label: "player1" },
  { value: 2, label: "player2" },
];

export function rollTargetLabel(player) {
  return player ? `player${player}` : "全部";
}

// 掷骰 / 硬币结果弹窗（大号结果，等待用户确认）
export function openRollResultPanel(title, badge, main, sub) {
  const body = el("div", { class: "roll-result" }, [
    el("div", { class: "roll-result__main", text: main }),
    el("div", { class: "roll-result__sub", text: sub }),
  ]);
  openModal({
    title,
    badge,
    width: "min(320px,90vw)",
    body,
    buttons: [{ label: "确定", class: "cy-btn--exec", onClick: closeModal }],
  });
}

// 决斗结束确认弹窗
export function openResetPanel(onConfirm) {
  const modal = openModal({
    title: "决斗结束",
    badge: "// END",
    width: "min(360px,90vw)",
    body: el("div", { class: "form" }, [
      el("p", { class: "hint", text: "将清空双方战场、结束本次决斗并暂停识别，是否继续？" }),
    ]),
    buttons: [
      { label: "取消", onClick: () => modal.close() },
      {
        label: "决斗结束", class: "cy-btn--danger",
        onClick: () => { modal.close(); onConfirm(); },
      },
    ],
  });
}

function rollTargetGrid(onPick) {
  return el("div", { class: "quick-grid" }, ROLL_TARGETS.map((t) =>
    el("button", {
      class: "cy-btn", text: t.label, type: "button",
      onclick: () => { closeModal(); onPick(t.value); },
    })
  ));
}

export function openDicePanel(onApply) {
  openModal({
    title: "掷骰子（1-6）", badge: "// DICE",
    body: rollTargetGrid((player) => {
      const value = 1 + Math.floor(Math.random() * 6);
      onApply({ player, value });
      openRollResultPanel("骰子结果", "// DICE", String(value),
        `点数 ${value} · ${rollTargetLabel(player)}`);
    }),
  });
}

export function openCoinPanel(onApply) {
  openModal({
    title: "投硬币", badge: "// COIN",
    body: el("div", {}, [
      el("p", { class: "hint", text: "正面 = heads，反面 = tails" }),
      rollTargetGrid((player) => {
        const value = Math.random() < 0.5 ? 1 : 0; // 1=正面，0=反面
        onApply({ player, value });
        openRollResultPanel("硬币结果", "// COIN", value === 1 ? "正" : "反",
          `${value === 1 ? "正面 (heads)" : "反面 (tails)"} · ${rollTargetLabel(player)}`);
      }),
    ]),
  });
}

export function openImportPanel(player, onPick) {
  const fileIn = el("input", { type: "file", accept: ".ydk,.txt", class: "cy-input" });
  const modal = openModal({
    title: `导入卡组 · player${player}`, badge: "// YDK",
    stack: true,
    body: el("div", { class: "form" }, [
      el("p", { class: "hint", text: "选择该玩家的 .ydk 文件，解析出卡号列表后发送给 center。" }),
      fieldRow("ydk 文件", fileIn),
    ]),
    buttons: [{
      label: "上传并发送", class: "cy-btn--exec", onClick: () => {
        const f = fileIn.files && fileIn.files[0];
        if (!f) return;
        onPick(f);
        modal.close();
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
