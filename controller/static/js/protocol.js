/**
 * protocol.js
 * ---------------------------------------------------------------------------
 * controller 页面与 center 之间通信的「协议常量」与「数据结构说明」集中在此。
 *
 * 页面 -> center 的消息类型（复用 display 的 on_* 命名）：
 *   on_battlefield_change  { battlefield: "<battlefield JSON 字符串>" }   完整战场快照
 *   on_lp_change           { player, lp }                                 变更 LP
 *   on_summon_anim         { summon_type }                               播放召唤动画
 *   on_destroy_anim        { player, cell_type, cell_index }             播放破坏动画
 *   on_attack_anim         { from_player, from_cell_type, from_cell_index,
 *                            to_player, to_cell_type, to_cell_index, is_direct }
 *   on_phase_anim          { phase_index }                               播放阶段切换动画
 *   on_play_bgm            { bgm_filename }                              播放 BGM
 *   on_play_se             { se_filename }                               播放音效
 *   on_card_relate_effect  { from_player, from_cell_type, from_cell_index,
 *                            to_player, to_cell_type, to_cell_index }    卡片关联
 *   on_import_ydk          { player, ids, main, extra, side }            导入卡组
 *   on_dice                { player, value }                             掷骰子（value 1-6）
 *   on_coin                { player, value }                             投硬币（value 1=正面, 0=反面）
 *   on_guide               { show }                                      显示/隐藏 display 上的定位方块
 *
 * battlefield JSON 结构（由 controller 拟定，后续按需调整）：
 * {
 *   "phase": "main1",            // 当前阶段: draw/standby/main1/battle/main2/end
 *   "turn_player": 1,            // 当前回合玩家 1/2（0 未知）
 *   "dice": null | { "player": 1, "value": 4, "ts": 1699999999999 },
 *   "coin": null | { "player": 1, "value": 1, "ts": 1699999999999 },
 *   "players": {
 *     "1": {
 *       "lp": 8000,
 *       "exdeck": null | card,   // 额外卡组（堆叠，单格）
 *       "deck":   null | card,   // 主卡组（堆叠，单格；不支持手动设置）
 *       "grave":  null | card,   // 墓地（堆叠，单格）
 *       "field":  null | card,   // 场地魔法（单格）
 *       "front": [card|null x5], // 怪兽区 front1..front5
 *       "back":  [card|null x5], // 魔陷区 back1..back5
 *       "ex":    [card|null x2]  // 额外怪兽区 ex1..ex2（每方各 2 格，存朝向）
 *     },
 *     "2": { ... }
 *   }
 * }
 *
 * card 结构（可扩展：额外字段放 "extra"，避免破坏兼容）：
 * {
 *   "id": -1,                    // ydk passcode；-1 表示占位/未识别
 *   "name": "",                  // 卡名
 *   "atk": 0, "def": 0,          // 攻击力 / 守备力
 *   "level": 0, "rank": 0,       // 星 / 阶
 *   "attribute": "",             // 属性（光/暗/地/水/炎/风/神）
 *   "race": "",                  // 种族
 *   "arrows": [],                // 连接箭头（功能暂不做，留空）
 *   "face_up": true,             // true=正面 false=背面（盖卡）
 *   "orientation": "vertical",   // vertical=纵向（攻击/表侧） horizontal=横向（守备/里侧）
 *   "markers": [],               // 标记: invalid/continuous/equip（可多个）
 *   "counters": [],              // 指示物: [{ "kind": "魔力", "count": 2 }]（可多个）
 *   "extra": {}                  // 预留扩展
 * }
 */

// 阶段：与 display on_phase_anim 的 phase_index 对齐
export const PHASES = [
  { key: "draw", label: "抽卡" },
  { key: "standby", label: "准备" },
  { key: "main1", label: "主要1" },
  { key: "battle", label: "战斗" },
  { key: "main2", label: "主要2" },
  { key: "end", label: "结束" },
];

