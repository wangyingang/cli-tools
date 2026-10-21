# subx 重构与评估执行计划

本 ExecPlan 是一个 live 文档。后续新开 thread 并使用多 agent 实施时，必须持续更新 `Progress`、`Surprises & Discoveries`、`Decision Log` 与 `Outcomes & Retrospective`，让后来接手的人只靠当前工作树和这份文件就能继续推进。

当前仓库以本文件作为唯一的项目级执行计划。后续如果阶段完成并归档，应迁移到 `docs/archive/`，而不是把已完成的计划长期留在根目录。

## Purpose / Big Picture

目标是把当前项目重构为一套职责清晰的命令行接口：`subx` 只面向最终用户做硬字幕提取，仓库内部的样本评估和性能基准则转移到独立的 `subx-dev`。用户最终应能稳定执行 `subx <video>` 完成提取；研发阶段则通过 `subx-dev eval` / `subx-dev bench` 真实比较 PaddleOCR 主路线与 ONNX 候选路线，而不是靠主观印象判断 OCR 质量和性能。

这项工作的用户价值有三点。第一，字幕提取流程需要从“单脚本试验品”升级为可维护的包结构。第二，OCR 路线需要通过样本和指标来选，而不是只根据模型名称或框架假设。第三，后续工作将使用多 agent 并行推进，因此必须把当前上下文、冻结点和分工写清楚，避免新线程重复踩坑。

## Progress

- [x] (2026-04-02) 已将项目从单文件脚本重构为 `src/subx` 包结构，并把控制台入口切到 `subx = "subx.cli:main"`。
- [x] (2026-04-02) 已落地提取、评估、基准三条工作流的 CLI 骨架，以及 ROI、SRT、评估指标和 OCR backend 抽象。
- [x] (2026-04-02) 已补充 `samples/` 样本格式支持，`meta.json` 当前使用 `lang` 和 `tags`，`roi` 仍为可选字段。
- [x] (2026-04-02) 已在 Python 3.12 环境下执行 `uv sync`，并更新 `uv.lock`。
- [x] (2026-04-02) 已通过纯函数测试：`uv run --python 3.12 python -m unittest discover -s tests -v`。
- [x] (2026-04-02) 已完成 Paddle smoke test：`subx samples/zh_single_dark/clip.mp4 --engine paddle --lang zh --workers 1 --sample-every 6` 跑通并产出 `/tmp/subx-zh-paddle.srt`。
- [x] (2026-04-02) ONNX smoke test 已闭合：`subx samples/zh_single_dark/clip.mp4 --engine onnx --lang zh --workers 1 --sample-every 6` 最终可完成，产出 3 条 cue，`elapsed_seconds≈224.34`；原冻结点已从“疑似 hang”改判为“顺序 OCR 极慢且阶段可观测性不足”。
- [x] (2026-04-02) 已将 ONNX 冻结点缩小到 OCR 阶段：`OnnxBackend('zh')` 与单张 ROI 的 `recognize()` 都能返回，当前主要问题是 `workers=1` 时 OCR 每帧约 5.7 到 11.5 秒，导致采样后出现数分钟静默。
- [x] (2026-04-02) 已给 `_run_ocr()` 增加 `OCR (engine)` 进度条，避免 ONNX 长耗时阶段表现成“采样后假死”。
- [x] (2026-04-02) 已在当前 thread 启动多 agent 执行，并按本文分工推进测试、评估和主线收敛。
- [x] (2026-04-02) 已量化 ONNX 在 `workers>1` 下的真实样本吞吐：`workers=2` 仅把 `zh_single_dark` 从 `224.34s` 降到 `209.95s`，收益约 `6.4%`，不足以支撑直接进入 `--engine all` 的全量评估。
- [x] (2026-04-02) 已完成 Paddle 的真实样本级基线评估，并产出根目录 `eval-paddle.json` / `eval-paddle.md`。
- [x] (2026-04-02) 已完成 ONNX 的受控单样本对比：`en_double_bright` 上 ONNX 比 Paddle 更慢且精度更差，当前没有证据支持扩大 ONNX 评估范围。
- [x] (2026-04-02) 已根据现有评估结果确认默认 backend 继续维持 Paddle，并同步 README / AGENTS 中的推荐使用路径。
- [x] (2026-04-02) 已将最终用户命令与研发命令拆分：`subx` 只保留提取，`eval` / `bench` 迁移到 `subx-dev`。
- [x] (2026-04-02) 已验证新命令边界可用：`subx --help` 只显示提取参数，`subx-dev --help` 显示 `eval` / `bench`，两条轻量 smoke test 均成功返回。
- [x] (2026-04-02) 已按 TDD 修复单 worker 分批 OCR 的重复初始化问题：新增失败测试后，确认同一次提取跨多个批次时只初始化一次 backend。
- [x] (2026-04-02) 已按 TDD 压掉 Paddle 初始化与批次级 OCR 噪音：新增失败测试后，`subx` 轻量 smoke run 只显示 `Sampling` 和最终 JSON，不再向最终用户泄露 Paddle 系统提示或多段 `OCR (...)` 进度条。
- [x] (2026-04-02) 已按 TDD 把 Paddle `PP-OCRv5_server_det/rec` 收口到 Hugging Face snapshot cache：backend 现在显式通过 `huggingface_hub.snapshot_download(...)` 拉取模型，并把本地 snapshot 目录传给 PaddleOCR，而不是继续依赖 PaddleX 的隐式 `model_name` 下载路径。
- [x] (2026-04-02) 已按 TDD 把用户侧进度收口为单一 `Extracting` reporter：采样与 OCR 共用一条总体进度信号，不再显示分阶段或批次级第二进度条。
- [x] (2026-04-02) 已按 TDD 修复多 worker 的主性能瓶颈：`workers>1` 时 OCR 进程池现在会在同一次提取中跨多个 flush 复用，而不是每 64 帧批次重建一次。
- [x] (2026-04-02) 已按 TDD 新增低风险 OCR 候选二次筛选：通过 `ocr_candidate_similarity_threshold` 过滤与上一张已提交候选过于相似的帧，减少 `submitted_ocr_frames` 且不破坏 cue 连续性。
- [x] (2026-04-02) 已在默认采样路径上增加 150ms 的内部 OCR 去抖：对 `sample_every > 1` 的连续变化段，不再每个采样点都提交 OCR；真实 `subx-dev eval ./samples --engine paddle` 验证显示 `ocr_calls` 从 `7/91/57` 降到 `7/49/36`，`CER/WER` 保持不变，`mixed_double_dark` / `zh_single_dark` 的样本耗时也进一步下降。
- [x] (2026-04-02) 已补做默认 Paddle 路径的真实长视频短时验证：`/Users/wangyg/Downloads/RBD-648-UC/RBD-648-UC.compressed.mp4` 在约 `1m47s` 时推进到 `4586/438955`，仍为单一 `Extracting` 进度条，且未再出现“先预估最大采样步数、采样结束后回缩总量”的错位表现。
- [x] (2026-04-02) 已把单一 `Extracting` 进度条改成“真实 frame_count 起步 + 按实际排队 OCR 工作增长”：当前长视频默认路径起始总量从旧的 `438955` 收口到 `329216`，短时观测中总量会随真实 OCR 队列增长到 `329536`，不再预先把“最大采样上限”算进总量。
- [x] (2026-04-02) 已把非采样帧从 `read()` 全量解码改成 `grab()`，只在采样点和末帧 `retrieve()`：真实长视频前缀 `12000` 帧基准在保持 `sampled/submitted/reused` 不变的前提下，从 `33.602s` 降到 `15.987s`。
- [x] (2026-04-02) 已把提交 OCR 时的 ROI 准备收口为“只做必要 resize，不重复灰度化/模糊化”：`_collect_checkpoints()` 现在复用 `_prepare_roi_gray()` 的判定结果，只在真正提交 OCR 时再走 `_prepare_ocr_frame()`；`uv run --python 3.12 python -m unittest discover -s tests -v` 的 32 个测试通过，且 `subx samples/zh_single_dark/clip.mp4 --engine paddle --lang zh --workers 1 --sample-every 180` smoke 成功结束，产出 `/tmp/subx-post-ocr-frame-path.srt`。
- [x] (2026-04-02) 已用真实长视频前缀基准验证“提交路径去掉重复灰度化”的实际收益：在 `/Users/wangyg/Downloads/RBD-648-UC/RBD-648-UC.compressed.mp4` 的前 `12000` 帧、`4000` sampled frame、`1040` submitted frame 上，模拟旧实现 `old_dup_gray` 3 轮均值 `12.457s`，当前实现 3 轮均值 `12.273s`，计数保持一致，平均快 `0.183s`（约 `1.47%`）；这说明优化方向成立，但收益幅度较小。
- [x] (2026-04-02) 已把“采样判定用的 resize 结果”直接复用于提交 OCR 的彩色 ROI，避免 submitted frame 再做一次 resize：`_collect_checkpoints()` 现在先 `_resize_roi_frame()`，再基于同一张 `prepared_roi_frame` 做灰度判定和 OCR 提交；`uv run --python 3.12 python -m unittest discover -s tests -v` 的 32 个测试通过，`subx samples/zh_single_dark/clip.mp4 --engine paddle --lang zh --workers 1 --sample-every 180` smoke 也成功结束并产出 `/tmp/subx-post-resize-reuse.srt`。
- [x] (2026-04-02) 已完成两条解码侧候选路线的受控排除：`CAP_PROP_CONVERT_RGB=0` 的灰度解码在前缀基准里更快，但会改变候选判定并在样本评估中造成 `WER` 回退；`CAP_PROP_HW_ACCELERATION` 在本机 OpenCV/FFmpeg 组合上全部 `set_ok=False`，当前不能作为可落地方案。
- [x] (2026-04-02) 已启动 Apple Silicon 加速路线评估，主目标从“继续微调当前 Paddle CPU 路径”切换为“验证是否可切到利用 Apple 硬件的实验后端”。
- [x] (2026-04-02) 已以官方 `PP-OCRv5_server_det/rec` 为唯一模型来源，完成 `Paddle -> ONNX -> ONNX Runtime + CoreMLExecutionProvider` 的技术可行性验证。
- [x] (2026-04-02) 已完成 Apple 路线 spike 命令 `subx-dev apple-spike`：当前可把官方 `PP-OCRv5_server_det/rec` 转为 ONNX，并验证 ORT session 的主 provider 命中 `CoreMLExecutionProvider`。
- [x] (2026-04-02) 已新增实验 engine `onnx-coreml`，当前依赖默认 cache 根 `/Users/wangyg/.cache/subx/onnx-coreml` 中的官方 ONNX 产物，只做受控评估，不改默认 backend。
- [x] (2026-04-02) 已为 `onnx-coreml` 加入内存保护：当前强制 `--workers 1`，避免多进程复制多份 CoreML det/rec session 把统一内存打满。
- [x] (2026-04-02) 已完成 Apple 路线的全样本评估；结果显示当前 `onnx-coreml` 在 `workers=1` 下 3/3 样本都慢于 Paddle，因此不再继续消耗时间跑长视频前缀 benchmark。
- [x] (2026-04-02) 已基于速度与精度门槛做出当前阶段决策：`onnx-coreml` 保留为实验 backend，但不保留为候选默认后端。
- [x] (2026-04-02) 已按最新决策终止 Apple/CoreML 实验路线：`onnx-coreml` 与 `apple-spike` 的活跃代码入口已移除，仓库主线重新回到官方 PaddleOCR。
- [x] (2026-04-02) 已排除“直接压低 Paddle det 输入边长”这条主线优化思路：`text_det_limit_side_len=192` 虽在 2 张 ROI 微基准里看似显著加速，但全样本评估出现英文精度回退，且 `mixed_double_dark` / `zh_single_dark` 的总耗时反而更差。
- [x] (2026-04-02) 已把默认内部 OCR 去抖从 `150ms` 收敛到 `200ms`：真实 `subx-dev eval ./samples --engine paddle --workers 1` 显示 3/3 样本 `overlap_hit_rate=1.0`，同时保住当前文本指标；更激进的 `250ms` 已明确拒绝。
- [x] (2026-04-02) 已排除“在当前 PaddleOCR 包装层上改用批量 `predict(list)` 调度”这条主线优化思路：`mixed_double_dark` 的 49 张候选上，`single_loop≈46.048s`、`batch_all≈46.032s`、`chunk_8≈45.959s`、`chunk_4≈46.207s`，没有形成值得引入复杂度的收益。
- [x] (2026-04-02) 已确认“默认 ROI 收窄到中心 70% 宽度”只在当前 `samples/` 上成立，不适合作为主线默认值：真实长视频前缀显示更窄 ROI 会让提交给 Paddle 的图像高度变大，并把单次 OCR 成本抬高，因此默认 ROI 已回退到全宽底部 `0,0.8,1,0.2`。
- [x] (2026-04-02) 已完成单行/双行字幕高度的第一轮实测，并新增结构化 ROI CLI：`subx` 现在支持 `--lines/-l`、`--width/-w`、`--height/-H`、`--bottom-offset/-b`；其中 `--lines` 默认 `single`，并会结合视频尺寸、ROI 宽度和 `1280` 宽上限反推高度，让进入 OCR 的实际像素高度贴近实测默认值。
- [x] (2026-04-02) 已把结构化 ROI 参数的命名、作用和默认值写入 `subx --help`，避免最终用户必须回看 README 才知道 `lines/width/height/bottom-offset` 的语义。
- [x] (2026-04-02) 已验证“按 prepared-height 反推 ROI 高度”确实消除了“缩窄宽度后 OCR 输入高度被动抬高”的副作用；在长视频前缀里，`width=0.7 + double` 与全宽默认都落到 `144x1280` 的同一 prepared shape，单张 OCR 成本也回到同一量级。
- [x] (2026-04-02) 已初步排除“把默认宽度收窄到 `0.8` 或 `0.85`”这条主线默认值方向：即便 prepared-height 反推逻辑已经消除缩放副作用，双行样本的精度仍然明显退化。
- [x] (2026-04-02) 已确认 `lines` 预设后续不应只控制默认高度，还应同时控制默认宽度：当前证据已显示单行和双行不仅高度需求不同，宽度安全区间也不同。
- [x] (2026-04-02) 已把 `lines` preset 落成两套默认宽高：当前 `single` 默认按 `width=0.75 + prepared_height≈100.8px`，`double` 默认按 `width=1.0 + prepared_height≈144px`；显式 `--width/--height` 仍然按需覆盖。
- [x] (2026-04-02) 已按“优先减少 OCR 调用次数、允许一定精度牺牲”的新目标，把默认内部 OCR 去抖从 `200ms` 提到 `225ms`。
- [x] (2026-04-02) 已把 `lines` preset 继续扩展到默认采样间隔：当前 `single` 与 `double` 默认都已收敛到 `sample_every=6`；显式 `--sample-every` 仍可覆盖。
- [x] (2026-04-02) 已确认仓库级 Python 版本默认就是 `3.12`：`pyproject.toml` 的 `requires-python` 与根目录 `.python-version` 都已收敛到 `3.12`，后续 `uv run` / `uv sync` 无需再显式带 `--python 3.12`。
- [x] (2026-04-02) 已完成“动态采样回退”受控实验，并确认这条路当前不应进入主线：全局启用会先打坏 `zh_single_dark`，即便只挂在 `sample_every=6` 的双行路径上，也没有形成优于固定采样的净收益。
- [x] (2026-04-02) 已重新基准当前 Paddle 多 worker 默认值：在现有 `samples/` 上，`workers=6` 明显快于 `1/2/4`，而 `workers=8` 开始出现回退，因此当前默认值已从 `4` 提到 `6`。
- [x] (2026-04-02) 已在真实长视频前 `12000` 帧前缀上复核 `workers=6`：当前默认单行结构化 ROI 下，`workers=6` 在保持 `sampled/submitted/reused` 完全一致的前提下，比 `workers=4` 再快约 `16.1%`。
- [x] (2026-04-02) 已补完双行默认采样间隔的继续上探：`double` 的 `sample_every=7/8` 虽然进一步减少采样帧，但会显著放大长视频前缀的 OCR 提交量，因此双行默认值继续保留在 `6`。
- [x] (2026-04-02) 已把默认 OCR 候选相似度门限从 `0.97` 下调到 `0.86`：当前单行/双行样本都未出现新的指标退化，同时长视频前缀的 OCR 提交量和单行 wall time 都继续明显下降；`0.85` 已确认为当前单行坏点。
- [x] (2026-04-02) 已确认双行路径可以比单行更激进地下调 OCR 候选相似度门限，并把这条差异固化到 `subx` 用户入口：当前 `single=0.86`、`double=0.8`；`double=0.75` 已明确退化。
- [x] (2026-04-02) 已在新门限默认下重试单行采样频率，并把 `subx` 的 `single` 默认 `sample_every` 从 `5` 提到 `6`：样本未退化，真实长视频前缀 wall time 也继续下降。
- [x] (2026-04-02) 已新增显式 `--speed-profile aggressive` 性能档位：当前只作用于 `single`，通过 entry-debounce 明显减少 OCR 提交；默认 `balanced` 保持原有精度优先路径。
- [ ] (2026-04-02) 后续性能工作重新聚焦官方 PaddleOCR 主线，只在 Paddle 路线下继续追求更短运行时间与更低系统开销。
- [x] (2026-04-02) 已补完 `width=0.9`、`width=0.95` 与更高 double prepared-height 的受控对比；当前结论是 `single` 可安全更窄，而 `double` 在速度优先约束下仍应保持全宽基线。
- [ ] 如后续仍需推进 ONNX，补做有明确调优假设的受控对比，而不是直接扩大到全样本 `--engine all`。

