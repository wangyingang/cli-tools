# 项目级 AGENTS.md

本文件补充上层全局 `AGENTS.md`，只记录当前仓库特有且稳定的信息。

## 项目结构

- `src/subx/cli.py`：`subx` CLI 入口，只提供最终用户的单视频字幕提取。
- `src/subx/dev_cli.py`：`subx-dev` CLI 入口，提供仓库内部使用的 `eval`、`bench` 子命令。
- `src/subx/pipeline.py`：视频采样、ROI 变化检测、OCR 调度、字幕合并主流程。
- `src/subx/ocr/`：OCR backend 抽象和实现，当前包含 Paddle 与 ONNX 两条路线。
- `src/subx/eval.py`：样本集加载、指标计算、Markdown/JSON 报告输出。
- `tests/`：ROI、SRT、文本相似度、评估指标等纯函数测试。
- `samples/`：评估样本目录，包含 `clip.mp4`、`truth.srt`、`meta.json`。
- `pyproject.toml`：项目元数据、依赖和 `subx = "subx.cli:main"` 命令入口。
- `README.md`：安装、CLI、样本格式说明。

## 技术架构

- 这是一个 `src` 布局的 Python CLI 项目，目标运行时是 Python `3.12.x`。
- 主默认 OCR backend 是 PaddleOCR，目标模型配置是 `PP-OCRv5_server_det + PP-OCRv5_server_rec`。
- ONNX 候选 backend 通过 `rapidocr-onnxruntime` 加载 Hugging Face 上的 `monkt/paddleocr-onnx` 模型文件。
- 视频处理主线是：顺序解码 -> ROI 裁剪 -> 图像差分筛候选帧 -> OCR 工作池 -> 文本去重与时间补偿 -> `.srt` 输出。
- `eval`/`bench` 共享同一套提取流水线，只是在输出侧分别做准确率评估和性能统计。

## 运行方式

- 安装依赖：`uv sync`
- 安装命令行工具：`uv tool install --editable .`
- 单视频提取：`subx /path/to/video.mp4`
- 样本评估：`subx-dev eval ./samples --engine paddle`
- 性能基准：`subx-dev bench ./samples --engine paddle`
- 如需受控对比，再显式使用 `--engine all` 或 `--engine onnx`；当前推荐默认路径仍是 Paddle

## 常用命令

- `build`：通过 `uv tool install --editable .` 验证可安装的 `subx` 入口。
- `test`：`PYTHONPATH=src python3 -m unittest discover -s tests -v`
- `lint`：当前没有独立 lint/format 配置。

## 项目约束

- 最终可执行入口必须保持为 `subx`。
- `subx` 只服务最终用户提取场景；评估和基准命令应留在 `subx-dev` 这类仓库内部入口，而不是继续暴露在 `subx` 下。
- 当前 CLI 已不做向后兼容；新增最终用户参数优先加到 `subx` 顶层选项，评估类参数优先放在 `subx-dev` 子命令下。
- `meta.json` 中的 `roi` 是可选的；评估逻辑必须支持使用统一默认 ROI。
- `mixed` 语义是“中英混合识别配置”，不是严格语言检测结果。
- ONNX 只是一条候选 backend；只有在准确率不明显退化且性能更好时才应成为默认路线。
- 当前主线基线和推荐评估路径都以 Paddle 为准；继续推进 ONNX 时应先有明确调优假设，再做受控对比。

## 协作分工

- 主 agent：使用 `gpt-5.4`，`reasoning_effort=high`。负责整体实施顺序、阶段切换、阻塞处理、合并各子 agent 结果，并持续维护根目录 `PLANS.md` 的 `Progress`、`Decision Log`、`Surprises & Discoveries`。
- 评估子 agent：使用 `gpt-5.4`，`reasoning_effort=high`。只负责 `samples/`、`subx-dev eval` / `subx-dev bench`、指标解释、基线对比和样本覆盖建议。
- 实现子 agent：优先使用 `gpt-5.4-mini`。只负责明确边界内的代码实现，不主导产品决策。
- 测试子 agent：优先使用 `gpt-5.4-mini`。只负责 `tests/`、验证命令、失败复现与修复建议，不主导产品设计或 OCR 选型。
- 文档子 agent：优先使用 `gpt-5.4-mini`。只负责 `README.md`、`AGENTS.md`、必要时按主 agent 指令同步 `PLANS.md` 的非决策性内容。
- 多 agent 并行时避免同时改同一文件；主 agent 负责拆分写入范围、收敛冲突和最终验收。
- 只有主 agent 可以修改 `PLANS.md` 中的决策性内容并拍板默认 backend；评估子 agent 提供结论和证据，但不单独做最终产品决策。
- 每个可暂停节点都要先回写 `PLANS.md`，再结束当前工作。
