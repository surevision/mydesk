# 主控端 center

职责：

- **WebSocket 中转**：display（Godot）与 controller（浏览器）都连到这里。
- **保存当前战场权威状态**：人工设置优先，识别结果补充（便于容错）。
- **摄像头识别**：读取视频流 → 检测卡牌 → 由卡牌中心坐标映射到格子 → 更新战场并广播。
- **HTTP 管理页面**：切换摄像头模式/参数、查看视频流与运行状态。

## 运行

```powershell
cd D:\Git\mydesk\center
# 识别需要 cv2/ultralytics/onnxruntime，请用装好这些库的环境（如 conda ygodesk）
conda run -n ygodesk python center.py
```

启动输出管理页面地址（默认 `http://0.0.0.0:8080/`）与 WebSocket 地址（默认 `ws://0.0.0.0:8765`）。
只需预览/中转、不做识别时，任意 Python 3 均可直接 `python center.py`（缺少的库会自动降级并提示）。

可用 `--http-port` / `--ws-port` 覆盖端口。

## 识别实现（参考 test/videotest.py、test/yolotest.py）

- **cv2** 取流（`CAP_PROP_BUFFERSIZE=1`，读帧失败自动重连）。
- **ultralytics YOLO(OBB)**：正面 `ygo_yolo.pt`、卡背 `cardback_best.pt`；走 **GPU**（`detect.device`，默认 `0`；设 `cpu` 则用 CPU）。
- **onnxruntime GPU**：卡名识别 `vit_fp32.onnx`，`providers` 依次尝试 `CUDAExecutionProvider`→`CPUExecutionProvider`（实际使用的提供者在状态里显示）。
- 朝向/尺寸用 OBB 的 `xywhr` 判断（与 videotest 一致）；正反面用 HSV 暗区/色相方差判定。
- 使用 **OBB 跟踪 id + 卡名缓存（TTL）**，避免每帧重复跑卡名 ONNX。
- 中心坐标 → `(玩家, 格子)`，落格结果写入战场（人工格优先）。

## 文件

| 文件 | 说明 |
| --- | --- |
| `center.py` | 入口：串起 HTTP + WebSocket + 识别，并做消息路由 |
| `config.py` / `config.json` | 配置读写（首次运行自动生成 config.json） |
| `ws_server.py` | 纯标准库 WebSocket 服务端（RFC6455），无第三方依赖 |
| `state.py` | 战场状态存储（人工优先、识别补充） |
| `gridmap.py` | 画面坐标 → (玩家, 格子) 的映射 |
| `recognize.py` | 摄像头线程 + YOLO/ONNX 识别流水线 |
| `http_server.py` | 管理页面、接口、MJPEG 预览 |
| `static/` | 管理页面（admin.html/js/css） |

## 消息路由

- 收到 `on_battlefield_change`：解析并入 `state`，再广播给所有客户端。
- 收到 `on_lp_change` / `on_phase_anim`：更新 `state` 并广播对应消息。
- 其余 `on_*`（召唤/破坏/攻击/关联/音效/导入/骰子等）：原样转发给其它端（主要是 display）。
- 新客户端连接时，立即下发一次当前战场快照。

## 摄像头模式

- **单摄像头 `single`**：一台摄像头横向拍摄双方场地；画面左右各属一名玩家，`player1_side` 决定 player1 在左还是右。
- **双摄像头 `dual`**：每台拍一名玩家；`cameras[i].player` 指定对应玩家，`swap` 可整体交换。

识别到的卡牌用**中心坐标**落到格子：先确定属于哪名玩家区域，再在区域内按 `layout` 各格子的归一化矩形判断。

## 格子布局与校准

`config.json` 的 `layout` 是「某名玩家区域内」各格子的归一化矩形（0-1）：

- `back`（魔陷 5）、`front`（怪兽 5）、`ex`（额外怪兽 2）、`field` / `grave` / `deck` / `exdeck`（各 1）。

管理页面的视频预览会把当前布局以黄框**叠加**在画面上，方便对照实拍调整这些数字。

### 是否需要定位识别物？

**建议使用**。当前方案基于「拍摄区域正好覆盖卡牌区域」的假设，直接用归一化坐标映射；只要摄像头固定且摆正即可工作。

若摄像头有透视/倾斜、或会移动，建议在场地四角放置 **4 个标记物（ArUco / AprilTag）**：

- 用 4 个角点计算单应矩阵做透视矫正，可显著提升落格准确率与鲁棒性；
- 后续可在此基础上增加自动标定（无需手调 layout 数字）。

如需该功能请告知，可在 `recognize.py` 中接入（依赖 `opencv-contrib-python` 的 `cv2.aruco`）。

## 人工优先策略

- controller 发来的完整快照中被改动的格子标记为 `manual`。
- 识别只更新非 `manual` 格子；人工设置的格子不会被识别覆盖（清空同理）。
- 因此识别出错时，人工设置该格即可「钉住」，识别不再改动它。
