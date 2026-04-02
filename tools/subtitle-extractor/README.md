# subtitle-extractor

`subx` 是一个面向硬字幕视频的命令行工具，当前面向最终用户只保留一个能力：从单个视频提取字幕并输出 `.srt`。

仓库内另提供 `subx-dev`，只用于研发阶段的样本评估和性能基准，不属于最终用户主命令界面。

## 环境

- Python `3.12.x`
- 推荐使用 `uv`

安装依赖：

```bash
uv sync
```

安装命令行工具：

```bash
uv tool install --editable .
```

## CLI

提取字幕：

```bash
subx ./video.mp4 --engine paddle --lang mixed
```

使用 ONNX 候选后端：

```bash
subx ./video.mp4 --engine onnx --lang zh --roi 0.1,0.78,0.8,0.18
```

## 仓库内评估命令

评估样本集：

```bash
subx-dev eval ./samples --engine paddle --json ./eval.json --report ./eval.md
```

如需做受控对比，再显式使用 `--engine all` 或 `--engine onnx`；当前推荐默认路径仍是 Paddle。

性能基准：

```bash
subx-dev bench ./samples --engine paddle --json ./bench.json
```

## 样本格式

每个样本目录使用以下结构：

```text
samples/<sample_id>/
  clip.mp4
  truth.srt
  meta.json
```

`meta.json` 的最小格式：

```json
{
  "lang": "mixed",
  "tags": ["bilingual", "double-line", "bottom-centered"]
}
```

可选加入：

```json
{
  "lang": "zh",
  "roi": [0.1, 0.78, 0.8, 0.18],
  "tags": ["single-line", "light-text-dark-bg"]
}
```

## 当前实现说明

- 主默认后端是 PaddleOCR，目标模型配置是 `PP-OCRv5_server_det + PP-OCRv5_server_rec`
- Paddle v5 模型通过 Hugging Face Hub 下载，并默认复用 `~/.cache/huggingface/hub` 下的 snapshot cache
- ONNX 候选后端优先使用 [monkt/paddleocr-onnx](https://huggingface.co/monkt/paddleocr-onnx)
- `subx` 只保留最终用户的提取入口；`subx-dev` 承接仓库内评估与基准命令
- 当前样本基线已优先验证 Paddle；ONNX 仍是候选路线，因为现阶段在已测样本上没有表现出更好的速度或准确率
- 当前已完成 Paddle 全样本基线；在已测英文样本上，ONNX 相比 Paddle 同时更慢且更差
- 处理流水线是“顺序解码 + ROI 变化检测 + OCR 工作池”，不再按视频分段多进程重复解码
- 纯函数测试位于 `tests/`，不依赖真实 OCR 模型