## Surprises & Discoveries

- Observation: 当前环境最初没有安装 `numpy`、`opencv-python`、`tqdm`、`rapidocr-onnxruntime`、`huggingface_hub`、`paddleocr`、`paddlepaddle`，因此一开始只能做纯函数层验证。
  Evidence: 在仓库根目录运行 `python3 - <<'PY' ... __import__(mod) ... PY` 时，这些模块均返回 `No module named ...`。

- Observation: 项目切到 Python 3.12 后，`uv sync` 可以成功解析并安装 PaddleOCR、PaddlePaddle、RapidOCR ONNX Runtime 等依赖。
  Evidence: `uv sync` 成功创建 `.venv`，安装了 `paddleocr==3.4.0`、`paddlepaddle==3.3.1`、`rapidocr-onnxruntime==1.4.4` 等 71 个包。

- Observation: 当前仓库实际安装的 `paddlepaddle==3.3.1` / `paddleocr==3.4.0` 在本机只暴露 `cpu` 设备，不能直接把 Python PaddleOCR 路线切到 Apple GPU。
  Evidence: 运行 `uv run --python 3.12 python - <<'PY' ... import paddle; print(paddle.device.get_device()); print(paddle.device.get_all_custom_device_type()) ... PY` 得到 `cpu` 与 `[]`。

- Observation: 本机 `onnxruntime==1.23.2` 已提供 `CoreMLExecutionProvider`，说明 ONNX Runtime 是当前最现实的 Apple 硬件入口。
  Evidence: 运行 `uv run --python 3.12 python - <<'PY' ... import onnxruntime as ort; print(ort.get_available_providers()) ... PY` 返回 `['CoreMLExecutionProvider', 'AzureExecutionProvider', 'CPUExecutionProvider']`。

- Observation: 当前 `rapidocr-onnxruntime` 只内建 CPU/CUDA/DML provider 选择，不支持 CoreML。
  Evidence: `.venv/lib/python3.12/site-packages/rapidocr_onnxruntime/utils/infer_engine.py` 中 `EP` 仅定义 `CPUExecutionProvider`、`CUDAExecutionProvider` 与 `DmlExecutionProvider`。

- Observation: `PaddleOCR 3.4.0` 的 `predict()` 确实接受 `list[np.ndarray]`，但在当前 CPU 路径下小样本实测并未带来显著提速。
  Evidence: 在 `samples/en_double_bright/clip.mp4` 的前 7 张 ROI 上，受控实验 `single_loop≈6.004s`、`batch_8≈6.073s`，两者几乎持平。

- Observation: `enable_hpi=True` 在当前环境不可用。
  Evidence: 构造 `PaddleOCR(..., enable_hpi=True)` 时，PaddleX 初始化直接报错 `The high-performance inference plugin is not available.`。

- Observation: 当前 `paddlex --install paddle2onnx` 在本仓库的 `uv` 虚拟环境里不能直接工作，因为 `.venv` 内没有 `pip` 模块。
  Evidence: 执行 `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True uv run --python 3.12 paddlex --install paddle2onnx -y` 时，PaddleX 安装器报错 `/Users/wangyg/Development/Working/subtitle-extractor/.venv/bin/python: No module named pip`；随后改用 `uv pip install --python .venv/bin/python paddle2onnx` 成功安装 `paddle2onnx==2.1.0`。

- Observation: 官方 `PP-OCRv5_server_det/rec` 已能稳定转换为 ONNX，并在默认 cache 根 `/Users/wangyg/.cache/subx/onnx-coreml` 下被 `apple-spike` 复用。
  Evidence: 执行 `PYTHONPATH=src uv run --python 3.12 python -m subx.dev_cli apple-spike` 成功结束，输出 JSON 中 `det` / `rec` 均生成 `inference.onnx`，路径分别为 `/Users/wangyg/.cache/subx/onnx-coreml/det/inference.onnx` 与 `/Users/wangyg/.cache/subx/onnx-coreml/rec/inference.onnx`。

- Observation: 当前官方 det/rec ONNX 模型都能把 `CoreMLExecutionProvider` 作为 ORT session 的主 provider，但并非全部节点都由 CoreML 接管，仍存在 CPU fallback。
  Evidence: `apple-spike` 期间 ORT 日志显示 det 模型 `265` 个节点中 `255` 个由 CoreML 支持，rec 模型 `287` 个节点中 `187` 个由 CoreML 支持；最终 JSON 中两者的 `primary_provider` 都是 `CoreMLExecutionProvider`，且 `session_providers` 均为 `['CoreMLExecutionProvider', 'CPUExecutionProvider']`。

- Observation: `onnx-coreml` 实验 backend 已完成最小端到端 smoke，并在真实中文样本上给出第一条有竞争力的速度/准确率信号。
  Evidence: 执行 `PYTHONPATH=src uv run --python 3.12 python -m subx.cli samples/zh_single_dark/clip.mp4 --engine onnx-coreml --lang zh --workers 1 --sample-every 180 --output /tmp/subx-onnx-coreml-smoke.srt` 成功结束，`elapsed_seconds≈9.83`；随后执行 `... --sample-every 6 --output /tmp/subx-onnx-coreml-zh6.srt` 成功结束，输出 `produced_cues=3`、`elapsed_seconds≈44.63`。离线对 `/tmp/subx-onnx-coreml-zh6.srt` 与 `samples/zh_single_dark/truth.srt` 的评分结果为 `CER=0.0`、`WER=0.0`、`cue_exact_match=1.0`、`overlap_hit_rate=1.0`。

- Observation: `onnx-coreml` 当前不能安全复用现有多进程 OCR worker 策略；默认 `workers=4` 会把多份 CoreML det/rec session 复制进多个进程，存在直接耗尽统一内存的风险。
  Evidence: 在同时启动 `subx-dev eval ./samples --engine onnx-coreml` 与 `subx-dev bench ./samples --engine onnx-coreml`、且沿用默认 `workers=4` 时，机器出现系统内存耗尽并整机失去响应；代码路径上 `extract_subtitles()` 会在 `workers>1` 时通过 `ProcessPoolExecutor(initializer=_init_worker, ...)` 为每个 worker 单独初始化 backend。现已加入 fail-fast 保护，`onnx-coreml` 若不是 `--workers 1` 会直接抛出 `ValueError`。

- Observation: 在当前官方 ONNX 模型和当前实现下，`onnx-coreml` 的全样本结果没有满足“速度优先”的门槛；它在 3/3 样本上都慢于 Paddle，且英文样本精度明显退化。
  Evidence: 用同一组参数 `subx-dev eval ./samples --engine <engine> --workers 1` 复跑后，`en_double_bright` 从 Paddle 的 `10.234s / CER=0.06 / WER≈0.2121` 退化到 `onnx-coreml` 的 `16.862s / CER=0.18 / WER≈0.3636`；`mixed_double_dark` 从 `47.717s` 变为 `60.063s`；`zh_single_dark` 从 `30.575s` 变为 `44.360s`。

- Observation: ORT 官方模型可用性分析把当前瓶颈进一步缩小到“官方 det/rec ONNX 模型的动态 shape 不利于 CoreML EP”。
  Evidence: 执行 `python -m onnxruntime.tools.check_onnx_model_mobile_usability` 后，det/rec 两个模型在“as is”状态下对 `CoreML NeuralNetwork` 和 `CoreML MLProgram` 都给出 `Model should perform well ...: NO`；工具明确指出若把动态 shape 固定，det 的 `CoreML MLProgram` 才变为 `MAYBE`（`264/265` 节点，2 partitions），rec 的 `CoreML MLProgram` 也才变为 `MAYBE`（`286/287` 节点，2 partitions）。

- Observation: `MLProgram` 不是当前官方 det ONNX 模型的直接可用解；在真实初始化中它会因为 `MaxPool` 约束失败，只能回退到 `NeuralNetwork`。
  Evidence: 在 `onnx-coreml` backend 中显式尝试 `ModelFormat=MLProgram` 时，det session 初始化报错 `Unable to parse ML Program: in operation MaxPool.0: ceil_mode must be False when pad_type is equal to same`；现实现已改为“先试 `MLProgram`，失败后回退到 `NeuralNetwork`”。

- Observation: CoreML model cache 确实能降低 warm run 的初始化成本，但它没有把当前 `onnx-coreml` 路线拉回到可竞争区间。
  Evidence: 为 `onnx-coreml` 加上 `ModelCacheDirectory` 后，`zh_single_dark` 冷启动从约 `45.94s` 降到 warm run 的约 `41.71s`，改善约 `9.2%`；`en_double_bright` 的 warm run 也降到约 `11.65s`，已接近 Paddle 的 `10.23s`。但英文样本的 `CER/WER` 仍保持在 `0.18 / 0.3636`，没有改善到可接受区间；中文样本 warm run 也仍明显慢于 Paddle 的 `30.57s`。

- Observation: 用户已明确放弃 Apple/CoreML 路线，因此实验入口已经从当前工作代码路径移除。
  Evidence: `subx` 与 `subx-dev` 的 `--engine` 选项已不再接受 `onnx-coreml`，`subx-dev apple-spike` 子命令也已删除；对应 `src/subx/apple_spike.py`、`src/subx/ocr/onnx_coreml_backend.py` 与相关测试文件已移除。

- Observation: Paddle 路线在真实样本 `samples/zh_single_dark/clip.mp4` 上已跑通，但速度偏慢。
  Evidence: `subx ... --engine paddle --workers 1 --sample-every 6` 输出 stats：`sampled_frames=90`、`submitted_ocr_frames=45`、`produced_cues=3`、`elapsed_seconds≈97.71`。

- Observation: ONNX 路线当前存在未定位的长时间卡住现象，至少在 `samples/zh_single_dark/clip.mp4` 上，采样完成后没有返回结果。
  Evidence: `subx ... --engine onnx --workers 1 --sample-every 6` 输出了完整 `Sampling: 100%|...| 540/540` 进度条，但随后多次轮询仍无 stdout/stderr 结束信号。

- Observation: PaddleOCR 在显式传入 `text_detection_model_name` / `text_recognition_model_name` 时，会忽略 `lang` 和 `ocr_version`。
  Evidence: Paddle smoke test 期间打印了 `UserWarning: lang and ocr_version will be ignored when model names or model directories are not None.`。

- Observation: ONNX backend 当前并非“单张图必现卡死”；最小复现显示 backend 初始化和单张 ROI 识别都能成功返回。
  Evidence: 在仓库根目录运行 `uv run --python 3.12 python - <<'PY' ... backend = OnnxBackend('zh') ... result = backend.recognize(ocr_frame) ... PY`，输出了 `backend inited` 和 `result OCRText(text='', score=0.0, lines=[])`。

- Observation: `samples/zh_single_dark` 上 ONNX 的主要阻塞是顺序 OCR 吞吐过慢，而不是采样结束后的控制流死锁。
  Evidence: 对同一批候选帧逐帧计时时，前 7 帧单次 `backend.recognize(image)` 分别约为 `6.874s`、`7.054s`、`6.375s`、`7.559s`、`10.625s`、`10.728s`、`11.520s`；同时在 CLI 中已可见 `OCR (onnx): ... 6/45 [00:34<03:43, 5.74s/frame]` 进度。

