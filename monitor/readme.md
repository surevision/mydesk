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
python monitor.py --width 1280 --height 720 --quality 70
```

启动后终端会打印每路对应的地址，例如：

```
[monitor] /video/0  ← 摄像头 index=0   →  center 填 http://192.168.x.x:8080/video/0
[monitor] /video/1  ← 摄像头 index=1   →  center 填 http://192.168.x.x:8080/video/1
```

## 接口

| 路径 | 说明 |
| --- | --- |
| `GET /` | 说明页（各路状态 + 链接） |
| `GET /video/<idx>` | MJPEG 视频流（center 用） |
| `GET /video` | 等价 `/video/0`（兼容单路） |
| `GET /snapshot/<idx>` | 单帧 JPEG（浏览器调试） |
| `GET /status` | 各路状态 JSON |

## 配置 config.json

```json
{
  "host": "0.0.0.0",
  "port": 8080,
  "quality": 70,
  "cameras": [
    { "index": 0, "width": 1280, "height": 720, "fps": 30 },
    { "index": 1, "width": 1280, "height": 720, "fps": 30 }
  ]
}
```

- `host` 用 `0.0.0.0` 才能被另一台电脑（center）访问；防火墙需放行该端口。
- `cameras` 的**顺序**就是端点编号：第 1 项是 `/video/0`，第 2 项是 `/video/1`。
- `index` 是 OpenCV 的摄像头编号，Windows 上通常 0/1 对应两个物理摄像头。

## center 端配置

把 `center/config.json` 里的地址指向 monitor：

```json
"single": { "url": "http://<monitor-ip>:8080/video/0", "player1_side": "left" }
```

双摄像头模式：

```json
"dual": {
  "swap": false,
  "cameras": [
    { "url": "http://<monitor-ip>:8080/video/0", "player": 1 },
    { "url": "http://<monitor-ip>:8080/video/1", "player": 2 }
  ]
}
```
