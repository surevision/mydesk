/**
 * state.js
 * ---------------------------------------------------------------------------
 * 战场数据模型与操作函数。数据结构见 protocol.js 顶部注释。
 *
 * 注意：真正的权威状态在 center 端；这里保存的是页面本地的镜像，
 *       用于渲染，以及在任何编辑后发送「完整战场快照」给 center。
 */

// 单格（堆叠）区域：没有下标
export const SINGLE_ZONES = ["exdeck", "deck", "grave", "field"];
// 数组区域：有下标
export const ARRAY_ZONES = ["front", "back", "ex"];

export function isArrayZone(type) {
  return ARRAY_ZONES.includes(type);
}

// 各数组区域的格子数
export function zoneSize(type) {
  if (type === "ex") return 2;
  if (type === "front" || type === "back") return 5;
  return 1;
}

// 区域中文名
export const ZONE_LABEL = {
  exdeck: "EX",
  deck: "DECK",
  grave: "GRAVE",
  field: "FIELD",
  front: "FRONT",
  back: "BACK",
  ex: "EX",
};

/** 生成一张默认卡牌（占位卡 id=-1） */
export function makeCard(overrides = {}) {
  return Object.assign(
    {
      id: -1,
      name: "",
      atk: 0,
      def: 0,
      level: 0,
      rank: 0,
      attribute: "",
      race: "",
      arrows: [],
      face_up: true,
      orientation: "vertical",
      markers: [],
      counters: [],
      extra: {},
    },
    overrides
  );
}

/** 某一方玩家的初始区域 */
export function makePlayer() {
  return {
    lp: 8000,
    exdeck: null,
    deck: null,
    grave: null,
    field: null,
    front: [null, null, null, null, null],
    back: [null, null, null, null, null],
    ex: [null, null],
  };
}

/** 初始战场 */
export function makeBattlefield() {
  return {
    phase: "draw",
    turn_player: 1,
    dice: null,
    coin: null,
    players: { "1": makePlayer(), "2": makePlayer() },
  };
}

/** 补全/规范化外部传入的战场（比如 center 推送的识别结果），缺失字段用默认值填充 */
export function normalizeBattlefield(raw) {
  const bf = makeBattlefield();
  if (!raw || typeof raw !== "object") return bf;

  if (typeof raw.phase === "string") bf.phase = raw.phase;
  if (raw.turn_player === 1 || raw.turn_player === 2 || raw.turn_player === 0) {
    bf.turn_player = raw.turn_player;
  }
  bf.dice = raw.dice || null;
  bf.coin = raw.coin || null;

  for (const p of ["1", "2"]) {
    const src = raw.players && raw.players[p];
    if (!src || typeof src !== "object") continue;
    const dst = bf.players[p];
    if (typeof src.lp === "number") dst.lp = src.lp;
    for (const z of SINGLE_ZONES) {
      dst[z] = src[z] ? normalizeCard(src[z]) : null;
    }
    for (const z of ARRAY_ZONES) {
      const arr = Array.isArray(src[z]) ? src[z] : [];
      dst[z] = [];
      for (let i = 0; i < zoneSize(z); i++) {
        dst[z][i] = arr[i] ? normalizeCard(arr[i]) : null;
      }
    }
  }
  return bf;
}

/** 规范化一张卡 */
export function normalizeCard(raw) {
  const c = makeCard();
  if (!raw || typeof raw !== "object") return c;
  c.id = typeof raw.id === "number" ? raw.id : -1;
  c.name = typeof raw.name === "string" ? raw.name : "";
  c.atk = Number(raw.atk) || 0;
  c.def = Number(raw.def) || 0;
  c.level = Number(raw.level) || 0;
  c.rank = Number(raw.rank) || 0;
  c.attribute = raw.attribute || "";
  c.race = raw.race || "";
  c.arrows = Array.isArray(raw.arrows) ? raw.arrows : [];
  c.face_up = raw.face_up === undefined ? true : !!raw.face_up;
  c.orientation = raw.orientation === "horizontal" ? "horizontal" : "vertical";
  c.markers = Array.isArray(raw.markers) ? raw.markers.slice() : [];
  c.counters = Array.isArray(raw.counters)
    ? raw.counters.map((x) => ({ kind: String(x.kind ?? ""), count: Number(x.count) || 0 }))
    : [];
  c.extra = raw.extra && typeof raw.extra === "object" ? raw.extra : {};
  return c;
}

/** 读取格子上的卡（无返回 null） */
export function getCell(bf, player, type, index = 0) {
  const p = bf.players[String(player)];
  if (!p) return null;
  if (isArrayZone(type)) {
    return (p[type] && p[type][index]) || null;
  }
  return p[type] || null;
}

/** 写入格子（card 传 null 表示清空） */
export function setCell(bf, player, type, index, card) {
  const p = bf.players[String(player)];
  if (!p) return;
  if (isArrayZone(type)) {
    if (!p[type]) p[type] = new Array(zoneSize(type)).fill(null);
    p[type][index] = card;
  } else {
    p[type] = card;
  }
}

/** 深拷贝战场（发送前避免后续修改影响） */
export function cloneBattlefield(bf) {
  return JSON.parse(JSON.stringify(bf));
}
