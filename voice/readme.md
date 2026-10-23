# voice（语音指令模块）

独立模块：通过 CH340（USB 转串口）读取语音模块输出的文本指令，转换成 center 的 WebSocket 消息。
**只发送、不接收** center 的消息；发送失败直接忽略；串口连接失败每 5 秒自动重试。

## 运行

```bash
# 安装依赖（只用到 pyserial；WebSocket 客户端为内置实现）
pip install -r requirements.txt

python voice.py
```

启动后：

- 配置页面：`http://<本机>:4583/`
- 串口：`voice/config.json` 里的 `serial_port`（默认 `COM3`）/ `baudrate`
- center：`ws://<center_host>:<center_port>`（默认 `127.0.0.1:4560`）

## 配置页面（端口 4583）

可设置：

| 配置项 | 说明 |
| --- | --- |
| 串口 | CH340 对应的串口名，通常为 `COM1` / `COM3`；可从下拉列表选择已识别串口 |
| 波特率 | 与语音模块一致（常见 9600 / 115200） |
| center 地址 | center 的 IP / 主机名，也可直接填 `ws://ip:port` |
| center 端口 | center 的 WebSocket 端口（默认 4560） |

保存后串口/波特率变化会自动重连；center 地址立即生效。配置文件为 `voice/config.json`。

> 页面自身的监听地址（`http_host` / `http_port`）也在配置文件里，修改后需重启 `voice.py` 才生效。

## 串口消息 → center 指令

串口按行读取（`\r\n` 结尾），每行一条：

| 串口文本 | 动作 | 发给 center |
| --- | --- | --- |
| `voice_game_start` | 决斗 | `{"type": "on_game_start"}` |
| `voice_game_reset` | 决斗结束 | `{"type": "on_game_reset"}` |
| `voice_dice` | 掷骰子 | `{"type": "on_dice", "player": 0, "value": 1-6}` |
| `voice_coin` | 掷硬币 | `{"type": "on_coin", "player": 0, "value": 0/1}` |

- `player: 0` 表示双方（与 controller 默认「全部」一致），数值在模块内随机。
- 每条消息附带 `"source": "voice"`，center 收到后会打印一条 `[center] 收到语音指令: {...}` 日志；center 不会把该字段转发给其它端。
- 重复指令照常发送：已开始时再说「决斗」、未开始时再说「决斗结束」都会转发给 center（center 照常广播，由 display 端自行判断是否重复）。
- 其它文本只记录到页面「最近收到」，不做处理。

## 行为说明

- 每条指令临时建立一次 WebSocket 连接发送后断开，center 重启或暂时不可达都不影响后续指令。
- 串口打不开、被拔出、读失败：状态栏显示原因，5 秒后自动重试。
- 未安装 `pyserial` 时模块仍可启动（配置页可用），状态栏提示安装依赖。

## 文件

| 文件 | 说明 |
| --- | --- |
| `voice.py` | 入口：HTTP 配置页 + 串口线程 + 消息映射 |
| `serial_link.py` | 串口读取线程（自动重连）、串口列表 |
| `ws_client.py` | 极简 WebSocket 发送（内置实现，无第三方依赖） |
| `config.py` | 配置读写与 center 地址解析 |
| `config.json` | 运行配置 |
| `static/index.html` | 配置页面 |
| `twencode/` | 语音模块（TWEN 天问）工程文件 |