// 格子类型（用于弹窗选择）
export const CELL_TYPES = [
  { key: "front", label: "怪兽区 front" },
  { key: "back", label: "魔陷区 back" },
  { key: "ex", label: "额外怪兽区 ex" },
  { key: "field", label: "场地 field" },
  { key: "exdeck", label: "额外卡组 exdeck" },
  { key: "grave", label: "墓地 grave" },
  { key: "deck", label: "卡组 deck" },
];

// 允许手动「这里有一张卡」/清除的格子类型（deck 不允许手动设置）
export const SETTABLE_CELL_TYPES = ["front", "back", "ex", "field", "exdeck", "grave"];

// 破坏动画支持的格子类型（与 display on_destroy_anim 说明一致）
export const DESTROY_CELL_TYPES = ["front", "back", "ex"];

// 召唤类型（on_summon_anim.summon_type）
export const SUMMON_TYPES = [
  { key: "normal", label: "通常召唤" },
  { key: "special", label: "特殊召唤" },
  { key: "flip", label: "反转召唤" },
  { key: "ritual", label: "仪式召唤" },
  { key: "fusion", label: "融合召唤" },
  { key: "synchro", label: "同调召唤" },
  { key: "xyz", label: "超量召唤" },
  { key: "pendulum", label: "灵摆召唤" },
  { key: "link", label: "连接召唤" },
];

// 属性 / 种族（作为可选项，允许自由输入）
export const ATTRIBUTES = ["光", "暗", "地", "水", "炎", "风", "神"];
export const RACES = [
  "龙族", "魔法师族", "战士族", "天使族", "恶魔族", "不死族", "机械族", "水族",
  "炎族", "岩石族", "鸟兽族", "兽族", "兽战士族", "昆虫族", "植物族", "鱼族",
  "海龙族", "爬虫类族", "雷族", "恐龙族", "念动力族", "幻神兽族", "创造神族", "幻龙族",
];

// 卡片标记（图片素材放 assets/markers/）
export const MARKER_TYPES = [
  { key: "invalid", label: "无效", img: "assets/markers/invalid.svg" },
  { key: "continuous", label: "永续", img: "assets/markers/continuous.svg" },
  { key: "equip", label: "装备", img: "assets/markers/equip.svg" },
];

// 朝向
export const ORIENTATIONS = [
  { key: "vertical", label: "纵向" },
  { key: "horizontal", label: "横向" },
];

