# 主控端 center

职责：

- **WebSocket 中转**：display（Godot）与 controller（浏览器）都连到这里。
- **保存当前战场权威状态**：人工设置优先，识别结果补充（便于容错）。
- **摄像头识别**：读取视频流 → 检测卡牌 → 由卡牌中心坐标映射到格子 → 更新战场并广播。
- **HTTP 管理页面**：切换摄像头模式/参数、查看视频流与运行状态。

## 运行

首次使用先装依赖（识别需要 cv2/ultralytics/onnxruntime）：

```powershell
conda activate ygodesk
pip install -r requirements.txt      # 见 center/requirements.txt；GPU 可换 onnxruntime-gpu
```

```powershell
cd D:\Git\mydesk\center
# 识别需要 cv2/ultralytics/onnxruntime，请用装好这些库的环境（如 conda ygodesk）
conda run -n ygodesk python center.py
```

启动输出管理页面地址（默认 `http://0.0.0.0:4580/`）与 WebSocket 地址（默认 `ws://0.0.0.0:4560`）。
只需预览/中转、不做识别时，任意 Python 3 均可直接 `python center.py`（缺少的库会自动降级并提示）。

可用 `--http-port` / `--ws-port` 覆盖端口。

## 识别实现（参考 test/videotest.py、test/yolotest.py）

- **cv2** 取流（`CAP_PROP_BUFFERSIZE=1`，读帧失败自动重连）。每路摄像头拆成 **采集 / 识别 / 发布** 三条线程：采集只管读帧，识别按 `detect.interval` 取最新帧（可慢），预览始终按采集帧率刷新，不会因为推理慢把管理页拖成 1fps。
- **正面检测走纯 ONNX**（`models.yolo_front` 以 `.onnx` 结尾时）：`ygo_yolo.onnx`（draw2 网页版同款 YOLO11s-obb，输入 640、单类）。自己做 letterbox → onnxruntime 推理 → 解析 `[6,N]`(x,y,w,h,conf,angle) → OBB 近似 IoU NMS（`nms_iou`）。解析和 NMS 都做了整表向量化（8400 行逐元素循环在 Python 里要 ~1s）。路径为 `.pt` 时仍走 **ultralytics YOLO(OBB)**。**卡背检测**暂仍用 ultralytics `cardback_best.pt`（如需纯 ONNX，可提供它的 onnx 导出）。
- **ultralytics** 推理设备 `detect.device` 默认 `0`，但会**自动判断**：`torch.cuda.is_available()` 为假（如 CPU 版 torch）时回退 `cpu`，卡号越界也会纠正；显式设 `cpu` 则强制 CPU。实际使用的设备在运行状态里显示。
- **onnxruntime**：卡名识别 `vit_fp32.onnx`（带 `.onnx` 正面检测时复用同一批 `providers`），依次尝试 `CUDAExecutionProvider`→`CPUExecutionProvider`（实际使用的提供者在状态里显示）。**注意**：`onnxruntime-gpu` 1.2x 起要求 CUDA 13，而 torch 2.6+cu124 自带的是 CUDA 12；版本不匹配时 CUDA EP 建不起来会**静默退回 CPU**（启动日志里 PROVIDER 会只剩 CPU，正面推理 ~300ms）。装 `onnxruntime-gpu==1.20.1`（CUDA 12 + cuDNN 9）即可走 GPU（~10ms）。
- ONNX 模型**无内置跟踪器**，用自建 **IoU 跟踪**（`track_iou`/`track_ttl`）维持稳定 id；`.pt` 路径仍用 ultralytics 跟踪。
- 朝向/尺寸用 OBB 的 `xywhr` 判断。分类顺序：先跑 draw2 `vit_fp32.onnx` 识别卡名，识别成功即按正面；未识别时再由 `cardback_best.pt` 判断，且该区域中心必须为暗色（`dark>0.6` 且 `mean_v<80`）才按反面，否则按卡面（无卡名）。这样卡名识别优先于卡背模型，卡背模型也只对暗色区域生效，避免把亮色正面卡误判成卡背。
- 卡裁切移植 draw2：四个 OBB 角点先统一绕向、再从**短边**起重排，单应矫正成 `detect.crop_size`（默认 224）**方图**，使卡片长边始终竖直（横置/守备卡不再被压扁）。矫正后只剩 0°/180° 歧义：先用卡面上下亮度猜（正立时下半部更亮），置信度低于 `flip_low` 再试另一方向，且需比原方向好 `flip_margin` 倍才采纳。
- 跟踪 id + **卡名缓存（TTL）**，避免每帧重复跑卡名 ONNX；卡名候选可用已导入卡组约束（`on_import_ydk` → `DeckStore`，前 `top_k` 个里挑选）。导入卡组后，draw2 认出卡组外的卡名不会输出，也不采信其低阈值识别结果；此时改用 HSV 亮度判断，暗色按卡背，否则按未知正面卡牌。**这个识别方法可能后续还会变更。**
- **卡名黑名单**：`blacklist.txt` 一行一个 `card_id`，命中后该卡名不按卡面处理。可直接编辑文件，也可在管理页「卡名黑名单」维护；保存后立即生效，无需重启识别。
- 中心坐标 → `(玩家, 格子)`，落格结果写入战场（人工格优先）。

## 文件

