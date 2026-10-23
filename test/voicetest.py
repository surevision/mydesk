import serial
import time

# 配置串口参数
PORT = 'COM3'      # 改成你在设备管理器看到的端口号
BAUD = 115200         # 改成你 ASRPRO 程序里设置的波特率

try:
    # 打开串口，设置超时避免卡死
    ser = serial.Serial(PORT, BAUD, timeout=1)
    print(f"已打开 {PORT}，波特率 {BAUD}，等待数据...")
    
    while True:
        # 检查是否有数据可读
        if ser.in_waiting > 0:
            # 读取一行数据（直到遇到换行符），并解码
            # 如果你的数据没有换行符，可以改用 ser.read(ser.in_waiting)
            data = ser.readline().decode('utf-8', errors='ignore').strip()
            if data:
                print(f"收到: {data}")
        time.sleep(0.1)  # 短暂休眠，避免 CPU 占用过高

except serial.SerialException as e:
    print(f"串口打开失败: {e}")
    print("请检查：1. 端口号是否正确 2. 串口是否被其他软件（如天问Block）占用")
except KeyboardInterrupt:
    print("\n停止读取")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()
        print("串口已关闭")