- Observation: 原冻结命令在 `samples/zh_single_dark` 上最终会正常完成，只是总耗时明显偏长。
  Evidence: 评估子 agent 复跑 `uv run --python 3.12 subx samples/zh_single_dark/clip.mp4 --engine onnx --lang zh --workers 1 --sample-every 6 --output /tmp/subx-zh-onnx.srt`，最终返回 `sampled_frames=90`、`submitted_ocr_frames=45`、`produced_cues=3`、`elapsed_seconds=224.34`。

- Observation: ONNX 在当前样本上的多 worker 扩展性很差，至少 `workers=2` 不能显著改善总耗时。
  Evidence: 评估子 agent 用真实 CLI 复跑 `samples/zh_single_dark/clip.mp4`，`workers=1` 时 `elapsed_seconds=224.34`，`workers=2` 时 `elapsed_seconds=209.9458993330045`，同样都是 `submitted_ocr_frames=45`、`produced_cues=3`；`workers=4` 的中途观测也未显示出明显更快的早期进度。

- Observation: Paddle 路线已经能稳定产出全样本评估报告，并在当前 3 组样本上给出可用的准确率与耗时基线。
  Evidence: 执行 `uv run --python 3.12 subx-dev eval ./samples --engine paddle --json ./eval-paddle.json --report ./eval-paddle.md` 成功结束，并写出根目录报告文件；其中 `zh_single_dark` 为 `CER=0.0`、`WER=0.0`、`elapsed_seconds=28.20`，`mixed_double_dark` 为 `CER≈0.00885`、`WER≈0.1579`、`elapsed_seconds=39.53`，`en_double_bright` 为 `CER=0.06`、`WER≈0.2121`、`elapsed_seconds=10.22`。

- Observation: 在当前最轻的英文样本上，ONNX 也没有表现出“牺牲一些速度换来更好精度”的趋势。
  Evidence: 执行 `uv run --python 3.12 subx-dev eval /tmp/subx-one-sample --engine onnx --json /tmp/subx-onnx-en.json --report /tmp/subx-onnx-en.md` 后，`en_double_bright` 的 ONNX 结果为 `CER=0.14`、`WER≈0.3636`、`elapsed_seconds=21.78`；同一样本 Paddle 基线为 `CER=0.06`、`WER≈0.2121`、`elapsed_seconds=10.22`。

- Observation: 为了避免长视频把候选帧全部堆在内存里，当前提取流程已改为分批 OCR；如果单 worker 模式下每批都重复初始化 Paddle backend，会带来明显的额外耗时和大量系统提示。
  Evidence: TDD 过程中新增的单测先失败，显示同一次 `extract_subtitles()` 跨 3 个批次会触发 3 次 `create_backend(...)`；修复后测试通过，确认同一提取任务只初始化一次 backend。

- Observation: Paddle 的导入期和初始化期都会向终端输出系统提示，如果不显式压制，最终用户会看到 connectivity/model/cache 等内部信息。
  Evidence: TDD 过程中新增的 `tests/test_paddle_backend.py` 先失败，分别复现了导入期 stdout/stderr 和初始化期 stdout/stderr/warning 泄露；修复后 3 个相关测试全部通过。

- Observation: PaddleX 虽然默认把模型源设为 `huggingface`，但默认缓存根目录仍是 `~/.paddlex`；如果继续只传 `text_detection_model_name` / `text_recognition_model_name`，运行时有效模型目录不会自然收口到 Hugging Face cache。
  Evidence: 本地安装包 `.venv/lib/python3.12/site-packages/paddlex/utils/flags.py` 显示 `MODEL_SOURCE = ... \"huggingface\"`，而 `.venv/lib/python3.12/site-packages/paddlex/utils/cache.py` 显示默认 `CACHE_DIR = ~/.paddlex`；同时本机同时存在 `~/.paddlex/official_models/PP-OCRv5_server_*` 和 `~/.cache/huggingface/hub/models--PaddlePaddle--PP-OCRv5_server_*/...`。

- Observation: 改为显式 `snapshot_download()` 后，Paddle v5 模型已经以标准 Hugging Face snapshot 形式落在 `~/.cache/huggingface/hub`，并且可以直接作为 PaddleOCR 的 `text_detection_model_dir` / `text_recognition_model_dir` 复用。
  Evidence: 轻量 smoke run 后，本机出现 `~/.cache/huggingface/hub/models--PaddlePaddle--PP-OCRv5_server_det/snapshots/ca867c897ecbca8873081573a802ad70d499cb94` 与 `...PP-OCRv5_server_rec/snapshots/b26c3587fda8da3c8ec0ce357214b4d661ff1558`，目录内均包含 `inference.json`、`inference.pdiparams`、`inference.yml`。

- Observation: 当前最终用户进度已不再按“采样条 + OCR 条”分段显示，而是单一 `Extracting` 进度条贯穿采样与 OCR，并在 postfix 中持续显示 `frames` / `ocr` 计数。
  Evidence: 执行 `uv run --python 3.12 subx samples/zh_single_dark/clip.mp4 --engine paddle --lang zh --workers 1 --sample-every 180 --output /tmp/subx-progress-smoke.srt` 时，终端只显示一条 `Extracting: ... [ocr | frames 540/540 | ocr 3/3]` 进度并最终输出 JSON。

- Observation: 当前长视频默认参数路径的主性能损耗之一，确实来自多 worker 模式下每个 OCR flush 都重复创建 `ProcessPoolExecutor`；改成整次提取复用一个池后，样本级耗时和真实长视频前期推进速度都有改善。
  Evidence: 新增的 `tests/test_pipeline.py` 已固定“同一次 `extract_subtitles()` 只创建 1 个进程池、跨 3 个 flush 复用、最后只 `shutdown()` 1 次”；同时 `subx samples/zh_single_dark/clip.mp4 --workers 2 --sample-every 3` 的真实 smoke 现为 `elapsed_seconds≈41.70`。对真实视频 `RBD-648-UC.compressed.mp4` 的短时观测中，新版在约 `1m27s` 时已推进到 `2305/438955`，而旧版 terminal 记录是在约 `1m50s` 才到相同位置。

- Observation: 低风险的 OCR 候选二次筛选确实进一步压低了候选提交量，而且没有破坏 cue 连续性。
  Evidence: 在 `samples/zh_single_dark/clip.mp4` 上，默认参数 smoke 的 `submitted_ocr_frames` 从 `83` 降到 `57`，`reused_frames` 从 `97` 增到 `124`，`elapsed_seconds` 从约 `43.71` 降到约 `30.37`；`workers=2` 版本也保持 `submitted_ocr_frames=57`，`elapsed_seconds≈42.17`。随后执行 `uv run --python 3.12 subx-dev eval ./samples --engine paddle --json /tmp/eval-paddle-after-filter.json --report /tmp/eval-paddle-after-filter.md`，`en_double_bright` / `mixed_double_dark` / `zh_single_dark` 的 `CER` / `WER` 与旧基线一致，同时 `ocr_calls` 分别为 `7` / `91` / `57`。

- Observation: 默认采样路径上再加 150ms 的内部 OCR 去抖后，长变化段的重复提交继续下降，但 `sample_every=1` 的低密度采样测试没有被误伤。
  Evidence: 重新运行 `_collect_checkpoints()` 后，`zh_single_dark` 的 `submitted_ocr_frames` 从 `57` 降到 `36`，`mixed_double_dark` 从 `91` 降到 `49`，`en_double_bright` 仍为 `7`；`tests/test_pipeline.py` 当前相关用例全部通过，其中包括 `sample_every=1` 的 distinct / redundant candidate 覆盖，以及默认采样路径下的去抖覆盖。

- Observation: 150ms 内部去抖在当前 3 组 Paddle 样本上没有带来准确率回退，但确实进一步压低了 OCR 调用数和总耗时。
  Evidence: 执行 `uv run --python 3.12 subx-dev eval ./samples --engine paddle --json /tmp/eval-paddle-post-debounce.json --report /tmp/eval-paddle-post-debounce.md` 后，`en_double_bright` 仍为 `CER=0.06`、`WER≈0.2121`、`ocr_calls=7`、`elapsed_seconds≈5.84`；`mixed_double_dark` 仍为 `CER≈0.00885`、`WER≈0.1579`、`ocr_calls=49`、`elapsed_seconds≈19.28`；`zh_single_dark` 仍为 `CER=0.0`、`WER=0.0`、`ocr_calls=36`、`elapsed_seconds≈13.49`。

- Observation: 当前默认 Paddle 路径在真实长视频上的前期推进速度继续提升，且单一 `Extracting` 进度条的总量对齐比旧记录更稳定。
  Evidence: 执行 `uv run --python 3.12 subx /Users/wangyg/Downloads/RBD-648-UC/RBD-648-UC.compressed.mp4 --output /tmp/RBD-648-UC.default-validation.srt` 的短时观测中，约 `1m40s` 已推进到 `4488/438955`，约 `1m47s` 时到 `4586/438955`；此前计划内旧记录是约 `1m27s` 到 `2305/438955`。本轮观测全程只显示单一 `Extracting` 进度条，且总量维持在 `438955` 基线上，没有出现采样结束后回缩总量的表现；命令最后由人工 `Ctrl-C` 中断，未跑完整体 benchmark。

- Observation: 当前进度条总量对齐修正确实已经落进实现；新默认路径不再把“最大采样上限”预加到总量里，而是从真实帧数起步并随已发现的 OCR 工作量增长。
  Evidence: 执行 `uv run --python 3.12 subx /Users/wangyg/Downloads/RBD-648-UC/RBD-648-UC.compressed.mp4 --output /tmp/RBD-648-UC.post-lazy-prep.srt` 的短时观测中，起始总量为 `329216`，随后随实际 OCR 排队增长到 `329249`、`329401`、`329536`；相同文件在旧实现下的起始总量是 `438955`，因为当时把 `frame_count + max_sampled_frames` 预先算进了总步数。

- Observation: 当前“惰性 OCR 图像准备”补丁并未在真实长视频前缀的隔离基准里表现出明确收益，说明它还不是一个已经闭合的性能优化。
  Evidence: 在同一长视频前缀 `12000` 帧、`4000` 个 sampled frame、`1040` 次 submitted frame 的受控脚本中，旧 eager 路径耗时 `26.793s`，当前 lazy 实现耗时 `26.996s`，几乎持平；另一个实验性分支“灰度路径不 resize、只在提交 OCR 时 resize”耗时 `26.676s`，但会把 `submitted` 从 `1040` 改到 `1093`，说明它改变了候选判定语义，当前不能直接采用。

- Observation: 对长视频默认参数路径来说，更有效的优化点不是灰度预处理，而是非采样帧的解码策略；把非采样帧改为 `grab()`、只在采样点 `retrieve()` 后，前缀吞吐接近翻倍。
  Evidence: 在 `/Users/wangyg/Downloads/RBD-648-UC/RBD-648-UC.compressed.mp4` 的前 `12000` 帧受控脚本中，旧 `read()` 路径耗时 `33.602s`，而 `grab()/retrieve()` 路径耗时 `15.987s`；两者都得到 `sampled=4001`、`submitted=1040`、`reused=2961`，说明当前候选判定语义保持一致。

- Observation: `grab()/retrieve()` 改动没有带来 Paddle 样本级准确率或 OCR 调用次数回退。
  Evidence: 执行 `uv run --python 3.12 subx-dev eval ./samples --engine paddle --json /tmp/eval-paddle-post-grab.json --report /tmp/eval-paddle-post-grab.md` 后，`en_double_bright` 仍为 `CER=0.06`、`WER≈0.2121`、`ocr_calls=7`；`mixed_double_dark` 仍为 `CER≈0.00885`、`WER≈0.1579`、`ocr_calls=49`；`zh_single_dark` 仍为 `CER=0.0`、`WER=0.0`、`ocr_calls=36`。

- Observation: 即使引入了“惰性提交 OCR 图像准备”，提交路径里仍残留一处确定的重复工作：同一张已提交候选会先为判定做一次 `_prepare_roi_gray()`，再为 OCR 再做一次 resize 和灰度化/模糊化。
  Evidence: 本轮代码检查中，`src/subx/pipeline.py` 原实现先调用 `_prepare_roi_gray(roi_frame, ...)` 生成 `gray`，随后在 `should_submit` 分支里再次调用 `_prepare_roi_frame(roi_frame, ...)`；而后者返回的 `gray` 在调用点并未被使用。

- Observation: 把提交路径拆成 `_prepare_ocr_frame()` 后，当前行为仍保持稳定，但这只能证明去掉了确定冗余，不能替代真实前缀 benchmark。
  Evidence: 执行 `uv run --python 3.12 python -m unittest discover -s tests -v` 后 32 个测试全部通过；执行 `uv run --python 3.12 subx samples/zh_single_dark/clip.mp4 --engine paddle --lang zh --workers 1 --sample-every 180 --output /tmp/subx-post-ocr-frame-path.srt` 也成功结束，输出 stats 为 `sampled_frames=4`、`submitted_ocr_frames=4`、`produced_cues=0`、`elapsed_seconds≈5.50`。

- Observation: 重新跑真实长视频前缀基准后，“提交 OCR 时不再重复灰度化/模糊化”确实带来可重复但幅度较小的收益。
  Evidence: 使用 `PYTHONPATH=src uv run --python 3.12 python - <<'PY' ... PY` 的前缀隔离脚本，在同一当前代码树上比较“模拟旧实现的重复灰度化路径”和“当前 `_prepare_ocr_frame()` 路径”，3 轮结果分别为旧 `12.306/12.302/12.762s`、新 `12.247/12.075/12.498s`；两侧都保持 `sampled=4000`、`submitted=1040`、`reused=2960`，均值差约 `0.183s`（`1.47%`）。

- Observation: 在当前实现里，前缀基准的主要热点已经进一步集中到视频解码侧；`retrieve()` 远高于采样判定和 ROI 预处理。
  Evidence: 对当前代码树执行 `PYTHONPATH=src uv run --python 3.12 python - <<'PY' ... cProfile ... _collect_checkpoints(...) ... PY` 后，前 `12000` 帧 profile 显示 `_collect_checkpoints()` 总计约 `12.366s`，其中 `retrieve()` 约 `8.694s`、`grab()` 约 `2.050s`；相比上一轮同口径 profile，`resize()` 调用已从 `5040` 次降到 `4000` 次，对应累计时间从约 `1.071s` 收口到约 `0.728s`。