| 文件 | 说明 |
| --- | --- |
| `center.py` | 入口：串起 HTTP + WebSocket + 识别，并做消息路由 |
| `config.py` / `config/` | 配置读写；`config/config_default.json` 为提交的默认模板，首次运行复制生成 `config/config.json`（本机配置，可加入 .gitignore） |
| `ws_server.py` | 纯标准库 WebSocket 服务端（RFC6455），无第三方依赖 |
| `state.py` | 战场状态存储（人工优先、识别补充） |
| `blacklist.py` / `blacklist.txt` | 卡名黑名单：命中 `card_id` 的卡名不按卡面处理 |
| `gridmap.py` | 画面坐标 → (玩家, 格子) 的映射（未定位时的回退方案） |
| `calib.py` | 定位/校准：4 个定位方块 → 单应变换 → 正空间格子（纵向移植自 test/regiontest.py，横向移植自 test/h_regiontest.py；双摄每路可选方向） |
| `recognize.py` | 摄像头线程 + 每路独立 `Detector`（YOLO/ONNX）识别流水线；多路并发不串号 |
| `http_server.py` | 管理页面、接口、MJPEG 预览 |
| `static/` | 管理页面（admin.html/js/css） |

## 消息路由

- 收到 `on_battlefield_change`：解析并入 `state`，再广播给所有客户端。
- 收到 `on_lp_change` / `on_phase_anim`：更新 `state` 并广播对应消息。
- 收到 `on_guide`：转换为 `on_marker_guide`（附带定位四角坐标）后广播给 display。
- 收到 `on_mute`：记录全局静音状态并广播 `{ type: "on_mute", mute }`，display 控制 Master 总线静音。
- 收到 `on_game_start`：广播给所有 controller 和 display（controller 收到后不处理，display 端接口预留）。
- 收到 `on_game_reset`：把战场复位为初始状态，随后广播 `on_battlefield_change`（重置后的空战场），并向其它端转发带 `battlefield` 字段的 `on_game_reset`；display 端用该字段返回标题/刷新显示。
- 其余 `on_*`（召唤/破坏/攻击/关联/音效/导入/骰子等）：原样转发给其它端（主要是 display）。
- 新客户端连接时，立即下发一次当前战场快照和静音状态。

## 摄像头模式

- **单摄像头 `single`**：一台摄像头横向拍摄双方场地；画面左右各属一名玩家，`player1_side` 决定 player1 在左还是右。
- **双摄像头 `dual`**：每台拍一名玩家；`cameras[i].player` 指定对应玩家，`swap` 可整体交换。`cameras[i].orientation` 指定该路画面方向：`horizontal`=横向（3 行×7 列，默认），`vertical`=竖向（7 行×3 列）；两路可分别设置。
- 每路摄像头在**独立线程**里取流，并各有**独立的识别器**（独立 YOLO 实例与跟踪器、卡名缓存），因此两路可真正并发、OBB 跟踪 id 不会相互串号；只共享无状态的卡名 ONNX 会话。
- 双摄像头要填**两个不同**的视频流地址（如采集端 monitor 的 `/video/0`、`/video/1`）；若两路填同一地址，实际只有一路画面。

识别到的卡牌用**中心坐标**落到格子：若已做过定位（见下），走校准的单应映射；否则回退到「玩家区域矩形 + `layout` 归一化矩形」。

## 采集端（monitor）帧率 / 分辨率

在管理页「采集端 monitor」区域可下发帧率和采集分辨率（720p / 1080p）：center 会把 `POST /api/monitor_fps {fps}` / `POST /api/monitor_resolution {width,height}` 转发到当前配置里各摄像头地址所在的采集端（`scheme://host:port`）的 `/api/fps` 或 `/api/resolution`，采集端据此修改并写回其 config.json；改分辨率后会重新打开摄像头。center 收到的画面尺寸由采集端分辨率决定。本地摄像头索引地址（纯数字）不会转发。

## 定位 / 校准

用场地四角的 **4 个「二维码角块」样式定位方块**做透视矫正，替代「左右各半」的粗略划分：

1. 管理页「定位 / 校准」面板中，在每路画面上**框选玩家区域**（单摄像头框两次：player1、player2；双摄像头每路框一次）。
2. 点「开始定位」：在这些 ROI 内检测定位方块 → 分配 tl/tr/br/bl（2/3 点用平行四边形约束推算）→ 求「画面 → 正空间」单应矩阵。**检测不到 4 个方块会报错并要求重新框选。**
3. 正空间里按配置方向切网格：**单摄像头**固定为纵向 7 行×3 列（`regiontest.py` 参数）；**双摄像头**每路按 `orientation` 选择横向 3 行×7 列（`h_regiontest.py` 参数，定位方块更大、关闭内部黑约束）或竖向 7 行×3 列（`regiontest.py` 参数）。卡牌中心经单应映射后查格子。修改方向后需重新定位。
4. 「显示 / 隐藏定位方块」按钮会经 WebSocket 向 display 发送 `on_marker_guide` 消息（display 端处理函数目前留空）。

定位结果**仅保存在内存**，`center` 重启后需重新框选；定位成功后会自动重发一次当前战场快照给 control / display。

相关接口：

- `GET  /api/calib`：当前定位结果。
- `POST /api/calibrate` `{cam_id, rois:{player:[x0,y0,x1,y1]}}`：执行定位。
- `POST /api/guide` `{show:true|false}`：显示/隐藏 display 上的定位方块。
- `GET  /raw/<cam_id>`、`GET /rawsnap/<cam_id>`：原始帧预览（不带格子叠加，供框选）。

## 人工优先策略

- controller 发来的完整快照中被改动的格子标记为 `manual`。
- 识别只更新非 `manual` 格子；人工设置的格子不会被识别覆盖（清空同理）。
- 因此识别出错时，人工设置该格即可「钉住」，识别不再改动它。
