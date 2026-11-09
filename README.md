# FFmpeg Studio (FFmpeg 视频工具箱)

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%20x64-0078D6?style=for-the-badge&logo=windows" alt="Platform" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/GUI-PySide6%20%7C%20Qt6-41CD52?style=for-the-badge&logo=qt&logoColor=white" alt="PySide6" />
  <img src="https://img.shields.io/badge/Engine-FFmpeg%20%2B%20PyAV-007808?style=for-the-badge&logo=ffmpeg&logoColor=white" alt="FFmpeg" />
  <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License" />
</p>

<p align="center">
  <b>专为大疆航拍、运动相机、手机及相机创作者打造的高性能现代化桌面音视频生产力工具箱。</b><br>
  集批量1080p智能压制、Exif元数据保护、关键帧吸附极速无损裁剪、社交媒体智能分段、预裁剪无损拼接于一体。
</p>

---

## 快速下载 (开箱即用)

无需安装 Python，无需手动配置复杂的 FFmpeg 与 ExifTool 环境变量：

👉 **[前往 GitHub Releases 下载最新便携版 (FFmpegStudio-v1.0.0-windows-x64.zip)](https://github.com/cuicui-V5/ffmpeg-studio/releases/latest)**

> **便携版包含：**
> * 编译优化版 `FFmpegStudio.exe` 主程序；
> * 完整内置最新的 `ffmpeg.exe`、`ffprobe.exe`、`ffplay.exe` 与 `exiftool.exe`；
> * 解压至任意文件夹，双击即可直接运行，无任何外部环境依赖。

---

## 核心功能特色

### 1. 批量压制 (4K 智能转码 1080p & 元数据完整保护)
* **画质与体积的极致平衡**：针对 DJI 4K/60fps、GoPro、手机等超大高码率素材，默认配置精调转码参数（1080p, CRF 22, preset medium, AAC 192k），画质肉眼无损，体积缩减 70%~90%。
* **硬件加速智能探测**：启动时自动诊断 NVIDIA NVENC 硬件加速器 (`hevc_nvenc` / `h264_nvenc`)，未装独显或驱动异常时智能回退至 CPU (`libx265` / `libx264`)，稳定不崩溃。
* **ExifTool 拍摄元数据保护**：集成 ExifTool 提取原片的拍摄时间、相机型号、镜头参数、GPS 经纬度等所有 Exif/QuickTime 标签，并在压制后自动回写，保证导入手机相册时时间线、地理位置完全正确，永不紊乱。
* **批量自动化管理**：支持多文件拖拽、整个目录递归扫描导入、实时并发压制队列、处理速率与剩余时间动态预估。

### 2. 视频裁剪 (关键帧吸附免重编码无损剪辑)
* **关键帧吸附（Keyframe Snapping）**：内置 PyAV 关键帧解析器，剪切起止点自动吸附至最近的 I 帧（关键帧），杜绝免重编码剪辑常见的首段黑屏、画面卡顿或音画不同步问题。
* **双模式自由切换**：
  * **极速无损模式 (`-c copy`)**：无需重新编码，几秒内即可导出数 GB 大小的选区。
  * **帧精确重编码模式**：毫秒级精确定位，保证选区严格切分。
* **双滑块区间选择器**：支持起始/结束点直观拖拽选择、微调按钮与快捷键联动。

### 3. 视频分段 (社交平台传输利器)
* **各大社交媒体规则预设**：内置 QQ（普通用户 1GB、VIP 2GB、SVIP 3GB）与微信文件发送阈值规则。
* **智能分段切分规划**：输入单个超长或超大视频，自动根据文件体积计算最优分段数，各切分点自动吸附关键帧，使用免重编码快速切出子段，方便一键分享。

### 4. 视频合并 (参数自动校验 & 预裁剪无损拼接)
* **参数一致性智能体检**：自动解析并对比列表中所有片段的视频编码、分辨率、帧率、音频采样率、声道数。当所有参数完全契合时，自动点亮绿色无损合规标识。
* **自由拖拽排序**：支持通过鼠标直接拖拽表格行上下移动，快速调整拼接顺序。
* **独家单片预裁剪 (Pre-crop & Merge Pipeline)**：
  * 无需先手动把每个素材裁剪另存为新文件再重新导入；
  * 点击列表中的「裁剪」按钮，即可呼出快速裁剪弹窗，选定该片段所需保留的区间；
  * 点击「开始合并」后，后台流水线自动采用 `-avoid_negative_ts make_zero` 极速预裁出临时切片，并立即调用 Concat Demuxer 进行无损拼合，完成后自动清理临时文件，一气呵成。

### 5. 环境诊断
* 全自动探测本地系统或自带运行包中的 `ffmpeg`、`ffprobe`、`ffplay` 与 `exiftool` 版本及健康状况。
* 测试并持久化显卡硬件加速支持方案，避免重复探测开销。

---

## 性能与架构优化

| 优化技术 | 实现细节 | 带来提升 |
| :--- | :--- | :--- |
| **启动骨架屏 (Splash Screen)** | 采用轻量化原生组件直接绘制 Dark 主题加载卡片与进度动画 | **< 80ms** 瞬间弹出启动反馈，彻底消除启动停顿感 |
| **选项卡延迟加载 (Lazy Loading)** | 启动时仅初始化首个选项卡，其余选项卡通过 `_step_preload_tabs` 微队列在空闲时静默预加载 | 内存占用降低 60%，主窗口秒开即用 |
| **端点关键帧短路扫描** | 针对起始点 0s 与视频末尾点实施 0 耗时边界短路判定 | 规避遍历全文件 Packet，弹窗时间从 1.5s 骤降至 **0.02ms** |
| **异步解码工作线程** | 视频预览组件采用后台独立 `VideoLoadWorker(QThread)` 异步拉流解帧 | 界面无假死无冻结，无缝展示呼吸加载动效 |

---

## 源码开发与构建

### 1. 环境准备
确保已安装 Python 3.10 或更高版本：
```bash
# 克隆仓库
git clone https://github.com/cuicui-V5/ffmpeg-studio.git
cd ffmpeg-studio

# 安装 Python 依赖
pip install -r requirements.txt
```

### 2. 放置外部二进制工具 (若源码运行)
将 Windows 平台的以下可执行文件放置在项目根目录下：
* `ffmpeg.exe`
* `ffprobe.exe`
* `ffplay.exe`
* `exiftool.exe` 以及 `exiftool_files/`

### 3. 启动应用
```bash
python gui_main.py
```

### 4. 使用 PyInstaller 打包独立程序
项目已包含预配置的 `FFmpegStudio.spec` 打包规则：
```bash
# 安装 pyinstaller
pip install pyinstaller

# 一键打包
pyinstaller FFmpegStudio.spec
```
打包输出目录位于 `dist/FFmpegStudio`，将外部二进制工具拷贝至该目录下即可直接分发。

---

## 项目结构

```
ffmpeg-studio/
├── core/                       # 核心业务逻辑与后台处理任务
│   ├── tasks/                  # 任务工作线程与数据结构
│   │   ├── compress_task.py    # 批量压制与 ExifTool 元数据处理
│   │   ├── cutter_task.py      # 视频裁剪与关键帧切分
│   │   ├── split_task.py       # 智能分段逻辑与平台预设
│   │   └── merge_task.py       # 视频合并、一致性校验与预裁剪拼接管道
│   ├── hardware.py             # 显卡硬件加速探测与缓存
│   ├── keyframe_helper.py      # 基于 PyAV 的高性能关键帧索引
│   └── tool_manager.py         # 外部工具链查找与自检
├── ui/                         # PySide6 图形界面层
│   ├── components/             # 复用组件 (播放器、范围滑块、启动屏等)
│   ├── dialogs/                # 弹窗模块 (单视频裁剪对话框等)
│   ├── tabs/                   # 各功能选项卡模块
│   └── main_window.py          # 主窗口容器与懒加载调度器
├── FFmpegStudio.spec           # PyInstaller 编译工程文件
├── gui_main.py                 # 程序入口
├── requirements.txt            # Python 依赖项清单
└── README.md                   # 项目使用与技术说明文档
```

---

## 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。

感谢开源社区中 **FFmpeg**、**PySide6 / Qt**、**PyAV** 与 **ExifTool** 等杰出项目的支持！