- Observation: “复用 resize 结果”这一步确实消掉了预处理内部的确定冗余，但 wall-time benchmark 仍有明显抖动，不宜把它解读成同量级的整体验证提速。
  Evidence: 当前代码树上 3 轮普通前缀 benchmark 的 wall time 分别为 `12.433s`、`12.745s`、`12.438s`，均值约 `12.539s`；同一期间的 profile-run 为 `12.366s`。这说明局部 CPU 工作量下降是真实的，但长视频前缀总体时间已经更容易受解码和系统噪声影响。

- Observation: `CAP_PROP_CONVERT_RGB=0` 在本机 FFmpeg 后端上确实能把 `retrieve()` 变成单通道帧，并带来一定速度收益，但它会改变候选判定结果。
  Evidence: 受控裸解码实验中，前 `12000` 帧 / `4001` 次 sampled 的耗时从默认 `11.681s` 降到 `11.442s`；进一步在 `_collect_checkpoints()` 前缀实验里，灰度解码路径从 `12.015s` 降到 `11.296s`，但 `submitted_ocr_frames` 也从 `1040` 变成 `960`。

- Observation: 把灰度解码路线补上“submitted frame 转回 BGR 再喂 OCR”后，样本准确率并非完全等价，至少 `mixed_double_dark` 上出现了明确的 `WER` 回退。
  Evidence: 在 `workers=1`、`sample_every=3` 的受控评估中，当前基线结果为 `en_double_bright CER=0.06 / WER≈0.212121 / ocr_calls=7 / 8.536s`、`mixed_double_dark CER≈0.00885 / WER≈0.157895 / ocr_calls=49 / 45.768s`、`zh_single_dark CER=0.0 / WER=0.0 / ocr_calls=36 / 29.505s`；灰度解码实验结果则为 `en_double_bright CER≈0.053333 / WER≈0.272727 / ocr_calls=7 / 8.948s`、`mixed_double_dark CER≈0.00885 / WER≈0.210526 / ocr_calls=47 / 43.673s`、`zh_single_dark CER=0.0 / WER=0.0 / ocr_calls=32 / 26.735s`。

- Observation: 当前 OpenCV 暴露了 `VIDEO_ACCELERATION_*` 常量，但本机 FFmpeg backend 不接受这些硬件加速设置。
  Evidence: 对 `VIDEO_ACCELERATION_ANY` / `D3D11` / `MFX` / `NONE` / `VAAPI` 逐个调用 `cap.set(cv2.CAP_PROP_HW_ACCELERATION, value)` 时，结果全部为 `set_ok=False`、`actual=0.0`；对应前 `12000` 帧裸解码耗时也都落在 `11.56s` 到 `11.71s`，没有出现可用的硬件加速档位。

- Observation: 当前默认 ROI 在 Paddle det 的默认缩放策略下会被放大到非常宽的输入尺寸，因此简单下调 det 输入边长虽然看起来“更小更快”，但很容易同时改变检测质量和端到端时间。
  Evidence: 在 `samples/` 的默认 ROI 上，提交给 OCR 的候选帧实际是 `1280x144`；Paddle 运行时日志会把它先放大到 `6542x736`，再因为超过 `max_side_limit=4000` 被再次收缩。

- Observation: `text_det_limit_side_len=192` 的微基准收益是误导性的，不能直接作为主线优化方案。
  Evidence: 在 `mixed_double_dark` 的 2 张 ROI 微基准里，受控实验从 `24.058s` 降到 `3.553s`；但完整 `subx-dev eval ./samples --engine paddle --workers 1` 结果退化为 `en_double_bright CER=0.1467 / WER=0.3333 / 15.84s`、`mixed_double_dark WER=0.3684 / 85.19s`、`zh_single_dark 56.70s`。

- Observation: 内部 OCR 去抖继续从 `150ms` 往上调时，真正先被打坏的不是 `CER/WER`，而是 cue 对齐。
  Evidence: `250ms` 的受控全样本评估中，`mixed_double_dark` 虽仍为 `CER≈0.00885 / WER≈0.05263`，但 `overlap_hit_rate` 已降到 `0.6667`，`cue_exact_match` 也降到 `0.6667`，`mean_start_error≈1.8291s`。

- Observation: `200ms` 是当前已验证可接受的默认去抖值；它保住了 cue 对齐，同时继续压掉一部分无价值 OCR 调用。
  Evidence: 在代码默认值改为 `200ms` 后重新执行 `PYTHONPATH=src uv run --python 3.12 python -m subx.dev_cli eval ./samples --engine paddle --workers 1 --json /tmp/eval-paddle-debounce020.json`，3 组样本的 `overlap_hit_rate` 全部为 `1.0`；结果分别为 `en_double_bright 9.10s / ocr_calls=7`、`mixed_double_dark 47.61s / ocr_calls=49`、`zh_single_dark 29.89s / ocr_calls=35`。

- Observation: 在当前 PaddleOCR 3.4.0 包装层上，直接把单张调用改成 `predict(list)` 并没有带来可观收益。
  Evidence: 对 `mixed_double_dark` 的 49 张候选做受控 OCR 阶段对比时，`single_loop≈46.048s`、一次性 `batch_all≈46.032s`、`chunk_8≈45.959s`、`chunk_4≈46.207s`；差异只有噪声级别。

- Observation: 当前样本里的真实字幕框远窄于默认全宽 ROI，横向收窄比继续折腾 Paddle 调度更值得投入。
  Evidence: 对前 10 张有效候选做 Paddle 检测框统计后，`mixed_double_dark` 的平均文本横向占比约 `0.414`、左右边界约 `0.293/0.707`；`zh_single_dark` 约 `0.391`、`0.304/0.695`；`en_double_bright` 约 `0.656`、`0.172/0.828`。

- Observation: 把默认 ROI 收窄到中心 `70%` 宽度后，当前样本集在保持 cue 对齐的同时给出了这轮最明显的真实耗时收益。
  Evidence: 在代码默认值切到 `ROI(0.15, 0.8, 0.7, 0.2)` 且 `subx-dev` 默认 `--default-roi` 同步后，重新执行 `PYTHONPATH=src uv run --python 3.12 python -m subx.dev_cli eval ./samples --engine paddle --workers 1 --json /tmp/eval-paddle-default-roi070.json`，结果为 `en_double_bright 7.26s / CER≈0.0667 / WER≈0.2121 / overlap=1.0`、`mixed_double_dark 36.00s / CER≈0.00885 / WER≈0.1579 / overlap=1.0`、`zh_single_dark 22.63s / CER=0 / WER=0 / overlap=1.0`。

- Observation: 但在真实长视频前缀里，单独收窄 ROI 宽度并不会自动更快；由于 `_resize_roi_frame()` 只限制宽度到 `1280`，更窄的 ROI 反而可能保留更大的输入高度，导致单次 OCR 更慢。
  Evidence: 在 `/Users/wangyg/Downloads/RBD-648-UC/RBD-648-UC.compressed.mp4` 的前缀抽样中，全宽 ROI 的首批候选形状为 `1280x144`，单次 OCR 约 `776ms`；`center_70` 的首批候选变成 `1280x206`，单次 OCR 约 `1127ms`；`center_65` 的首批候选为 `1248x216`，单次 OCR 约 `1126ms`。同一前缀的候选收集阶段里，`full_100 submitted=1040`，`center_70 submitted=1085`，`center_65 submitted=1094`。

- Observation: 单行和双行字幕需要不同的默认高度，不能继续共用同一个固定值。
  Evidence: 在全宽底部 ROI 的受控评估里，`zh_single_dark` 的 `h=0.10` 已出现 `CER=3.2 / overlap=0.6667`，而 `h=0.12` 与 `h=0.14` 都恢复到 `CER=0 / WER=0 / overlap=1.0`，其中 `h=0.14` 耗时约 `20.90s`；双行样本上，`en_double_bright` 的 `h=0.14~0.18` 全部明显退化，直到 `h=0.20` 才回到当前基线，`h=0.22` 进一步把 `CER/WER` 压到约 `0.0067 / 0.0303`，但耗时增加到约 `8.52s`。`mixed_double_dark` 上，`h=0.14~0.18` 同样退化，`h=0.20` 回到基线，`h=0.22` 保持同等 `CER/WER` 但更慢。

- Observation: 当前 `subx` 已支持结构化 ROI 参数，不再要求最终用户总是手写完整 `x,y,w,h`，而且参数名已收敛为更短的最终用户接口。
  Evidence: CLI 现已新增 `--lines/-l`、`--width/-w`、`--height/-H`、`--bottom-offset/-b`；对应测试 `tests/test_cli.py` 与 `tests/test_roi.py` 已覆盖“按视频尺寸反推 preset 高度”、“按 `lines` 自动选择默认 width/height”以及“显式宽/高/底部偏移组装 ROI”。

- Observation: `subx --help` 现在会直接打印结构化 ROI 参数的默认值和用途，最终用户不再需要翻 README 才能知道预设行为。
  Evidence: 当前帮助文本已显式说明 `--lines` 默认 `single`、`--width` 默认“根据 `--lines` preset 推导（single=0.75, double=1.0）”、`--height` 默认“根据 `--lines` 和视频尺寸反推”、`--bottom-offset` 默认 `0.0`。

- Observation: 只要把 ROI 高度按 `prepared_height` 反推，缩窄 ROI 宽度本身并不会再自动抬高 OCR 输入高度；此前长视频里“收窄 width 反而更慢”的主要缩放副作用已经被消掉。
  Evidence: 在 `/Users/wangyg/Downloads/RBD-648-UC/RBD-648-UC.compressed.mp4` 的前缀实验里，全宽默认 ROI 的 prepared shape 为 `144x1280`、前 30 个候选平均约 `772.58ms/张`；`width=0.7` 且双行 preset 改为 prepared-height 反推后，prepared shape 同样为 `144x1280`，前 30 个候选平均约 `761.34ms/张`。

- Observation: 但在 prepared-height 反推逻辑已经生效后，`0.8` 和 `0.85` 这两档默认宽度候选仍然不安全，问题已不再是缩放副作用，而是双行字幕本身的横向分布超出这两个宽度。
  Evidence: `width=0.8` 时，`en_double_bright` 退化到 `CER=0.48 / WER≈0.4848`，`mixed_double_dark` 退化到 `CER≈0.3451 / WER≈0.3158`；`width=0.85` 时，`en_double_bright` 仍为 `CER≈0.4733 / WER≈0.4848`，`mixed_double_dark` 仍为 `CER≈0.2743 / WER≈0.4211`。与之对照，`zh_single_dark` 在这两档宽度上仍保持 `CER=0 / WER=0`。

- Observation: 对双行字幕来说，默认高度适当上调是有效方向；在同样的 `width=0.9` 下，把 double 的 prepared-height 从 `144px` 抬到 `158.4px` 后，精度明显回升。
  Evidence: `width=0.9 + prepared_height=144px` 时，`en_double_bright` 为 `CER≈0.2467 / WER≈0.4848 / 12.94s`，`mixed_double_dark` 为 `CER≈0.0265 / WER≈0.3158 / 65.93s`；把 prepared-height 抬到 `158.4px` 后，`en_double_bright` 改善到 `CER≈0.0867 / WER≈0.3030 / 9.56s`，`mixed_double_dark` 改善到 `CER≈0.0088 / WER≈0.1579 / 60.84s`。这说明 double 预设很可能需要同时“更宽 + 更高”。

- Observation: 在“速度优先”的约束下，double 默认高度不能为了精度继续无限上调；`151.2px` 和 `158.4px` 虽然能改善英文双行指标，但长视频前缀单次 OCR 成本都会明显上升。
  Evidence: 当前基线 `width=1.0 + prepared_height=144px` 的前 30 个长视频候选约为 `1120.11ms/张`；`width=1.0 + prepared_height=151.2px` 升到 `1314.97ms/张`，`width=0.95 + prepared_height=151.2px` 也仍有 `1299.55ms/张`。虽然 `width=1.0 + prepared_height=151.2px` 能把 `en_double_bright` 改善到 `CER≈0.0333 / WER≈0.1515`，但 `mixed_double_dark` 仍维持原有文本指标，说明这部分收益主要是在用更高的 OCR 成本换英文样本精度。

- Observation: 当前最符合“single 更窄、double 更宽”的默认形态，是 `single` 默认宽度收敛到 `0.75`，而 `double` 继续维持 `1.0` 全宽基线。
  Evidence: 最新单行受控实验里，`zh_single_dark` 在 `width=0.85/0.8` 时退化到 `CER≈0.2857 / WER≈0.3333 / overlap≈0.6667`，而 `width=0.75/0.7` 恢复到 `CER=0 / WER=0 / overlap=1.0`；同时在真实长视频前 `12000` 帧上，`width=0.75` 与旧的 `0.85` 同样保持 `submitted_ocr_frames=719`，`workers=6` 下 wall time 约 `129.12s` 对比 `129.52s`，没有额外代价。

- Observation: 如果把目标重新切回“优先减少 OCR 调用次数”，当前最有效的现成旋钮仍然是内部 OCR 去抖；候选相似度门限和 diff 门限的收益都远小于去抖。
  Evidence: 在仅观察 `_collect_checkpoints()` 的受控实验里，默认 `200ms` 时 `mixed_double_dark/zh_single_dark` 的 submitted 分别为 `49/35`；改成 `225ms` 后直接降到 `33/25`，`250ms` 也仍是 `33/25`。相比之下，把 `ocr_candidate_similarity_threshold` 提到 `0.985` 对 `mixed_double_dark` 没有帮助，甚至把 `zh_single_dark` 的 submitted 从 `35` 提高到 `36`。

- Observation: `225ms` 去抖已经足以触发明显的 cue 对齐回退，但这是当前“允许一定精度牺牲、优先减少 OCR 调用次数”目标下可接受的主线取舍；同时 `225ms` 和 `250ms` 的候选量几乎相同，因此应优先选择更小的 `225ms`。
  Evidence: 在真实样本评估里，`225ms` 时 `mixed_double_dark` 的 `ocr_calls` 从 `49` 降到 `33`，`elapsed` 从约 `82.13s` 降到约 `55.78s`，但 `overlap_hit_rate` 退到 `0.6667`，`cue_exact_match` 升到 `0.6667`，`mean_start_error≈1.8291s`；与此同时，前面的 `_collect_checkpoints()` 实验已表明 `250ms` 的 submitted 与 `225ms` 相同，因此当前默认值收敛到 `225ms` 更合适。

