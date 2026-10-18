## 投影端功能

- 战场网格
- 游戏阶段
    阶段切换动画
- 放置卡牌的位置播放光圈
- 场地大图片（半张）
- 显示召唤动画
- 双方LP
- 卡牌关联连线
- 攻击连线
- 攻击动画
- 破坏动画

## 图像识别功能

- 识别卡牌位置
    yolo
- 识别卡牌方向
    yolo
- 识别卡牌正反
    根据yolo返回的卡牌框使用 opencv 识别
- 识别卡牌内容
    draw2

## PAD端功能

- 导入双方ydk卡组信息
- 显示战场情况
- 设置“这里有一张卡”，给识别错误容错
- 清除“这里有一张卡”，给识别错误容错
- 显示卡牌详情
- 显示LP
- 切换阶段
- 播放召唤动画
- 播放破坏动画
- 设置卡牌信息
    卡名
    攻击力
    防御力
    星
    阶
    箭头
    属性
    种族
- 增加/删除卡片标记
    无效
    永续
    装备
- 添加/删除/修改指示物
    种类
    数量
- 攻击指令
- 设置卡牌关联
- 播放BGM
- 播放音效

- 设置识别置信度

## 环境记录

```
conda create -n ygodesk python=3.12
conda activate ygodesk
```

```
pip install pydantic>=2.7.0
pip install ultralytics
pip install onnxruntime
pip install onnxruntime-gpu
```


如果cuda找不到
```
# 1. 卸载 CPU 版（如果同时有 conda 装的，也一并清理）
pip uninstall torch torchvision torchaudio -y

# 2. 安装 CUDA 12.4 版本（3060 Ti 完全兼容）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```