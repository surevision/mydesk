## 控制端

用于主动控制要展示的内容及参数调整。使用 Python `http.server` 提供静态页面，
页面内的 JS 作为 WebSocket 客户端连接 center，收发指令。

可部署在中心端机器上，用 Pad 等终端访问（横屏）。

### 架构 / 数据流

```
 浏览器页面(JS)  ──WebSocket──▶  center  ──▶  display(投影端)
      ▲   │                         │
      │   └──HTTP──▶ controller(Python)   (静态页面 + ydk 解析 + 配置读写)
      └──────── 接收 center 推送的战场情况
```

- **controller（Python）**：只负责提供页面/JS/CSS/图片素材，以及少量接口
  （ydk 上传解析、center 连接配置读写）。不主动连接 center。
- **页面 JS**：连接 center 的 WebSocket，接收战场情况并渲染，编辑后把指令发回 center。
- **战场状态**：权威状态在 center 端，controller 页面只是「接收 + 回发指令」。

### 运行

仅用 Python 标准库，无需安装第三方依赖（`requirements.txt` 为空占位）。

```bash
cd controller
python server.py          # 默认监听 0.0.0.0:4582
python server.py 4582     # 指定端口
```

用 Pad 浏览器打开 `http://<中心端IP>:4582/`。页面右上角「配置」可设置 center 的 ip/端口、
骰子/硬币是否指定玩家、静音复选框，以及导入卡组、交换显示位置、显示/隐藏定位等快捷操作。
勾选「骰子、硬币指定玩家」后，点击骰子/硬币先选择“全部 / player1 / player2”；
不勾选则直接按“全部”投掷并显示结果。

### 目录

```
controller/
  server.py              HTTP 服务 + 接口
  config.json            center 连接配置（页面可改，也可手动编辑）
  static/
    index.html           主页面
    css/cyberpunk.css    赛博朋克组件库（取自 materials/Cyberpunk-Style-Kit.html）
    css/app.css          页面布局
    js/protocol.js       协议常量 + battlefield 数据结构说明
    js/state.js          战场数据模型与操作
    js/center.js         center WebSocket 客户端（自动重连 + 心跳）
    js/render.js         战场渲染
    js/panels.js         弹窗与操作面板
    js/api.js            后端接口调用
    js/app.js            主逻辑
    assets/              占位素材（卡背、占位卡、标记色块 SVG）
```

### 后端接口

| 方法 | 路径          | 说明 |
|------|---------------|------|
| GET  | `/api/config` | 读取 center 的 ip/端口配置 |
| POST | `/api/config` | 保存配置，body: `{ "center_ip": "...", "center_port": 4560, "dice_coin_choose_player": false }` |
| POST | `/api/ydk`    | 上传并解析 ydk。multipart 字段 `player` + `file`，或 JSON `{player, content}` |

`/api/ydk` 返回：`{ ok, player, main: [...], extra: [...], side: [...], ids: [...] }`

### 页面 -> center 的消息协议

消息为 JSON 文本 `{ "type": "...", ... }`，类型复用 display 的 `on_*` 命名：

| type                    | 参数 |
|-------------------------|------|
| `on_battlefield_change` | `battlefield`（battlefield 的 JSON 字符串，完整快照） |
| `on_lp_change`          | `player`, `lp` |
| `on_summon_anim`        | `summon_type` |
| `on_destroy_anim`       | `player`, `cell_type`, `cell_index` |
| `on_attack_anim`        | `from_player/from_cell_type/from_cell_index`, `to_player/to_cell_type/to_cell_index`, `is_direct` |
| `on_phase_anim`         | `phase_index`（draw/standby/main1/battle/main2/end） |
| `on_play_bgm`           | `bgm_filename` |
| `on_play_se`            | `se_filename` |
| `on_card_relate_effect` | `from_*`, `to_*`（同上） |
| `on_import_ydk`         | `player`, `ids`, `main`, `extra`, `side` |
| `on_dice`               | `player`（0=全部）, `value`（1-6） |
| `on_coin`               | `player`（0=全部）, `value`（1=正面） |
| `on_guide`              | `show` |
| `on_mute`               | `mute`（true=静音） |
| `on_game_reset`         | 无（center 清空战场并广播空战场给 display） |
| `on_game_start`         | 无（center 广播给所有 controller 和 display） |

上传 ydk 成功后立即发送 `on_import_ydk`，WebSocket 重连成功后也会补发已上传卡组；center 用这些 id 限制卡名识别范围。

进入页面默认只显示中央大号「决斗」按钮，点击后隐藏按钮、显示正常界面并发送 `on_game_start`；center 广播给所有 controller 和 display，controller 收到后不处理，display 端接口预留。

顶部「重新开始」按钮会先弹确认，确认后发送 `on_game_reset`；center 把战场复位为初始状态，并广播重置后的 `on_battlefield_change` 空战场，同时转发带 `battlefield` 字段的 `on_game_reset` 给其它 controller 和 display。controller 收到 `on_game_reset` 后重新显示「决斗」按钮并隐藏正常操作界面。

### battlefield 数据结构

见 `static/js/protocol.js` 顶部注释。要点：

- 每方区域：`exdeck`×1、`deck`×1、`grave`×1（堆叠单格）、`field`×1、`front`×5、`back`×5、`ex`×2。
- 格子类型（cell_type）：`front` / `back` / `ex` / `field` / `exdeck` / `grave` / `deck`。
  - `deck` 不支持手动设置；`front`/`back`/`ex` 有下标（0 起）。
- 卡牌字段：`id`(ydk passcode，-1 为占位)、`name`、`atk`、`def`、`level`(星)、`rank`(阶)、
  `attribute`、`race`、`arrows`(暂留空)、`face_up`(正/背面)、`orientation`(纵/横)、
  `markers`(无效/永续/装备，可多个)、`counters`([{kind,count}]，可多个)、`extra`(预留扩展)。

### 素材替换

占位素材均为 SVG 纯色块，后续可替换为真实图片：

- `static/assets/card_placeholder.svg` 未识别/占位卡面
- `static/assets/card_back.svg` 卡背
- `static/assets/markers/{invalid,continuous,equip}.svg` 标记
- `static/assets/cards/<id>.png` 已知卡号的卡图（缺失时自动回退到占位图）