- Observation: 在当前更激进的 `225ms` 去抖前提下，继续下调“候选相似度门限”或上调“变化检测门限”都不是理想主线；前者会先打坏中文单行，后者会先打坏混合双行文本质量。
  Evidence: 把 `ocr_candidate_similarity_threshold` 降到 `0.95` 时，`zh_single_dark` 的 `ocr_calls` 虽从 `25` 进一步降到 `19`，但 `CER/WER` 退化到约 `0.2857/0.3333`、`overlap_hit_rate=0.6667`；把 `diff_threshold` 调到 `0.02` 时，`mixed_double_dark` 的 `ocr_calls` 从 `33` 降到 `31`，但 `CER/WER` 退化到约 `0.3805/0.4211`。

- Observation: 对当前样本来说，把默认 `sample_every` 做成 `lines` 相关，比继续扭更激进的去重门限更像一条可落地的主线优化。
  Evidence: 在 `225ms` 去抖下，`double` 样本把 `sample_every` 从 `3` 提到 `6` 后，`en_double_bright` 的 `sampled_frames` 从 `145` 降到 `73`，`ocr_calls` 保持 `7`，`elapsed` 从约 `14.24s` 降到约 `10.81s`；`mixed_double_dark` 的 `sampled_frames` 从 `181` 降到 `91`，`ocr_calls` 为 `34`，`elapsed` 约 `47.54s`，且 `overlap_hit_rate` 仍为 `1.0`。在新的 `single=0.75` 前提下，`zh_single_dark` 则以 `sample_every=5` 优于旧的 `3`：样本侧 `elapsed≈11.44s` 对比 `13.04s`，`ocr_calls=24` 对比 `25`，同时保持 `CER/WER=0`；真实长视频前 `12000` 帧上也把 `sampled_frames` 从 `4000` 降到 `2400`、`submitted_ocr_frames` 从 `719` 降到 `702`。

- Observation: 当前仓库已经不需要在 `uv` 命令里重复显式指定 `--python 3.12`。
  Evidence: 根目录 `.python-version` 当前为 `3.12`，`pyproject.toml` 的 `requires-python` 为 `>=3.12,<3.13`；实际执行 `uv run python -V` 返回 `Python 3.12.13`，执行 `uv run python -m unittest tests.test_cli -v` 也能直接通过。

- Observation: “连续静态段动态放大采样间隔”如果全局启用，会先打坏单行中文样本，因此不能作为默认路径优化。
  Evidence: 在一次全样本实验里，动态采样把 `en_double_bright/mixed_double_dark/zh_single_dark` 的 `sampled_frames` 分别压到 `82/153/139`；但 `zh_single_dark` 退化到 `CER≈0.2857`、`WER≈0.3333`、`overlap_hit_rate=0.6667`，而当前固定采样基线仍为 `CER=0`、`WER=0`、`overlap_hit_rate=1.0`。

- Observation: 即便把动态采样限制到 `sample_every=6` 的双行路径，它也没有跑赢固定采样，因此当前不值得保留。
  Evidence: 对 `/tmp/subx-double-samples` 的受控对比中，动态采样把 `en_double_bright/mixed_double_dark` 的 `sampled_frames` 从固定采样的 `73/91` 压到 `43/86`，但 `en_double_bright` 耗时从约 `8.49s` 变为约 `8.68s`，`mixed_double_dark` 耗时从约 `33.13s` 变为约 `34.69s`，且 `WER` 从约 `0.0526` 回退到约 `0.1579`。

- Observation: 在当前 `225ms` 去抖和固定采样策略下，Paddle 多 worker 仍然继续有效扩展到 `workers=6`，但 `workers=8` 已经接近峰值并在较重样本上开始回退。
  Evidence: 同口径 `subx-dev bench ./samples --engine paddle` 中，`workers=1/2/4/6/8` 的 `en_double_bright` 耗时分别约为 `8.73/6.24/5.44/5.12/4.91s`，`mixed_double_dark` 约为 `32.57/19.96/13.52/12.01/12.15s`，`zh_single_dark` 约为 `21.57/14.09/10.02/8.84/9.32s`；`ocr_calls` 与 `sampled_frames` 在各档位保持一致。

- Observation: `workers=6` 的默认值不仅在 `samples/` 上成立，在真实长视频前缀上也成立。
  Evidence: 对 `/Users/wangyg/Downloads/RBD-648-UC/RBD-648-UC.compressed.mp4` 的前 `12000` 帧做受控提取时，旧的 `single` ROI `[0.075, 0.881, 0.85, 0.119]` 在 `workers=4/6` 下分别为 `wall_seconds≈154.35/129.52s`；新的 `single` ROI `[0.125, 0.895, 0.75, 0.105]` 在 `workers=6` 下为 `wall_seconds≈129.12s`。这些结果都保持 `sampled_frames=4000`、`submitted_ocr_frames=719`、`reused_frames=3281`，说明 `workers=6` 的收益稳定成立，且 `single=0.75` 不会破坏当前长视频吞吐。

- Observation: 双行路径的固定采样间隔不能继续从 `6` 上调到 `7/8`；虽然采样帧数继续下降，但长视频前缀里的 OCR 提交量会明显反弹。
  Evidence: 在 `double` 默认 ROI `[0.0, 0.8, 1.0, 0.2]` 下，`sample_every=6/7/8` 的双行样本结果分别为：`en_double_bright` `ocr_calls=7/7/7`、`elapsed≈8.72/7.26/7.41s`，`mixed_double_dark` `ocr_calls=34/56/52`、`elapsed≈33.01/53.17/50.15s`；真实长视频前 `12000` 帧前缀上，`submitted_ocr_frames` 也从 `616` 激增到 `965/873`。这说明 `7/8` 并不是更省的默认值，只是把更稀疏的检查点变成了更多的 OCR 提交。

- Observation: 单行路径把 `sample_every` 从 `5` 再提到 `6`，确实能继续减少 OCR 调用并缩短长视频前缀 wall time，但当前样本上的精度回退已经明显超出“轻微牺牲”。
  Evidence: 在 `single` 默认 ROI `[0.125, 0.895, 0.75, 0.105]` 下，`zh_single_dark` 的 `sample_every=5/6/7` 分别为：`CER≈0.0857/0.3429/0.0571`、`WER≈0.3333/0.6667/0.3333`、`ocr_calls=24/20/32`、`elapsed≈11.79/8.56/13.35s`；真实长视频前 `12000` 帧前缀上，`sample_every=5/6` 的 `submitted_ocr_frames` 为 `702/618`，`workers=6` 下 wall time 约 `123.48/111.80s`。虽然 `6` 比 `5` 再快约 `9.5%`，但样本侧的文本与对齐回退过大，因此当前仍不足以直接替换默认值。

- Observation: 把默认 OCR 候选相似度门限从 `0.97` 微降到 `0.86`，当前看仍然是有效且低风险的主线优化；`0.85` 已经开始明显打坏单行。
  Evidence: 在 `single` 默认路径 `[0.125, 0.895, 0.75, 0.105] + sample_every=5` 下，`zh_single_dark` 的 `threshold=0.97/0.95/0.93/0.9/0.88/0.86/0.85` 分别为 `ocr_calls=24/22/18/14/10/9/7`。其中到 `0.86` 为止，文本指标仍保持 `CER≈0.0857 / WER≈0.3333 / overlap=1.0`，真实长视频前 `12000` 帧前缀上的 `submitted_ocr_frames` 从 `702` 进一步降到 `660/613/544/506/462`，`workers=6` 下单行 wall time 也已确认从 `≈118.03s` 降到 `≈100.26s`（`0.95 -> 0.9`）；但到 `0.85` 时，`zh_single_dark` 已退化到 `CER≈0.3714 / WER≈0.6667 / overlap≈0.3333`。在 `double` 默认路径 `[0.0, 0.8, 1.0, 0.2] + sample_every=6` 下，`en_double_bright` 与 `mixed_double_dark` 在 `threshold=0.86` 仍保持原有 `CER/WER/overlap`，长视频前缀的 `submitted_ocr_frames` 则从 `616` 继续降到 `584/547/492/453/427`。

- Observation: 双行路径可以比当前全局安全边界更激进地下调相似度门限，但 `0.75` 已经越界。
  Evidence: 在 `double` 默认路径 `[0.0, 0.8, 1.0, 0.2] + sample_every=6` 下，`threshold=0.86/0.8/0.75` 时，`mixed_double_dark` 的 `ocr_calls` 分别为 `27/15/9`，长视频前 `12000` 帧前缀的 `submitted_ocr_frames` 分别为 `427/342/289`。其中 `0.8` 仍保持当前双行样本的 `CER/WER/overlap`，但 `0.75` 已把 `en_double_bright` 直接打到 `CER=1.0 / WER=1.0 / overlap=0.0`，`mixed_double_dark` 也退化到 `CER≈0.3805 / WER≈0.4211`。

- Observation: 在新的单行默认相似度门限 `0.86` 下，`single sample_every=6` 已经不再像早期实验那样退化，反而成为新的更优默认点。
  Evidence: 在 `single` 默认路径 `[0.125, 0.895, 0.75, 0.105] + threshold=0.86` 下，`zh_single_dark` 的 `sample_every=5/6` 分别为 `CER≈0.0857/0.0571`、`WER≈0.3333/0.3333`、`overlap=1.0/1.0`、`ocr_calls=9/9`、`elapsed≈5.88/4.07s`；真实长视频前 `12000` 帧前缀上，`submitted_ocr_frames` 从 `462` 进一步降到 `430`，`workers=6` 下 wall time 从 `≈87.18s` 降到 `≈82.49s`。

- Observation: 把双行路径的 OCR 去抖从 `225ms` 进一步提到 `275ms/300ms`，没有形成值得保留的收益，且会直接打坏英文双行样本。
  Evidence: 在 `double` 默认路径 `[0.0, 0.8, 1.0, 0.2] + sample_every=6 + threshold=0.8` 下，`debounce=0.225/0.275/0.3` 的长视频前缀 `submitted_ocr_frames` 都保持 `342` 不变；但 `en_double_bright` 的 `ocr_calls` 会从 `7` 直接掉到 `3`，并退化到 `CER≈0.66 / WER≈0.7879 / overlap≈0.3333`。

- Observation: 单行路径存在一条高收益但明显更激进的候选策略：对新的 distinct 变化段先做 entry-debounce，再决定是否提交 OCR。
  Evidence: 在 `single` 默认路径 `[0.125, 0.895, 0.75, 0.105] + sample_every=6 + threshold=0.86` 下，`zh_single_dark` 使用 entry-debounce 后 `ocr_calls` 从 `9` 降到 `5`，但 `cue_exact/overlap` 从 `1.0/1.0` 退到 `0.6667/0.6667`；真实长视频前 `12000` 帧前缀上，`submitted_ocr_frames` 从 `431` 降到 `243`，`wall_seconds` 从 `≈81.11s` 降到 `≈53.18s`。

## Decision Log

- Decision: 本轮允许完全重写实现，不保留旧的 `main.py` 入口和旧顶层参数。
  Rationale: 旧实现的包结构、ROI 表达能力、评估能力和并发模型都不足以支持后续多阶段重构。
  Date/Author: 2026-04-02 / Codex

- Decision: 最终 CLI 边界调整为“`subx` 只保留提取，`subx-dev` 承接 `eval` / `bench`”。
  Rationale: `subx` 应只服务最终用户的单一任务；评估和基准是研发期内部能力，不应继续暴露在最终用户主命令参数里。
  Date/Author: 2026-04-02 / Codex

- Decision: 主默认 backend 仍以 PaddleOCR 为准，ONNX 先作为候选分支。
  Rationale: 用户优先级是准确率高于性能；Paddle 已经实测跑通，而 ONNX 虽可运行但当前吞吐明显更慢，且尚未完成样本级准确率对比。
  Date/Author: 2026-04-02 / Codex

- Decision: 后续执行采用“主 agent 统筹 + 测试/评估/文档子 agent 分工”的多 agent 模式。
  Rationale: 本任务跨代码实现、样本评估、性能验证和文档同步，多 agent 更适合并行推进，但必须先有清晰边界和统一计划文件。
  Date/Author: 2026-04-02 / Codex

- Decision: 多 agent 的模型分配固定为“主 agent 和评估 agent 使用 `gpt-5.4` + `reasoning_effort=high`，其余实现/测试/文档子 agent 优先使用 `gpt-5.4-mini`”。
  Rationale: 主线推进和评估判断需要更强的综合推理，其他边界清晰的执行任务更适合交给更轻量的 agent 提高并行效率。
  Date/Author: 2026-04-02 / Codex

- Decision: 本轮先把 ONNX 问题按“吞吐与可观测性”处理，而不是继续按“采样后死锁”方向盲查。
  Rationale: backend 级最小复现已经证明初始化和单张 `recognize()` 可返回，当前同参数命令的静默更符合顺序 OCR 阶段极慢且没有阶段进度提示。
  Date/Author: 2026-04-02 / Codex

- Decision: 在当前证据下暂不直接执行 `subx-dev eval ./samples --engine all`。
  Rationale: ONNX 在真实样本上的 `workers=2` 仅比 `workers=1` 提升约 `6.4%`，不足以把全量评估成本降到合理区间；主线应先完成 Paddle 基线，再决定 ONNX 的受控对比范围。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前继续维持 Paddle 作为默认与主线评估路线，ONNX 只保留为后续调优候选，不优先扩大样本评估范围。
  Rationale: Paddle 已完成全样本基线且当前指标与耗时都更可接受；ONNX 在 `zh_single_dark` 上吞吐明显偏慢，在 `en_double_bright` 上同时更慢且更差。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前阶段不再把“全样本 Paddle vs ONNX 对比报告”作为主线必需交付。
  Rationale: 默认 backend 决策已经被现有证据充分支撑；继续扩大 ONNX 评估只会消耗时间，而不会改变当前默认路线。若要继续 ONNX，应先提出明确调优假设，再做受控实验。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前 `subx` 的最终用户输出优先保证三件事：内存/磁盘开销可控、Paddle backend 在单 worker 分批模式下可复用、终端只保留稳定且高层的用户信息。
  Rationale: 用户明确要求不能再出现 swap 挤爆磁盘、不能把系统内部提示直接展示给最终用户，同时性能优化不能牺牲准确率。
  Date/Author: 2026-04-02 / Codex

