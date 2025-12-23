# Subtitle Extractor (视频硬字幕提取器)

一个高性能的视频硬字幕提取工具，基于 RapidOCR 和 OpenCV 开发。它利用多进程并行处理和图像差分技术，快速从视频中提取硬字幕并生成 `.srt` 文件。

## ✨ 特性

- **⚡ 高性能**：利用多进程 (Multiprocessing) 并行处理视频片段，大幅提升提取速度。
- **🧠 智能去重**：通过图像差分技术 (SSIM 简化版) 和文本相似度比对，自动过滤重复帧和微小变化的字幕。
- **🎯 精准 OCR**：集成 RapidOCR (ONNX Runtime)，提供高精度的中文/英文识别。
- **🛠 易于安装**：支持通过 `uv` 直接安装为系统全局工具。

## 📦 安装

本项目使用 [uv](https://github.com/astral-sh/uv) 进行依赖管理和打包。你可以直接将本项目安装为全局可用的命令行工具。

### 前置要求
- Python >= 3.13
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### 安装步骤

1. **克隆仓库**
   ```bash
   git clone [https://github.com/wangyingang/subtitle-extractor.git](https://github.com/wangyingang/subtitle-extractor.git)
   cd subtitle-extractor
   ```

2. 使用 uv 安装为全局工具 在项目根目录下运行：
   ```bash
   uv tool install .

   # 在开发调试期，使用如下命令可保持命令随时更新:
   uv tool install --editable .

   # 或者，如果你后续更新了代码，可以使用以下命令强制重新安装：
   uv tool install --force .
   ```

安装完成后，你可以在终端的任意位置直接使用 `subx` 命令。

### 使用方法

**基本用法**
```bash
subx /path/to/your/video.mp4
```
运行结束后，程序会在视频同级目录下生成一个与视频同名的 .srt 字幕文件。

**命令行参数**  
你可以通过 `subx --help` 查看所有可用参数：  

| 参数          | 默认值  | 说明                                    |
| ----------- | ---- | ------------------------------------- |
| video_path  | (必填) | 视频文件的路径。                              |
| --processes | 8    | 并行进程数。建议根据 CPU 核心数调整。                 |
| --crop      | 0.2  | 字幕区域截取比例（从底部向上）。`0.2` 表示截取底部 20% 的画面。 |
| --skip      | 15   | 采样跳帧数。数值越小识别越密，但速度越慢。                 |

**示例**  
1. 提取底部 20% 区域的字幕（默认）：
    ```bash
    subx ./movies/sample.mp4
    ```

2. 针对 16 核 CPU 优化，并截取底部 30% 的区域：
   ```bash
   subx ./movies/sample.mp4 --processes 16 --crop 0.3
   ```

### 开发指南

如果你想参与开发或调试：  
1. 同步依赖
   ```bash
   uv sync
   ```
2. 运行代码
   ```bash
   uv run main.py ./test_video.mp4
   ```

### License
MIT License