// 指示物类型（游戏王真实 Counter 类型，编号 0-70）。
// 卡牌 counters 里存的 kind 用英文名（en）作为规范键，界面显示中文。
export const COUNTER_TYPES = [
  { id: 0, en: "Magic", cn: "魔力" },
  { id: 1, en: "Normal", cn: "指示物" },
  { id: 2, en: "Clock", cn: "时计" },
  { id: 3, en: "Hyper", cn: "?" },
  { id: 4, en: "Gem", cn: "宝石" },
  { id: 5, en: "Chronicle", cn: "年代记" },
  { id: 6, en: "Bushido", cn: "武士道" },
  { id: 7, en: "D", cn: "D" },
  { id: 8, en: "Shine", cn: "光" },
  { id: 9, en: "Gate", cn: "门" },
  { id: 10, en: "Worm", cn: "虫" },
  { id: 11, en: "Deformer", cn: "变形斗士" },
  { id: 12, en: "Flower", cn: "花" },
  { id: 13, en: "Plant", cn: "植物" },
  { id: 14, en: "Psycho", cn: "念力" },
  { id: 15, en: "EarthBind", cn: "地缚神" },
  { id: 16, en: "Junk", cn: "废品" },
  { id: 17, en: "Genex", cn: "次时代" },
  { id: 18, en: "Dragonic", cn: "龙神" },
  { id: 19, en: "Ocean", cn: "海洋" },
  { id: 20, en: "BF", cn: "黑羽" },
  { id: 21, en: "Death", cn: "?" },
  { id: 22, en: "Karakuri", cn: "机巧" },
  { id: 23, en: "Stone", cn: "魔石" },
  { id: 24, en: "Thunder", cn: "雷" },
  { id: 25, en: "Donguri", cn: "橡子" },
  { id: 26, en: "Greed", cn: "强欲" },
  { id: 27, en: "Chaos", cn: "混沌" },
  { id: 28, en: "Double", cn: "倍倍" },
  { id: 29, en: "Destiny", cn: "命运" },
  { id: 30, en: "Orbital", cn: "遵命" },
  { id: 31, en: "Shark", cn: "鲨" },
  { id: 32, en: "Pumpkin", cn: "南瓜" },
  { id: 33, en: "HopeSlash", cn: "希望剑" },
  { id: 34, en: "Kattobing", cn: "毅飞冲天" },
  { id: 35, en: "Balloon", cn: "气球" },
  { id: 36, en: "Yosen", cn: "妖仙" },
  { id: 37, en: "Sound", cn: "音响" },
  { id: 38, en: "Em", cn: "娱乐法师" },
  { id: 39, en: "Kaiju", cn: "坏兽" },
  { id: 40, en: "Defect", cn: "缺陷" },
  { id: 41, en: "Athlete", cn: "运动员" },
  { id: 42, en: "Barrel", cn: "枪管" },
  { id: 43, en: "Summon", cn: "召唤" },
  { id: 44, en: "FireStar", cn: "炎星" },
  { id: 45, en: "Phantasm", cn: "幻魔" },
  { id: 46, en: "Otoshidama", cn: "落魂" },
  { id: 47, en: "Ounokagi", cn: "皇之键" },
  { id: 48, en: "Piece", cn: "拼图" },
  { id: 49, en: "Girl", cn: "?" },
  { id: 50, en: "Gardna", cn: "?" },
  { id: 51, en: "Alien", cn: "A" },
  { id: 52, en: "Ice", cn: "冰" },
  { id: 53, en: "Venom", cn: "毒" },
  { id: 54, en: "Fog", cn: "雾" },
  { id: 55, en: "Guard", cn: "守卫" },
  { id: 56, en: "Wedge", cn: "楔" },
  { id: 57, en: "Guard2", cn: "?" },
  { id: 58, en: "String", cn: "线" },
  { id: 59, en: "Houkai", cn: "方界" },
  { id: 60, en: "Zushin", cn: "咕咚" },
  { id: 61, en: "Predator", cn: "捕食" },
  { id: 62, en: "Scales", cn: "鳞粉" },
  { id: 63, en: "Police", cn: "警逻" },
  { id: 64, en: "Signal", cn: "信号" },
  { id: 65, en: "Venemy", cn: "蛊" },
  { id: 66, en: "Burn", cn: "燃烧" },
  { id: 67, en: "Illusion", cn: "幻觉" },
  { id: 68, en: "GG", cn: "G石人" },
  { id: 69, en: "Rabbit", cn: "兔耳" },
  { id: 70, en: "Kyoumei", cn: "?" },
];

/** 指示物显示名：中文(English) */
export function counterLabel(en) {
  const c = COUNTER_TYPES.find((x) => x.en === en);
  return c ? `${c.cn} (${c.en})` : en;
}

// 消息类型常量
export const MSG = {
  BATTLEFIELD: "on_battlefield_change",
  LP: "on_lp_change",
  SUMMON: "on_summon_anim",
  DESTROY: "on_destroy_anim",
  ATTACK: "on_attack_anim",
  PHASE: "on_phase_anim",
  BGM: "on_play_bgm",
  SE: "on_play_se",
  RELATE: "on_card_relate_effect",
  IMPORT_YDK: "on_import_ydk",
  DICE: "on_dice",
  COIN: "on_coin",
  GUIDE: "on_guide",
};

// 辅助：按 key 取 label
export function labelOf(list, key) {
  const item = list.find((x) => x.key === key);
  return item ? item.label : key;
}