- Decision: Paddle v5 模型获取路径改为显式通过 Hugging Face Hub 下载，并直接复用 `~/.cache/huggingface/hub` 下的 snapshot 目录。
  Rationale: 这能把模型缓存行为收口到 XDG/Hugging Face 体系，避免继续依赖 PaddleX 默认的 `~/.paddlex` 隐式缓存路径，同时也更容易通过测试约束“下载来源、缓存目录、传给 PaddleOCR 的本地模型目录”。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前 OCR 候选二次筛选的默认门限设为 `0.97`。
  Rationale: 该门限对应约 `0.03` 的 change-ratio，样本只读实验和真实评估都表明它能显著压低 `zh_single_dark` 的 OCR 提交量，同时几乎不影响 `mixed_double_dark` 与 `en_double_bright` 的调用数和准确率。
  Date/Author: 2026-04-02 / Codex

- Decision: 在默认 `sample_every > 1` 的采样路径上引入 150ms 的内部 OCR 去抖。
  Rationale: 现有证据表明长连续变化段会把几乎每个采样点都送入 OCR，但这些变化通常仍属于同一字幕段；固定的短去抖能显著压低默认 `submitted_ocr_frames`，同时只对相邻高频候选生效，不改变 `sample_every=1` 的现有测试语义。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前先保留“进度条总量按真实工作增长”的实现，但不把“惰性 OCR 图像准备”视为已完成的性能收益项。
  Rationale: 进度条对齐已经被真实长视频观测和测试覆盖证明成立；但采样侧惰性准备在真实长视频前缀隔离基准里暂未显示出可确认收益，继续推进时应先做更小步的受控实验，而不是直接把这部分记为已完成优化。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前默认 Paddle 路径继续采用“非采样帧 `grab()`，采样点/末帧 `retrieve()`”的解码策略。
  Rationale: 这是当前已验证收益最明确、且不改变样本级 `ocr_calls` 与准确率的性能优化；相比继续纠结灰度预处理细节，它更直接改善长视频默认路径的前期吞吐。
  Date/Author: 2026-04-02 / Codex

- Decision: 在本轮前缀基准复测完成之前，先接受“不改变候选判定语义但能去掉确定冗余”的小步性能修正，但暂不把 `_collect_checkpoints()` 这条惰性图像准备线标记为闭合。
  Rationale: 提交 OCR 时不再重复灰度化/模糊化是显然正确的局部收敛；但是否对真实长视频吞吐有可观收益，仍需要和现有前缀 benchmark 数据对齐后才能下结论。
  Date/Author: 2026-04-02 / Codex

- Decision: `_collect_checkpoints()` 中“提交路径去掉重复灰度化”这一步现在可以视为已验证完成，但后续不应继续把它当成主要性能突破口。
  Rationale: 前缀 benchmark 已证明该改动在真实长视频上方向正确且不会改变候选计数，但收益只有约 `1.47%`；相比之下，后续若还要继续优化，更值得关注 OCR 调用数、解码策略或 backend 吞吐，而不是继续深挖这条灰度准备路径。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前继续保留“采样时先统一 resize，再把同一张 prepared ROI 同时喂给灰度判定和 OCR 提交”的实现，但下一轮性能工作不再优先盯 ROI 预处理。
  Rationale: 这笔改动能稳定减少 `resize()` 调用次数且不改变候选计数；但最新 profile 也表明，当前前缀路径的绝对大头已经是 `retrieve()` 和 `grab()`，继续深挖 ROI 预处理的边际收益会越来越小。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前不把 `CAP_PROP_CONVERT_RGB=0` 的灰度解码路线合入主线，也不继续在 OpenCV `CAP_PROP_HW_ACCELERATION` 上投入实现时间。
  Rationale: 灰度解码虽然在前缀基准里能带来约 `6%` 的局部加速，但它已经在样本评估中带来 `WER` 回退，违反“性能优化不能牺牲准确率”的主线约束；而硬件加速属性在本机后端上全部设置失败，没有可落地空间。
  Date/Author: 2026-04-02 / Codex

- Decision: 下一阶段主线优先评估“Apple Silicon 可加速的替代运行时”，而不是继续把主要时间投入到当前 Paddle CPU 路径的细粒度微优化。
  Rationale: 现有解码/ROI 细节优化已进入边际收益递减区，而用户优先级首先是运行时间。
  Date/Author: 2026-04-02 / Codex

- Decision: Apple 路线保持官方 `PP-OCRv5` 模型族不变，只替换运行时，不换主模型。
  Rationale: 需要在尽量不破坏当前精度基线的前提下评估 Apple 硬件收益。
  Date/Author: 2026-04-02 / Codex

- Decision: Apple 路线先以新增实验 backend 的形式落地，不直接替换默认 Paddle。
  Rationale: 当前尚未证明其速度和精度都优于现有默认路线。
  Date/Author: 2026-04-02 / Codex

- Decision: Apple 路线优先尝试 `ONNX Runtime + CoreMLExecutionProvider`，本轮不把 Paddle Lite / Metal 作为主线实施方向。
  Rationale: ONNX Runtime 的 CoreML provider 已在本机可用，而 Paddle Lite / Metal 属于另一条 C++/移动端部署链路，工程改造面过大。
  Date/Author: 2026-04-02 / Codex

- Decision: 只有在“几乎不退化”的精度门槛下显著提速，Apple 路线才允许晋级为更强候选后端。
  Rationale: 用户已明确速度优先，但不能接受明显精度回退。
  Date/Author: 2026-04-02 / Codex

- Decision: 既然官方模型转换与 CoreML session 构造已经闭合，下一阶段 Apple 路线从“纯 spike”切换到“实验 backend 的受控样本评估”。
  Rationale: `subx-dev apple-spike` 已证明 det/rec 官方模型可转 ONNX 且主 provider 命中 CoreML；同时 `zh_single_dark` 的首个真实样本结果显示 `onnx-coreml` 已经在保持 `CER/WER=0` 的前提下把耗时压到约 `44.63s`，值得进入更系统的样本对比。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前 `onnx-coreml` backend 先固定依赖默认 cache 根 `/Users/wangyg/.cache/subx/onnx-coreml` 的官方 ONNX 产物，不在 `subx` 提取路径里隐式在线转换模型。
  Rationale: 这样可以把长时间的模型转换与最终用户提取路径解耦，避免首次运行 `subx --engine onnx-coreml` 时把转换成本混进提取耗时，也便于受控 benchmark。
  Date/Author: 2026-04-02 / Codex

- Decision: 在 `onnx-coreml` 明确验证出可控的内存占用之前，当前实现固定只允许单 worker；评估时也不得并行启动多个重命令复用同一台机器的统一内存。
  Rationale: `ProcessPoolExecutor` 会为每个 worker 各自初始化一套 backend，而 `onnx-coreml` 每套 backend 都要持有官方 det/rec ONNX 模型对应的 CoreML + CPU fallback session；多 worker、再叠加多命令并跑，会把统一内存快速放大到不可控区间，已经在真实机器上触发整机失去响应。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前阶段不把 `onnx-coreml` 保留为候选默认后端，也不继续为它消耗长视频前缀 benchmark 时间。
  Rationale: 在同口径 `workers=1` 全样本评估里，`onnx-coreml` 已经在 3/3 样本上都慢于 Paddle，且 `en_double_bright` 的 `CER/WER` 明显回退；既然速度和精度门槛都没有同时通过，就没有必要继续扩大 benchmark 面。
  Date/Author: 2026-04-02 / Codex

- Decision: 如果后续还要继续 Apple 路线，下一轮唯一值得投入的方向是“固定 shape 的官方 ONNX/CoreML 实验”，而不是继续在当前动态 shape 实现上做常规 benchmark。
  Rationale: ORT 官方工具已经把当前瓶颈指向动态 shape；在不解决这个前提问题之前，继续调整 worker、评估命令或长视频样本，只会重复验证一条已知失败的实现。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前 `onnx-coreml` 实现继续保留 CoreML cache 与 `MLProgram -> NeuralNetwork` 的自动回退，这两项作为实验路线的基础设施保留，但不改变它“非候选后端”的结论。
  Rationale: CoreML cache 对 warm run 有真实收益，自动回退也避免了 det 模型在 `MLProgram` 下直接不可用；但这两项改进仍不足以跨过当前速度/精度门槛，最多只说明后续 fixed-shape spike 有一个更干净的起点。
  Date/Author: 2026-04-02 / Codex

- Decision: 按用户最新指令，当前正式终止 Apple/CoreML 路线，仓库活跃主线回到官方 PaddleOCR；不再继续保留 `onnx-coreml` 与 `apple-spike` 的产品化入口。
  Rationale: 这条路线已经在当前实现下被证明不满足“速度优先”的目标，且用户已明确要求回到原来的官方 PaddleOCR 路线；继续保留活跃入口只会增加维护面和误用风险。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前不把 `text_det_limit_side_len` 下调作为官方 Paddle 路线的主线优化方向。
  Rationale: 这类调整会直接改变 det 的输入几何和检测行为；虽然在极小 ROI 微基准里可能显得很快，但全样本评估已经证明它会带来精度回退，并且不保证端到端 wall time 更好。
  Date/Author: 2026-04-02 / Codex

- Decision: 官方 Paddle 路线的默认内部 OCR 去抖当前收敛到 `200ms`，而不是旧的 `150ms` 或更激进的 `250ms`。
  Rationale: `200ms` 是当前最靠近“速度优先但不破坏 cue 对齐”的点：它在真实 `samples/` 评估里保持了 3/3 样本 `overlap_hit_rate=1.0` 与既有文本指标，而 `250ms` 已经在 `mixed_double_dark` 上造成明显的时间对齐回退。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前不为 Paddle 主线引入单 worker 批量 `predict(list)` 调度或额外的批次 API 包装。
  Rationale: 受控实验已经证明，在当前 PaddleOCR 3.4.0 包装层上这条路几乎没有端到端收益；继续为它扩展 backend 接口和测试，只会增加复杂度而不换来明显 wall-time 改善。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前默认 ROI 收敛到 `0.15,0.8,0.7,0.2`，把全宽底部 ROI 改为“底部中间 70% 宽度”。
  Rationale: 当前样本标签一致指向“bottom-centered + non-full-width”，而真实评估也表明这项收窄能在不破坏 `overlap_hit_rate` 的前提下带来最明显的 wall-time 改善；若用户遇到靠边或近全宽字幕，仍可显式用 `--roi` 覆盖。
  Date/Author: 2026-04-02 / Codex

- Decision: 上述“默认 ROI 收窄到中心 70% 宽度”的结论不再作为当前主线默认值；默认 ROI 已回退为全宽底部 `0,0.8,1,0.2`。
  Rationale: 真实长视频前缀已经证明，样本集上的加速不能直接外推到常规视频；在当前 `resize_max_width=1280` 的实现下，单独收窄宽度会抬高进入 OCR 的像素高度，并让长视频上的单次 OCR 变慢。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前把“单/双行默认高度”转成了按视频尺寸和 ROI 宽度反推的结构化 CLI，而不是继续只暴露一个固定 `x,y,w,h` 字符串。
  Rationale: 用户真正要控制的是宽度、高度和离底部偏移；同时如果已经知道单行/双行字幕的大致目标高度，就应该让进入 OCR 的实际像素高度贴近这个目标，而不是简单套一个固定归一化高度。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前单行 preset 先按“prepared height≈100.8px”收敛，双行 preset 先按“prepared height≈144px”收敛；显式 `--roi-height` 仍保留为手动覆盖。
  Rationale: 现有样本显示单行在全宽底部 ROI 下 `h≈0.14` 最稳且比更高值更快；双行样本则至少需要 `h≈0.20` 才不明显退化。把这两个结论转换为 prepared-height 目标后，ROI 宽度变化时也能保持更一致的 OCR 输入几何。
  Date/Author: 2026-04-02 / Codex

- Decision: 结构化 ROI 的最终用户参数名收敛为 `--lines/-l`、`--width/-w`、`--height/-H`、`--bottom-offset/-b`，并以 `--lines=single` 作为默认预设入口。
  Rationale: 这是比旧的 `--subtitle-lines` / `--roi-width` / `--roi-height` 更短、更直接的接口；同时 `-h` 必须留给 help，因此高度简写固定使用 `-H`。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前不能把默认 ROI 宽度直接收窄到 `0.8` 或 `0.85`；在剩余更宽档位完成前，默认宽度继续保持 `1.0`。
  Rationale: prepared-height 反推已经消除了“宽度变窄导致 prepared height 变高”的缩放副作用，但最新样本评估表明双行字幕在 `0.8/0.85` 上仍出现明显精度回退，因此这两档不能作为主线默认值。
  Date/Author: 2026-04-02 / Codex

- Decision: `lines` 预设的最终形态应当同时产出默认 `width` 和默认 `height`，而不是只让 `lines` 决定高度。
  Rationale: 新一轮 ROI 评估已经证明单行和双行不仅垂直尺寸不同，横向安全区间也不同；如果还让两者共用同一个默认宽度，就会把“单行可更窄、双行需更宽”的结构性差异丢掉。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前 `lines` 默认 preset 收敛为 `single -> width=0.75 + prepared_height≈100.8px`，`double -> width=1.0 + prepared_height≈144px`。
  Rationale: `single=0.75` 在现有单行样本上明显优于旧的 `0.85`，且在真实长视频前缀上没有额外吞吐代价；而 `double` 虽然可通过进一步增高来换取精度，但在“速度优先”的前提下，`151.2px` 和 `158.4px` 的长视频 OCR 成本上升过于明显，因此当前仍保留 `144px` 基线并维持全宽。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前默认内部 OCR 去抖从 `200ms` 上调到 `225ms`。
  Rationale: 用户已明确接受一定精度牺牲，以换取更少的 OCR 调用次数；现有实验表明 `225ms` 已能把 `mixed_double_dark/zh_single_dark` 的 submitted 大幅打到 `33/25`，而进一步到 `250ms` 不会明显再降调用，因此当前先收敛到更小的 `225ms`。
  Date/Author: 2026-04-02 / Codex

