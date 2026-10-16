# regiontest.py 算法说明

## 目录

- [一、整体流程](#一整体流程)
- [二、定位方块识别](#二定位方块识别)
- [三、卡片放置格子定位](#三卡片放置格子定位)
- [四、为什么这套算法鲁棒](#四为什么这套算法鲁棒)
- [五、关键参数说明](#五关键参数说明)
- [六、数据流](#六数据流)

---

## 一、整体流程

脚本分两大块：

1. **定位方块识别** —— 在画面里找出 4 个"二维码角块"样式的方块
2. **卡片放置格子定位** —— 用这 4 个方块算出玩家区的透视变换，再按比例切 7×3 网格

```
输入图像 (BGR)
    ↓
【定位方块识别】
    ① 灰度化 + CLAHE（压制反光）
    ② HSV 阈值 + 灰度阈值 → 白色掩膜
    ③ 闭运算（连接内部破碎）+ 腐蚀（分离粘连）
    ④ 找轮廓 + 六重过滤
    ⑤ 象限筛选（每象限 1 个）→ 每侧 4 个方块
    ↓
【格子定位】
    ⑥ 4 角分配（含 2/3 点推算）
    ⑦ 透视变换 H（画面 → 正空间 0~1）
    ⑧ 正空间里按 7×3 均匀切网格
    ⑨ 点击位置 → H 映射 → 查格子
    ↓
输出：PlayerN | 类型 | 第 N 号
```

---

## 二、定位方块识别

### 目标

每个玩家区有 **4 个定位方块**，分布在**玩家区的 4 个角**。识别到它们后，**4 个方块的外包围区域**就是这个玩家区的边界。

**定位方块外观**：

- 正方形，边长约 **56~70px**
- 白边 + 中间黑（实心版：外白框 + 黑心 + 内白点；空心版：只有白边框）
- **边缘是白**（不是黑）

### 步骤

#### 第 1 步：灰度化 + CLAHE 增强

```python
gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
gray_c = clahe.apply(gray)
```

- **灰度化**：3 通道压成 1 通道，减少计算量
- **CLAHE**：把图像分成 8×8 小块，每块独立做直方图均衡
- **`clipLimit=4.0`**（比默认 2.0 大）：**专门压制屏幕反光的过曝区**

#### 第 2 步：提取白色掩膜

```python
hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
mask_hsv = cv2.inRange(hsv, (0, 0, 120), (180, 160, 255))
_, mask_gray = cv2.threshold(gray_c, 180, 255, cv2.THRESH_BINARY)
mask_white = cv2.bitwise_and(mask_hsv, mask_gray)
```

- **HSV 条件**：H 任意、S ≤ 160（低饱和）、V ≥ 120（高亮度）→ 灰白色
- **灰度条件**：CLAHE 后灰度 ≥ 180 → 亮
- **交集**：同时满足"低饱和 + 高亮度" → 真正白色
- **排除**：彩色反光（S 高）、暗背景（V 低）

#### 第 3 步：闭运算（连接破碎区域）

```python
kernel_close = np.ones((3, 3), np.uint8)
mask_closed = cv2.morphologyEx(mask_white, cv2.MORPH_CLOSE,
                               kernel_close, iterations=1)
```

**闭运算 = 先膨胀后腐蚀**。

- **目的**：把方块内部的"外白框 + 内白点"（原本独立）**连成一块**
- **为什么 3×3 迭代 1**：膨胀 1px + 腐蚀 1px → **够连间隙 2px 的白块**，但不会把相邻方块（间隙 > 10px）粘一起

#### 第 4 步：腐蚀（分离粘连）

```python
kernel_erode = np.ones((3, 3), np.uint8)
mask_closed = cv2.erode(mask_closed, kernel_erode, iterations=1)
```

- **目的**：反光可能让相邻方块或方块和卡图**粘连成一块**。腐蚀一次让它们**缩回独立**

#### 第 5 步：找轮廓

```python
contours, _ = cv2.findContours(mask_closed, cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_SIMPLE)
```

- **`RETR_EXTERNAL`**：只找最外层轮廓
- **`CHAIN_APPROX_SIMPLE`**：压缩轮廓点

#### 第 6 步：逐轮廓六重过滤

| # | 过滤 | 阈值 | 目的 |
|---|------|------|------|
| 1 | **边长** | 40~70 | 过滤格子框（81×77）和噪点 |
| 2 | **宽高比** | 0.75~1.35 | 过滤细长形状 |
| 3 | **四边形 + 凸** | 4 顶点 + 凸 | 过滤箭头/圆形/不规则 |
| 4 | **白占比** | 0.05~0.90 | 允许空心框 & 实心方块 |
| 5 | **内部黑** | ≥ 0.01 | 允许反光洗白的方块 |
| 6 | **灰度 std** | ≥ 15 | 排除纯白反光 |

**为什么 `SIDE_MIN=40 / SIDE_MAX=70`**：定位方块约 56×56，格子框 81×77，取 70 就能区分。

**为什么 `INNER_BLACK_MIN=0.01`**：非常宽松，允许反光把黑心洗白的方块（只要求"不完全白"）。

#### 第 7 步：象限筛选

```python
def filter_by_quadrant(marks, rect):
    """每个象限只保留 1 个最靠角的方块。"""
```

把 ROI 分成 2×2 象限：

```
┌─────────┬─────────┐
│   tl    │   tr    │
├─────────┼─────────┤
│   bl    │   br    │
└─────────┴─────────┘
```

**每象限只保留"离该象限角最近"的 1 个方块** → 防止多候选落在同一象限 → 保证共 4 个。

---

## 三、卡片放置格子定位

### 第 1 步：4 角分配

```python
def assign_corners(marks, roi_x0=0, roi_x1=None):
```

4 个方块按位置分配到 `tl / tr / br / bl`：

| 情况 | 处理 |
|------|------|
| **4 个方块** | 按 x/y 中位数分四象限 |
| **3 个方块** | 同上，缺 1 个 |
| **2 个方块同列** | 判断在 ROI 左半还是右半，往另一边推 |
| **2 个方块同行** | 同上 |
| **2 个对角** | 无法推算，报错 |
| **< 2 个** | 报错 |

**2 点同列的推算**：

```python
player_h = bot_pt['cy'] - top_pt['cy']
player_w = player_h * PLAYER_AREA_W_H_RATIO   # 0.42

col_x = (top_pt['cx'] + bot_pt['cx']) / 2
mid_x = (roi_x0 + roi_x1) / 2
if col_x > mid_x:    # 右列 → 往左推
    tl_x = top_pt['cx'] - player_w
else:                # 左列 → 往右推
    tr_x = top_pt['cx'] + player_w
```

**`PLAYER_AREA_W_H_RATIO = 0.42`**：玩家区宽/高比。

### 第 2 步：用平行四边形约束推缺失角

4 个方块构成平行四边形，对角线中点相同：

```
TL + BR = TR + BL
```

缺一个角时：

```
missing = other1 + other2 - opposite
```

**例**：缺 BR，已知 TL、TR、BL：

```
BR = TR + BL - TL
```

**这个公式对透视投影也近似成立**。

### 第 3 步：透视变换（Homography）

```python
src = np.float32([tl, tr, br, bl])          # 画面上的 4 个角
r = SRC_CORNER_RATIO                         # 0.043
dst = np.float32([[r, r], [1-r, r], [1-r, 1-r], [r, 1-r]])
H = cv2.getPerspectiveTransform(src, dst)
inv_H = cv2.getPerspectiveTransform(dst, src)
```

**核心**：用 H 矩阵把画面坐标 → 正空间（0~1）。正空间里玩家区是标准矩形。

**`SRC_CORNER_RATIO = 0.043`**：

- 4 个方块在玩家区的 4 个角，但**方块本身有大小**
- **方块中心 ≠ 玩家区边缘**
- 从截图量：方块高 46px / 玩家区高 537px → 23/537 ≈ 0.043
- 所以 4 个方块在正空间的 `(0.043, 0.043)`、`(0.957, 0.043)`、`(0.957, 0.957)`、`(0.043, 0.957)`

### 第 4 步：正空间切 7×3 网格

```python
x0, x1 = r, 1 - r       # 0.043 ~ 0.957
y0, y1 = r, 1 - r
cell_w = (x1 - x0) / 3  # 3 列
cell_h = (y1 - y0) / 7  # 7 行
```

**网格范围 `[r, 1-r]`**，避开方块本身。

**布局定义**：

```python
LEFT_LAYOUT = [
    (1, 1, "额外卡组", None), (1, 2, "场地魔法", None), ...
    (3, 3, "EX", 1),
    (5, 3, "EX", 2),
    ...
]
```

每个格子写明 `(row, col, 类型, 编号)`。

### 第 5 步：判断点击位置

```python
# 1. 映射到正空间
norm = cv2.perspectiveTransform(np.array([[[px, py]]], np.float32), H_left)
nx, ny = norm[0, 0]

# 2. 检查是否在 0~1 范围内
if 0 <= nx <= 1 and 0 <= ny <= 1:
    # 3. 查哪个格子包含 (nx, ny)
    for region in left_regions:
        if region['x0'] <= nx <= region['x1'] and \
           region['y0'] <= ny <= region['y1']:
            return region
```

**输出**：`Player1(左) | 前场 | 第 2 号`

---

## 四、为什么这套算法鲁棒

### 定位方块识别

| 挑战 | 应对 |
|------|------|
| 屏幕反光 | CLAHE clipLimit=4.0 压制过曝；`inner_black ≥ 0.01` 允许洗白；`std ≥ 15` 排除纯白 |
| 空心框/实心框混用 | `WHITE_RATIO ∈ [0.05, 0.90]` |
| 格子框误检 | `SIDE_MAX=70` 过滤 |
| 方块粘连 | 腐蚀 1 次分离 |
| 多候选项 | 象限筛选，每象限 1 个 |

### 格子定位

| 挑战 | 应对 |
|------|------|
| 画面旋转/透视 | 用 4 个方块算 Homography，把歪四边形拉正 |
| 只检出 3 个方块 | 平行四边形约束推第 4 个 |
| 只检出 2 个方块 | 用 `PLAYER_AREA_W_H_RATIO` 推算另一列 |
| 方块中心 ≠ 玩家区边缘 | `SRC_CORNER_RATIO=0.043` 补偿 |

---

## 五、关键参数说明

| 参数 | 值 | 含义 |
|------|-----|------|
| `WHITE_MIN_V` | 120 | HSV V 通道下限（白色亮度） |
| `WHITE_MAX_S` | 160 | HSV S 通道上限（允许偏色） |
| `CLAHE_CLIP` | 4.0 | CLAHE 对比度限制（压制反光） |
| `SIDE_MIN/MAX` | 40 / 70 | 方块边长范围（过滤格子框） |
| `SQUARE_MIN/MAX` | 0.75 / 1.35 | 宽高比范围（正方形） |
| `WHITE_RATIO_MIN/MAX` | 0.05 / 0.90 | 白像素占比范围 |
| `INNER_BLACK_MIN` | 0.01 | 内部区域黑像素占比下限 |
| `STD_MIN` | 15 | 灰度标准差下限 |
| `ERODE_KERNEL` | 3 | 腐蚀核大小 |
| `PLAYER_AREA_W_H_RATIO` | 0.42 | 玩家区 宽/高 比 |
| `SRC_CORNER_RATIO` | 0.043 | 定位方块在正空间里的内缩比例 |
| `GRID_ROWS/COLS` | 7 / 3 | 网格行数和列数 |

---

## 六、数据流

```
输入图像 (BGR)
    ↓
① 灰度化 + CLAHE
    ↓
② HSV 阈值 + 灰度阈值 → mask_white
    ↓
③ 闭运算（连接内部破碎） + 腐蚀（分离粘连）
    ↓
④ 找轮廓
    ↓
对每个轮廓：
    边长 40~70？
    宽高比 0.75~1.35？
    四边形 + 凸？
    白占比 0.05~0.90？
    内部黑 ≥ 0.01？
    灰度 std ≥ 15？
    ↓
⑤ 象限筛选（每象限 1 个）
    ↓
每侧 4 个方块
    ↓
⑥ 4 角分配（含 2/3 点推算）
    ↓
⑦ 透视变换 H（画面 → 正空间）
    ↓
⑧ 在正空间按 7×3 切网格
    ↓
⑨ 点击 → H 映射 → 查格子
    ↓
输出：PlayerN | 类型 | 第 N 号
```