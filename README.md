# Gemini Catgirl 2D Desktop Pet (Gemini 猫猫桌宠)

一个基于 **Python + PySide6 + OpenCV** 打造的 2D Windows 透明桌面宠物，以 Gemini 猫娘形象为主题，内置 60FPS 实时 2D 网格变形微动画、连续撸猫互动与作息提醒。

## 核心特性

- **60FPS 实时活体微动画**（[pet/live_deformer.py](pet/live_deformer.py)）
  - 默认趴桌姿势支持 **3 阶段自然眨眼**（睁眼 → 半闭 → 闭眼，随机双眨眼）、**猫尾波浪摆动**、**双脚悠闲晃动**、**左右猫耳独立抖动**、**呆毛与发丝微风摆动**。
  - **鼠标眼神微跟随**：光标靠近时，头部轻微转向且异色瞳虹膜微微看向鼠标。
  - **说话口型同步**：对话气泡弹出时自动同步嘴部开合动画。
- **自然互动体验**
  - **连续撸猫抚摸**：鼠标在猫耳/头顶来回轻抚，原地融化为眯眼小虎牙开心表情、加快摇尾并飘出爱心与星芒。
  - **9 套独立猫猫姿势**：趴桌晃脚、眨眼双猫爪、摸头呼噜噜、猫猫爪爪洗脸、蹲扑四角星、害羞鸭子坐、抱尾打盹、踮脚伸懒腰、拎猫悬空，切换采用 0.26s 缓动交叉淡入过渡。
  - **拖拽钟摆物理 & 滚轮无级缩放**：自由拖动（带衣领支点摆动物理）、滚轮缩放并支持 Windows HiDPI 高清渲染。
- **贴心作息与学习提醒**
  - 支持自定义午餐、晚餐、睡觉定时提醒，以及学习/专注间隔休息提醒，附带系统托盘通知与可视化设置面板。

## 快速开始

### 环境要求
- Windows 10 / 11
- Python 3.10+

### 安装与运行
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```
或者直接双击项目根目录的 `start_pet.bat` 无黑框启动。

## 项目结构
```text
├── main.py                  # 启动入口与系统托盘
├── start_pet.bat            # Windows 无黑框一键启动脚本
├── requirements.txt         # 依赖列表
├── assets/                  # 高清透明立绘与面部微动画层
├── pet/
│   ├── pet_window.py        # 主透明窗口、交互状态机与渲染循环
│   ├── live_deformer.py     # 基于 OpenCV remap 的 2D 网格微变形引擎
│   ├── bubble.py            # 悬浮磨砂对话气泡
│   ├── particles.py         # 四角星 / 爱心 / Zzz 粒子特效
│   ├── reminder.py          # 吃饭/睡觉/学习提醒与设置弹窗
│   ├── dialogue.py          # 台词与提醒文案
│   └── config.py            # 本地配置读写
└── tools/                   # 绿幕抠图与面部像素对齐脚本
```