- Decision: `subx` 的默认 `sample_every` 当前收敛到统一的 `6`。
  Rationale: 双行路径早已证明 `6` 成立；单行路径在新的默认门限 `0.86` 下也已经确认 `6` 比旧的 `5` 更快，而且不再引入新的文本退化。因此当前用户路径没有必要继续保留按 `lines` 区分的采样默认值。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前不再继续上探双行默认 `sample_every` 到 `7` 或 `8`；`double` 路径固定保留 `6`。
  Rationale: 最新双行受控实验已经表明，`7/8` 虽然继续降低 `sampled_frames`，但会把 `mixed_double_dark` 的 OCR 调用从 `34` 放大到 `56/52`，并让真实长视频前缀的 `submitted_ocr_frames` 从 `616` 上升到 `965/873`。这类回退直接违背了“减少 OCR 调用次数优先”的当前主线目标。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前单行默认 `sample_every` 继续保留在 `5`，暂不直接上调到 `6`。
  Rationale: `6` 虽然在真实长视频前缀上进一步减少了 `submitted_ocr_frames` 并把 wall time 从约 `123.48s` 压到约 `111.80s`，但在 `zh_single_dark` 上已经回退到 `CER≈0.3429 / WER≈0.6667 / overlap≈0.6667`。在用户允许“适当”牺牲精度的前提下，这个幅度仍然偏大，当前更合理的做法是继续寻找更细粒度的过滤策略，而不是直接把默认单行采样再抬高一档。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前默认 `ocr_candidate_similarity_threshold` 从 `0.97` 下调到 `0.86`。
  Rationale: 这是当前已验证“安全边界”里更激进的一档。相比 `0.9`，`0.86` 继续减少单行和双行路径的 OCR 提交量，而现有样本的 `CER/WER/overlap` 仍未出现新的退化；同时 `0.85` 已经明确打坏单行，因此当前把默认值收在 `0.86`，比继续保守停在 `0.9` 更符合“运行时间优先，但只适度牺牲精度”的主线目标。
  Date/Author: 2026-04-02 / Codex

- Decision: `subx` 的用户路径把 OCR 候选相似度门限也做成 `lines` 相关默认值：`single=0.86`、`double=0.8`；`subx-dev` 暂不跟进这条差异化默认。
  Rationale: 双行路径已经证明可以比单行更激进，而 `subx` 才是最终用户主入口。先把这条差异化默认固化到用户路径，可以直接换取真实运行时间收益，同时避免把研发评估入口和历史基线一起扰动过大。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前 `subx` 的默认 `sample_every` 统一收敛到 `6`。
  Rationale: 单行路径在新默认门限 `0.86` 下已经证明 `sample_every=6` 不再带来早期那种文本退化，反而在样本和真实长视频前缀上都继续减少 OCR 提交并缩短 wall time。因此当前用户路径没必要再保留 `single=5`、`double=6` 的差异化采样默认。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前不把“动态采样回退”并入主线，无论是全局启用还是只挂到 `sample_every=6` 的双行路径，都视为已拒绝方案。
  Rationale: 这条路线虽然能继续压低 `sampled_frames`，但全局启用会直接打坏 `zh_single_dark`，而双行限定版也没有形成比固定采样更好的 wall time 或文本指标，不值得增加实现复杂度。
  Date/Author: 2026-04-02 / Codex

- Decision: 当前默认 `workers` 从 `4` 上调到 `6`，并继续保留最终用户和研发命令的一致默认值。
  Rationale: 最新同口径 Paddle benchmark 表明 `workers=6` 在现有样本上稳定快于 `1/2/4`，而 `workers=8` 已在较重样本上出现轻微回退；在用户优先级以运行时间为先的前提下，`6` 是当前更合适的默认点。
  Date/Author: 2026-04-02 / Codex

- Decision: entry-debounce 不直接替换当前默认单行路径，而是先作为 `subx --speed-profile aggressive` 的显式性能档位落地，并只作用于 `single`。
  Rationale: 这条策略在真实长视频前缀上能把单行路径的 wall time 从约 `81s` 压到约 `53s`，但会明显牺牲 cue 对齐，不适合静默覆盖当前默认行为；做成显式性能档位，既能把高收益策略交给愿意接受精度回退的用户，也能保住默认 `balanced` 路径的稳定性。
  Date/Author: 2026-04-02 / Codex

## Outcomes & Retrospective

当前阶段已经完成“把项目从试验脚本重构为职责清晰的工作树”这一目标，也已经基于现有证据确认默认 OCR backend 继续维持 Paddle。可以认为基础设施、命令边界和当前默认路线都已稳定；最新一轮 TDD 也已经把长视频内存防线、单 worker backend 复用和用户输出静默这三项关键约束落进实现。关键剩余工作只在于是否还要继续投入 ONNX 调优，以及如何进一步优化长视频吞吐。

阶段性结果符合预期的一半：包结构、CLI、测试、样本格式和 Paddle 路线都已经成形，而且 Paddle 的全样本基线报告现已落地；不符合预期的一半是 ONNX 路线仍明显慢于 Paddle，当前多 worker 也没有带来足够的吞吐改善，且在已测英文样本上精度也更差。后续线程应继续避免无方向尝试，把 ONNX 问题拆成“吞吐、并发、准确率”三类验证步骤，但主线已可以先围绕 Paddle 收口。

当前 CPU 路径上的局部优化已经证明主线实现可持续收敛，但继续深挖同一条路径不太可能再带来量级变化。Apple 路线的技术验证和受控评估也已经给出了足够清晰的结论：当前“官方 ONNX + 动态 shape + CoreML EP”实现既没有速度优势，也在英文样本上出现了精度回退。基于这个结论，加上用户已明确要求回到原来的官方 PaddleOCR 路线，本阶段的正确收尾是终止 Apple/CoreML 的活跃代码入口，把仓库主线重新收口到官方 PaddleOCR，而不是继续扩展实验分支。回到 Paddle 主线后，本轮闭合的有效结论是：`text_det_limit_side_len=192` 已被证明是误导性方向，单 worker 批量 `predict(list)` 没有形成真实收益，内部 OCR 去抖在“精度优先”阶段曾收敛到 `200ms`，而在用户明确接受一定精度牺牲后，当前主线已进一步上调到 `225ms` 以换取更少 OCR 调用；同时，`lines` preset 现在不仅控制默认宽高，也控制用户路径下的默认采样与相似度门限，当前已收敛到统一的 `sample_every=6`、`single threshold=0.86`、`double threshold=0.8`，且单行默认宽度已从旧的 `0.85` 收敛到 `0.75`。最新一轮“动态采样回退”实验也已经闭合：它虽然能继续压低 `sampled_frames`，但无论全局启用还是只限于 `sample_every=6` 的双行路径，都没能形成值得保留的速度/精度平衡，因此当前主线继续维持固定采样频率。ROI 这条线最终沉淀下来的正向产物，则是结构化 ROI CLI、`lines` 同时控制默认宽高和默认采样间隔的 preset 机制，以及“single 可比 double 更窄，但 double 在速度优先约束下仍应维持全宽 + 现有高度基线”这一新的默认边界。

## Context and Orientation

当前工作树的关键路径如下：

- `pyproject.toml`：项目依赖，以及 `subx` / `subx-dev` 两个入口定义。
- `src/subx/cli.py`：最终用户提取命令入口。
- `src/subx/dev_cli.py`：仓库内部评估与基准命令入口。
- `src/subx/pipeline.py`：顺序解码、ROI 裁剪、变化检测、OCR 调度、字幕合并。
- `src/subx/ocr/paddle_backend.py`：PaddleOCR backend。
- `src/subx/ocr/paddle_models.py`：官方 `PP-OCRv5_server_det/rec` 的 Hugging Face snapshot 解析与缓存目录定位。
- `src/subx/ocr/onnx_backend.py`：基于 `monkt/paddleocr-onnx` + `rapidocr-onnxruntime` 的 ONNX backend。
- `src/subx/eval.py`：样本集发现、准确率指标、Markdown/JSON 报告。
- `tests/`：当前只覆盖纯函数与指标层，不覆盖真实 OCR 推理。
- `samples/`：已有 3 组样本，包含 `zh_single_dark`、`mixed_double_dark`、`en_double_bright`。

几个项目内术语需要固定理解：

- `ROI`：标准化矩形区域，格式为 `x,y,w,h`，相对于完整视频帧。
- `mixed`：中英混合识别配置，不代表自动语言检测。
- `baseline`：当前阶段指 Paddle 路线，而不是旧的 RapidOCR 单脚本。
- `smoke test`：在单个样本上验证命令能否端到端跑通，不等于准确率通过。

当前工作树已经不再使用 `main.py`。后续如果新线程看到删除的旧入口，不要尝试恢复向后兼容，除非产品要求重新改变。

## Plan of Work

后续实施按四条线并行，但必须由主 agent 统一节奏。主 agent 使用 `gpt-5.4` 且 `reasoning_effort=high`，负责维护 `PLANS.md`、安排每轮谁改什么文件，确保测试 agent、评估 agent、文档 agent 不同时写同一文件。评估线也使用 `gpt-5.4` 且 `reasoning_effort=high`，由评估 agent 负责把现有样本跑全，整理 Paddle 基线报告，并把 ONNX 问题压缩成可复现的最小步骤。实现线、测试线、文档线默认优先交给 `gpt-5.4-mini`，分别负责代码实现、测试扩展和文档同步。

OCR 选型的正式决策顺序必须固定。当前已经完成 Paddle 路线的 `subx-dev eval ./samples` 基线报告，也完成了现有 RapidOCR ONNX 路线和 Apple/CoreML 路线的受控排除：前者在真实样本上吞吐优势不足，后者则在当前实现下同时没过速度和精度门槛。因此下一步不应再把主要时间投入到替代运行时探索，而应继续围绕官方 PaddleOCR 主线收敛，把后续优化限制在“明确假设 + 小步实验 + 全样本复核”这个闭环里。

当前主线的优化优先级也需要固定。第一层优先减少无价值 OCR 调用，并且必须用 `samples/` 全样本验证 cue 对齐不退化；第二层才是继续抠解码与预处理中的确定冗余；直接改 det/rec 输入形状、替换 backend 或重新扩大 ONNX/CoreML 试验，都不再是当前阶段的默认动作。已经闭合的最近一轮实验表明，`200ms` 内部 OCR 去抖是当前可以保留的默认值，而更激进的 `250ms` 和更激进的 det 输入下调都应视为已拒绝方案。

如果后续发现 `pipeline.py` 现有结构对调试 ONNX 不友好，可以做局部重构，但要保持三个事实不变：最终用户 CLI 名仍为 `subx`；样本评估接口仍是 `subx-dev eval`；`PLANS.md` 必须始终是最新的恢复点。

## Concrete Steps

工作目录：`/Users/wangyg/Development/Working/subtitle-extractor`

1. 主 agent 启动新线程后，先读 `PLANS.md`、`AGENTS.md`、`README.md`，再决定子 agent 写入边界。
   期望：新线程无需回看旧聊天，也能知道当前基线、冻结点和分工。

2. 测试子 agent 运行：

       uv run python -m unittest discover -s tests -v

   期望：当前 42 个测试全部通过。

3. 评估子 agent 先复现当前 Paddle 主线基线，作为后续微调的对照组：

       uv run subx-dev eval ./samples --engine paddle --json /tmp/eval-paddle-baseline.json --report /tmp/eval-paddle-baseline.md

   期望：命令成功结束，并产出可作为后续 Paddle 微调对照的 JSON / Markdown 报告。

4. 实现子 agent 的后续性能实验必须先给出明确假设，再做受控验证。当前优先级最高的方向是继续减少默认 `sample_every > 1` 路径下的冗余 OCR 提交，或在不改变候选判定语义的前提下减少单次提取的固定开销。
   当前状态：`_OCR_SUBMISSION_DEBOUNCE_SECONDS=0.225` 已在当前目标下通过受控验证；`text_det_limit_side_len=192`、动态采样回退、灰度解码和 Apple/CoreML 路线都已被排除，不应重复投入。

5. 文档子 agent 每完成一个里程碑，都要同步：

       README.md
       AGENTS.md
       PLANS.md

   期望：文档中的命令、当前状态、默认路线、已知阻塞保持一致。

补充协作约束：

- 主 agent 可以改任何文件，但应尽量避免和子 agent 写入重叠。
- 评估子 agent 只提交评估证据、复现步骤、结论建议，不直接拍板默认 backend。
- 实现子 agent、测试子 agent、文档子 agent 不应直接修改 `PLANS.md` 的决策性章节；如需更新，由主 agent 合并。

6. 每完成一轮 Paddle 主线实验后，都要重新执行：

       uv run subx-dev eval ./samples --engine paddle --workers 1 --json /tmp/eval-paddle-next.json --report /tmp/eval-paddle-next.md

   前置条件：实验必须先写入 `PLANS.md` 的 live 区块，明确假设、风险和验收门槛。
   期望：同时产出 Markdown 报告和 JSON 报告，并重新核对各样本的 `CER / WER / cue 指标 / elapsed_seconds / ocr_calls`；只要 `overlap_hit_rate` 或 cue 对齐退化，就立即拒绝该方案。

## Validation and Acceptance

后续阶段的验收不看“代码写了多少”，只看下面这些可观察行为：

- 执行 `uv run --python 3.12 python -m unittest discover -s tests -v`，当前测试全部通过。
- 执行 `uv run --python 3.12 subx --help`，应显示直接提取视频的顶层参数，而不是 `eval` / `bench` 子命令。
- 执行 `uv run --python 3.12 subx-dev --help`，可见 `eval`、`bench` 两个研发子命令。
- 执行 Paddle 基线命令后，能在指定路径得到 `.srt` 文件，并看到 JSON stats。
- 执行 ONNX 提取命令后，采样阶段结束时应能立即看到 `OCR (onnx)` 进度，而不是长时间完全无输出。
- 执行 `subx-dev eval ./samples` 后，能得到 JSON 和 Markdown 报告，而不是中途卡住或崩溃。
- 默认 backend 的最终选定必须基于样本报告，而不是口头判断；报告中至少要包含 CER、WER、cue exact match、overlap hit rate、总耗时、OCR 调用次数。

## Idempotence and Recovery

大部分步骤可安全重跑：

- `uv sync` 可重复执行，主要风险是重新解析 lock 和重新检查 Python 版本。
- `python -m unittest discover` 可重复执行，无持久副作用。
- `subx` 可重复执行，只会覆盖指定输出文件。
- `subx-dev eval` / `subx-dev bench` 可重复执行，但应避免把结果文件写到彼此冲突的位置。

需要谨慎的是 ONNX 调试：当前它在顺序 OCR 阶段可能出现数分钟静默。如果再次复现，优先在独立命令或最小脚本里定位，不要同时启动多条 ONNX 完整流水线，以免混淆是模型下载慢、推理慢还是命令卡死。

