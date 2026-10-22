# 视频采集端 monitor

采集对战双方场地的视频信息，中心端（center）通过网络摄像头的方式解析视频。
如果采集端性能够用，未来可以自己解析、把结果发给中心端；**目前只推原始视频流，不自己解析。**

## 做什么

在一台接有摄像头的电脑上运行，把 1~N 个物理摄像头编码成 **MJPEG-over-HTTP** 流，
center 端用 `cv2.VideoCapture("http://<本机IP>:<port>/video/<idx>")` 直接读取，
不需要别的协议，也不需要连 websocket。

- 单摄像头模式：一路 `/video/0` 即可。
- 双摄像头模式（本机接 2 个摄像头）：暴露 `/video/0`、`/video/1`，center 的
  `dual.cameras[].url` 分别填这两个地址。

## 安装依赖

```powershell
cd D:\Git\ygodesk\monitor
pip install -r requirements.txt
```

## 运行

```powershell
python monitor.py                    # 读取 config.json（默认开 2 路：index 0/1）
python monitor.py --cams 0,1         # 指定摄像头索引（顺序即 /video/0、/video/1）
python monitor.py --port 8081        # 改端口
python monitor.py --width 1920 --height 1080 --quality 70
```

启动后终端会打印每路对应的地址，例如：

```
[monitor] /video/0  ← 摄像头 index=0   →  center 填 http://192.168.x.x:4581/video/0
[monitor] /video/1  ← 摄像头 index=1   →  center 填 http://192.168.x.x:4581/video/1
```

## 用静态图片测试识别

不接摄像头时，可用 `test_monitor.py` 把图片包装成同样的 MJPEG 接口：

```powershell
python test_monitor.py --image ..\test\dm6.jpg              # 单路 /video/0
python test_monitor.py --image ..\test\dm6.jpg --cams 2     # 两路都用同一张
python test_monitor.py --image ..\test\dm6.jpg --image ..\test\dm7.jpg
```

默认端口 `4581`、帧率 `5`，接口与 `monitor.py` 相同（`/video/<idx>`、`/snapshot/<idx>`、`/status`）。
把 center 的摄像头地址临时指向 `http://127.0.0.1:4581/video/0` 即可测试。

## 接口

| 路径 | 说明 |
| --- | --- |
| `GET /` | 说明页（各路状态 + 链接） |
| `GET /video/<idx>` | MJPEG 视频流（center 用） |
| `GET /video` | 等价 `/video/0`（兼容单路） |
| `GET /snapshot/<idx>` | 单帧 JPEG（浏览器调试） |
| `GET /status` | 各路状态 JSON |
| `POST /api/fps` | 改采集帧率，body: `{ "fps": 5, "idx": 0 }`（省略 `idx` 则改全部），并写回 config.json |
| `POST /api/resolution` | 改采集分辨率，body: `{ "width": 1920, "height": 1080, "idx": 0 }`（省略 `idx` 则改全部），重开摄像头并写回 config.json |

## 配置 config.json

```json
{
  "host": "0.0.0.0",
  "port": 4581,
  "quality": 70,
  "cameras": [
    { "index": 0, "width": 1920, "height": 1080, "fps": 5 },
    { "index": 1, "width": 1920, "height": 1080, "fps": 5 }
  ]
}
```

- `host` 用 `0.0.0.0` 才能被另一台电脑（center）访问；防火墙需放行该端口。
- `cameras` 的**顺序**就是端点编号：第 1 项是 `/video/0`，第 2 项是 `/video/1`。
- `index` 是 OpenCV 的摄像头编号，Windows 上通常 0/1 对应两个物理摄像头。
- `width` / `height` 是采集分辨率，默认 **960×540**（16:9；双摄各拍一侧卡区时够用，也可用 640×360 / 854×480 / 1280×720 / 1920×1080）；运行中可用 `POST /api/resolution` 或 center 管理页的「采集端 monitor」区域下发，会重开摄像头并写回本文件。
- `fps` 默认 **5**（采集端性能不佳时调低）；运行中可用 `POST /api/fps` 或 center 管理页的「采集端 monitor」区域下发，会写回本文件。摄像头本身按 **30fps + MJPG** 打开，限帧在软件层做（未到间隔只 `grab()` 不解码），所以改帧率**不需要重开摄像头**。
- 1080p/720p 下务必走 MJPG：USB2 带宽下若用默认 YUY2，帧率会被压到个位数（画面很卡），代码已自动请求 `MJPG`。
- `index` 不存在时（多配置了一路摄像头）只会每 15 秒重试一次并显示「无法打开摄像头」；不用请从 `cameras` 里删掉。

## center 端配置

把 `center/config/config.json` 里的地址指向 monitor：

```json
"single": { "url": "http://<monitor-ip>:4581/video/0", "player1_side": "left" }
```

双摄像头模式：

```json
"dual": {
  "swap": false,
  "cameras": [
    { "url": "http://<monitor-ip>:4581/video/0", "player": 1 },
    { "url": "http://<monitor-ip>:4581/video/1", "player": 2 }
  ]
}
```
