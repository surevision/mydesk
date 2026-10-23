# -*- coding: utf-8 -*-
"""
serial_link.py
---------------------------------------------------------------------------
串口读取线程：通过 CH340（USB 转串口）读取语音模块输出的文本行。

- 一行一条消息（`\\r\\n` 结尾），按 UTF-8/ASCII 解码；
- 连接失败、读失败都只记录状态，隔 5 秒重试；
- 串口打开后收到的每一行都交给 on_message(text) 回调。
"""

import threading
import time

try:
    import serial
    from serial.tools import list_ports
    SERIAL_AVAILABLE = True
    SERIAL_IMPORT_ERROR = ""
except Exception as exc:  # noqa: BLE001  未安装 pyserial 时仍能启动配置页
    serial = None
    list_ports = None
    SERIAL_AVAILABLE = False
    SERIAL_IMPORT_ERROR = str(exc)

RETRY_SECONDS = 5.0


def available_ports():
    """列出本机串口：[{device, description, hwid}]；没有 pyserial 时返回空表。"""
    if not SERIAL_AVAILABLE:
        return []
    out = []
    try:
        for p in list_ports.comports():
            out.append({
                "device": p.device,
                "description": p.description or "",
                "hwid": p.hwid or "",
            })
    except Exception:  # noqa: BLE001
        pass
    out.sort(key=lambda x: x["device"])
    return out


class SerialLink(threading.Thread):
    def __init__(self, port, baudrate, on_message):
        super().__init__(name="voice-serial", daemon=True)
        self._lock = threading.Lock()
        self._port = str(port or "").strip()
        self._baudrate = int(baudrate or 9600)
        self._on_message = on_message
        self._stopping = threading.Event()
        self._reopen = threading.Event()

        self.connected = False
        self.error = "" if SERIAL_AVAILABLE else f"未安装 pyserial: {SERIAL_IMPORT_ERROR}"
        self.last_line = ""
        self.last_ts = 0.0
        self.rx_count = 0

    # ---- 配置 -------------------------------------------------------------
    def configure(self, port, baudrate):
        """修改串口后让读取线程自行关闭旧连接并重开。"""
        with self._lock:
            changed = (self._port != str(port or "").strip()
                       or self._baudrate != int(baudrate or 9600))
            self._port = str(port or "").strip()
            self._baudrate = int(baudrate or 9600)
        if changed:
            self._reopen.set()

    def status(self):
        with self._lock:
            return {
                "serial_available": SERIAL_AVAILABLE,
                "port": self._port,
                "baudrate": self._baudrate,
                "connected": self.connected,
                "error": self.error,
                "last_line": self.last_line,
                "last_ts": self.last_ts,
                "rx_count": self.rx_count,
            }

    def stop(self):
        self._stopping.set()
        self._reopen.set()

    # ---- 线程主体 ---------------------------------------------------------
    def run(self):
        while not self._stopping.is_set():
            with self._lock:
                port, baud = self._port, self._baudrate

            if not SERIAL_AVAILABLE:
                self._set(connected=False, error=f"未安装 pyserial: {SERIAL_IMPORT_ERROR}")
                self._sleep(1.0)
                continue
            if not port:
                self._set(connected=False, error="未配置串口")
                self._sleep(1.0)
                continue

            ser = None
            try:
                self._reopen.clear()
                ser = serial.Serial(port=port, baudrate=baud, timeout=0.5)
                self._set(connected=True, error="")
                print(f"[voice] 串口已打开 {port} @ {baud}")

                while not self._stopping.is_set() and not self._reopen.is_set():
                    try:
                        raw = ser.readline()
                    except Exception as exc:  # noqa: BLE001  串口被拔出等
                        raise OSError(str(exc))
                    if not raw:
                        continue
                    self._handle_line(raw)
            except Exception as exc:  # noqa: BLE001
                self._set(connected=False, error=f"串口连接失败: {exc}")
                self._reopen.clear()
                if not self._stopping.is_set():
                    print(f"[voice] {self.error}（{RETRY_SECONDS:.0f} 秒后重试）")
                    self._sleep(RETRY_SECONDS)
            finally:
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:  # noqa: BLE001
                        pass
                if self.connected:
                    self._set(connected=False, error="串口已关闭")

    # ---- 内部 -------------------------------------------------------------
    def _handle_line(self, raw):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("gbk", "ignore")     # 兼容以 GBK 输出中文的语音模块
        text = text.strip().strip("\x00").strip()
        # 兼容语音模块可能加上的引号/转义符
        text = text.strip("\"'“”‘’\\").strip()
        if not text:
            return
        with self._lock:
            self.last_line = text
            self.last_ts = time.time()
            self.rx_count += 1
        print(f"[voice] 收到: {text}")
        try:
            self._on_message(text)
        except Exception as exc:  # noqa: BLE001  回调出错不影响继续读串口
            print(f"[voice] 处理消息失败: {exc}")

    def _set(self, connected=None, error=None):
        with self._lock:
            if connected is not None:
                self.connected = bool(connected)
            if error is not None:
                self.error = error

    def _sleep(self, seconds):
        end = time.time() + seconds
        while time.time() < end and not self._stopping.is_set():
            time.sleep(0.1)