## Artifacts and Notes

- 纯函数测试已通过：

      uv run --python 3.12 python -m unittest discover -s tests -v
      OK

- 新 CLI 边界已验证：

      uv run --python 3.12 subx --help
      uv run --python 3.12 subx-dev --help

  结果摘要：

      `subx` 只显示直接提取视频的顶层参数
      `subx-dev` 显示 `eval`、`bench` 两个研发子命令

- TDD 回归测试已通过：

      uv run --python 3.12 python -m unittest discover -s tests -v

  结果摘要：

      当前共 26 项测试通过
      已覆盖 CLI 边界、分批 flush、单 worker backend 复用、多 worker 进程池复用、Paddle 导入/初始化静默、HF snapshot 下载与缓存目录约束、统一 progress reporter 接口、OCR 候选二次筛选

- Paddle smoke test 已通过：

      uv run --python 3.12 subx samples/zh_single_dark/clip.mp4 --engine paddle --lang zh --workers 1 --sample-every 6 --output /tmp/subx-zh-paddle.srt

  结果摘要：

      total_frames=540
      sampled_frames=90
      submitted_ocr_frames=45
      reused_frames=45
      produced_cues=3
      elapsed_seconds≈97.71

- 新 `subx` 轻量 smoke test：

      uv run --python 3.12 subx samples/zh_single_dark/clip.mp4 --engine paddle --lang zh --workers 1 --sample-every 180 --output /tmp/subx-cli-smoke.srt

  结果摘要：

      sampled_frames=3
      submitted_ocr_frames=3
      produced_cues=0
      elapsed_seconds≈6.87

- 新 `subx` 静默 smoke test：

      uv run --python 3.12 subx samples/zh_single_dark/clip.mp4 --engine paddle --lang zh --workers 1 --sample-every 180 --output /tmp/subx-quiet-smoke-3.srt

  结果摘要：

      终端只显示 `Sampling` 进度和最终 JSON
      不再泄露 Paddle connectivity/model/cache 等系统提示
      elapsed_seconds≈4.32

- 新 Paddle HF cache smoke test：

      uv run --python 3.12 subx samples/zh_single_dark/clip.mp4 --engine paddle --lang zh --workers 1 --sample-every 180 --output /tmp/subx-hf-cache-smoke.srt

  结果摘要：

      终端只显示 `Sampling` 进度和最终 JSON
      `sampled_frames=3`
      `submitted_ocr_frames=3`
      `produced_cues=0`
      `elapsed_seconds≈5.11`
      Paddle v5 模型 snapshot 已落在 `~/.cache/huggingface/hub/models--PaddlePaddle--PP-OCRv5_server_{det,rec}/snapshots/...`

- 新单一 progress smoke test：

      uv run --python 3.12 subx samples/zh_single_dark/clip.mp4 --engine paddle --lang zh --workers 1 --sample-every 180 --output /tmp/subx-progress-smoke.srt

  结果摘要：

      终端只显示单一 `Extracting` 进度条
      postfix 持续显示 `frames` / `ocr` 计数
      结束时为 `ocr | frames 540/540 | ocr 3/3`
      `elapsed_seconds≈4.80`

- 新多 worker 复用池 smoke test：

      subx samples/zh_single_dark/clip.mp4 --workers 2 --sample-every 3 --output /tmp/subx-w2-smoke.srt

  结果摘要：

      `sampled_frames=180`
      `submitted_ocr_frames=83`
      `produced_cues=3`
      `elapsed_seconds≈41.70`
      当前实现已不再在每个 OCR flush 时重建进程池

- 新 OCR 候选二次筛选 smoke test：

      subx samples/zh_single_dark/clip.mp4 --output /tmp/subx-sim-smoke-default.srt

  结果摘要：

      `sampled_frames=181`
      `submitted_ocr_frames=57`
      `reused_frames=124`
      `produced_cues=3`
      `elapsed_seconds≈30.37`
      相比筛选前同样本默认参数的 `submitted_ocr_frames=83`，下降约 `31%`

- 新 Paddle 全样本评估结果：

      uv run --python 3.12 subx-dev eval ./samples --engine paddle --json /tmp/eval-paddle-after-filter.json --report /tmp/eval-paddle-after-filter.md

  结果摘要：

      `en_double_bright`: `CER=0.06`, `WER≈0.2121`, `ocr_calls=7`, `elapsed≈9.75s`
      `mixed_double_dark`: `CER≈0.00885`, `WER≈0.1579`, `ocr_calls=91`, `elapsed≈36.62s`
      `zh_single_dark`: `CER=0.0`, `WER=0.0`, `ocr_calls=57`, `elapsed≈19.71s`
      当前样本上未观察到准确率退化

- 真实长视频短时观测：

      subx /Users/wangyg/Downloads/RBD-648-UC/RBD-648-UC.compressed.mp4

  结果摘要：

      这是人工中断的短时对比，不是完整跑完的 benchmark
      新版在约 `1m27s` 时推进到 `2305/438955`
      旧版 terminal 记录是在约 `1m50s` 才到 `2305/438955`
      说明长视频前期推进速度已有改善，但默认参数整体仍然偏慢，后续仍需继续优化 OCR 吞吐

- 默认 Paddle 路径真实长视频复验：

      uv run --python 3.12 subx /Users/wangyg/Downloads/RBD-648-UC/RBD-648-UC.compressed.mp4 --output /tmp/RBD-648-UC.default-validation.srt

  结果摘要：

      这是人工 `Ctrl-C` 中断的短时验证，不是完整跑完的 benchmark
      本轮约 `1m40s` 已推进到 `4488/438955`
      约 `1m47s` 时推进到 `4586/438955`
      全程保持单一 `Extracting` 进度条
      总量维持在 `438955` 基线上，没有出现采样结束后回缩总量
      说明默认路径的前期推进速度继续改善，且当前进度条对齐优于旧记录；但整体默认吞吐仍偏慢

- 当前进度条总量按真实工作增长的长视频复验：

      uv run --python 3.12 subx /Users/wangyg/Downloads/RBD-648-UC/RBD-648-UC.compressed.mp4 --output /tmp/RBD-648-UC.post-lazy-prep.srt

  结果摘要：

      这是人工 `Ctrl-C` 中断的短时验证，不是完整 benchmark
      起始总量为真实 `frame_count=329216`
      约 `0:51` 时推进到 `2360/329401`
      约 `1:30` 时推进到 `3126/329472`
      约 `1:47` 时推进到 `3625/329536`
      总量会随实际排队的 OCR 工作增长，不再预先加上 `max_sampled_frames`

- 长视频前缀隔离基准：

      PYTHONPATH=src uv run --python 3.12 python - <<'PY'
      # 比较 eager / lazy_current / gray_no_resize 三种前缀采样路径
      PY

  结果摘要：

      `eager`: `26.793s`, `sampled=4000`, `submitted=1040`, `reused=2960`
      `lazy_current`: `26.996s`, `sampled=4000`, `submitted=1040`, `reused=2960`
      `gray_no_resize`(实验性): `26.676s`, `submitted=1093`
      结论：当前 lazy 实现尚未证明出可确认收益；实验性 no-resize-gray 虽略快，但会改变候选判定，不可直接采用

- `grab()/retrieve()` 长视频前缀基准：

      PYTHONPATH=src uv run --python 3.12 python - <<'PY'
      # 比较 read() 与 grab()/retrieve() 两种前缀采样路径
      PY

  结果摘要：

      `read`: `33.602s`, `sampled=4001`, `submitted=1040`, `reused=2961`
      `grab`: `15.987s`, `sampled=4001`, `submitted=1040`, `reused=2961`
      结论：在保持候选判定结果不变的前提下，`grab()/retrieve()` 在真实长视频前缀上显著更快

- `grab()/retrieve()` 后的 Paddle 全样本验证：

      uv run --python 3.12 subx-dev eval ./samples --engine paddle --json /tmp/eval-paddle-post-grab.json --report /tmp/eval-paddle-post-grab.md

  结果摘要：

      `en_double_bright`: `CER=0.06`, `WER≈0.2121`, `ocr_calls=7`, `elapsed≈6.59s`
      `mixed_double_dark`: `CER≈0.00885`, `WER≈0.1579`, `ocr_calls=49`, `elapsed≈20.44s`
      `zh_single_dark`: `CER=0.0`, `WER=0.0`, `ocr_calls=36`, `elapsed≈14.50s`
      当前样本上未观察到准确率或 OCR 调用次数退化

- 已安装 CLI 的默认参数真实测试：

      uv tool install --python 3.12 --force --editable .
      subx samples/zh_single_dark/clip.mp4

  结果摘要：

      `subx` / `subx-dev` 已成功安装
      终端只显示单一 `Extracting` 进度条
      默认输出路径为 `samples/zh_single_dark/clip.srt`
      `sampled_frames=180`
      `submitted_ocr_frames=83`
      `reused_frames=97`
      `produced_cues=3`
      `elapsed_seconds≈43.71`

- ONNX smoke test 原冻结命令：

      uv run --python 3.12 subx samples/zh_single_dark/clip.mp4 --engine onnx --lang zh --workers 1 --sample-every 6 --output /tmp/subx-zh-onnx.srt

  旧现象：采样进度条完成后，多次轮询仍无进一步输出，也未正常结束。

- ONNX 最小复现与新证据：

      uv run --python 3.12 python - <<'PY'
      ...
      backend = OnnxBackend('zh')
      result = backend.recognize(ocr_frame)
      print(result)
      PY

  结果摘要：

      backend 初始化成功
      单张 ROI recognize() 成功返回
      `samples/zh_single_dark` 前 7 个候选帧单次识别约 6.4s 到 11.5s

- OCR 可观测性补丁：

      uv run --python 3.12 subx samples/zh_single_dark/clip.mp4 --engine onnx --lang zh --workers 1 --sample-every 6 --output /tmp/subx-zh-onnx-progress.srt

  结果摘要：

      采样完成后出现 `OCR (onnx)` 进度条
      现场观测到 `6/45 [00:34<03:43, 5.74s/frame]`

- ONNX smoke test 当前结论：

      sampled_frames=90
      submitted_ocr_frames=45
      produced_cues=3
      elapsed_seconds=224.34

  结论：命令可完成；当前首要问题已从“未闭合”切换为“顺序 OCR 吞吐偏慢”。

- ONNX 多 worker 吞吐证据：

      workers=1: elapsed_seconds=224.34
      workers=2: elapsed_seconds=209.9458993330045
      workers=4: 中途观测到至少 17/45，但未显示出明显更快的早期进度

  结论：当前样本上 `workers=2` 只提升约 6.4%，不足以支撑直接进入 `subx-dev eval ./samples --engine all`。

- Paddle 全样本基线报告：

      uv run --python 3.12 subx-dev eval ./samples --engine paddle --json ./eval-paddle.json --report ./eval-paddle.md

  结果摘要：

      en_double_bright: CER=0.06, WER≈0.2121, elapsed_seconds≈10.22
      mixed_double_dark: CER≈0.00885, WER≈0.1579, elapsed_seconds≈39.53
      zh_single_dark: CER=0.0, WER=0.0, elapsed_seconds≈28.20

- 新 `subx-dev eval` 轻量 smoke test：

      uv run --python 3.12 subx-dev eval /tmp/subx-one-sample --engine paddle --json /tmp/subx-dev-eval-smoke.json --report /tmp/subx-dev-eval-smoke.md

  结果摘要：

      en_double_bright: CER=0.06, WER≈0.2121, elapsed_seconds≈7.10

- 默认采样路径新增 150ms OCR 去抖后的 Paddle 全样本验证：

      uv run --python 3.12 subx-dev eval ./samples --engine paddle --json /tmp/eval-paddle-post-debounce.json --report /tmp/eval-paddle-post-debounce.md

  结果摘要：

      en_double_bright: CER=0.06, WER≈0.2121, ocr_calls=7, elapsed_seconds≈5.84
      mixed_double_dark: CER≈0.00885, WER≈0.1579, ocr_calls=49, elapsed_seconds≈19.28
      zh_single_dark: CER=0.0, WER=0.0, ocr_calls=36, elapsed_seconds≈13.49

  结论：当前去抖改动在 3 组 Paddle 样本上继续压低 `submitted_ocr_frames` / `ocr_calls`，且未观察到 CER/WER 回退。

- ONNX 受控英文样本对比：

      uv run --python 3.12 subx-dev eval /tmp/subx-one-sample --engine onnx --json /tmp/subx-onnx-en.json --report /tmp/subx-onnx-en.md

  结果摘要：

      en_double_bright: CER=0.14, WER≈0.3636, elapsed_seconds≈21.78

  结论：在当前最轻样本上，ONNX 相比 Paddle 同时更慢且更差。

## Interfaces and Dependencies

当前必须存在的对外接口：

- CLI 入口：`subx = "subx.cli:main"`
- 仓库内部入口：`subx-dev = "subx.dev_cli:main"`
- 最终用户命令：
  - `subx <video>`
- 仓库内部命令：
  - `subx-dev eval <samples_dir>`
  - `subx-dev bench <samples_dir>`
- 样本约定：
  - `samples/<sample_id>/clip.mp4`
  - `samples/<sample_id>/truth.srt`
  - `samples/<sample_id>/meta.json`

当前关键依赖：

- `paddleocr`
- `paddlepaddle`
- `rapidocr-onnxruntime`
- `huggingface_hub`
- `opencv-python`
- `numpy`
- `tqdm`

如果后续要改默认 backend、样本元数据格式或 CLI 子命令，必须同步更新：

- `README.md`
- `AGENTS.md`
- `PLANS.md`
- 对应测试与验证命令

## Live 文档维护规则

后续每次新线程暂停前，主 agent 必须至少检查四件事：

- `Progress` 是否真实反映当前状态
- `Surprises & Discoveries` 是否补上了新发现
- `Decision Log` 是否记录了新的选型变化
- `Artifacts and Notes` 是否补上了最近一次关键验证结果

如果 ONNX 最终跑通，或默认 backend 发生变化，不要只改 `Decision Log`。必须同步改 `Progress`、`Plan of Work`、`Validation and Acceptance`、`Artifacts and Notes`。

## 本次修订说明

- 初始创建：2026-04-02，将当前已完成的重构、Paddle smoke test、ONNX 冻结点和后续多 agent 分工全部落盘，供后续新线程直接接手。
