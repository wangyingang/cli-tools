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
- [ ] (2026-04-02) 已尝试把 `_collect_checkpoints()` 的 OCR 图像准备改成惰性，但当前隔离前缀基准尚未证明出实益；这部分性能优化未闭合，恢复额度后应继续以真实长视频前缀基准为准收敛。
- [ ] 如后续仍需推进 ONNX，补做有明确调优假设的受控对比，而不是直接扩大到全样本 `--engine all`。

## Surprises & Discoveries

- Observation: 当前环境最初没有安装 `numpy`、`opencv-python`、`tqdm`、`rapidocr-onnxruntime`、`huggingface_hub`、`paddleocr`、`paddlepaddle`，因此一开始只能做纯函数层验证。
  Evidence: 在仓库根目录运行 `python3 - <<'PY' ... __import__(mod) ... PY` 时，这些模块均返回 `No module named ...`。

- Observation: 项目切到 Python 3.12 后，`uv sync` 可以成功解析并安装 PaddleOCR、PaddlePaddle、RapidOCR ONNX Runtime 等依赖。
  Evidence: `uv sync` 成功创建 `.venv`，安装了 `paddleocr==3.4.0`、`paddlepaddle==3.3.1`、`rapidocr-onnxruntime==1.4.4` 等 71 个包。

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

## Outcomes & Retrospective

当前阶段已经完成“把项目从试验脚本重构为职责清晰的工作树”这一目标，也已经基于现有证据确认默认 OCR backend 继续维持 Paddle。可以认为基础设施、命令边界和当前默认路线都已稳定；最新一轮 TDD 也已经把长视频内存防线、单 worker backend 复用和用户输出静默这三项关键约束落进实现。关键剩余工作只在于是否还要继续投入 ONNX 调优，以及如何进一步优化长视频吞吐。

阶段性结果符合预期的一半：包结构、CLI、测试、样本格式和 Paddle 路线都已经成形，而且 Paddle 的全样本基线报告现已落地；不符合预期的一半是 ONNX 路线仍明显慢于 Paddle，当前多 worker 也没有带来足够的吞吐改善，且在已测英文样本上精度也更差。后续线程应继续避免无方向尝试，把 ONNX 问题拆成“吞吐、并发、准确率”三类验证步骤，但主线已可以先围绕 Paddle 收口。

## Context and Orientation

当前工作树的关键路径如下：

- `pyproject.toml`：项目依赖，以及 `subx` / `subx-dev` 两个入口定义。
- `src/subx/cli.py`：最终用户提取命令入口。
- `src/subx/dev_cli.py`：仓库内部评估与基准命令入口。
- `src/subx/pipeline.py`：顺序解码、ROI 裁剪、变化检测、OCR 调度、字幕合并。
- `src/subx/ocr/paddle_backend.py`：PaddleOCR backend。
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

OCR 选型的正式决策顺序必须固定。当前已经完成 Paddle 路线的 `subx-dev eval ./samples` 基线报告，也完成了 ONNX 的受控单样本对比：backend 级最小复现证明 ONNX 可运行，但 `workers=2` 的真实样本测试只带来有限收益，而英文小样本上 ONNX 还同时更慢且更差。因此下一步不应直接扩大到 `--engine all`，而应把主线继续收拢到 Paddle，并仅在明确调优假设下追加 ONNX 试验。

如果后续发现 `pipeline.py` 现有结构对调试 ONNX 不友好，可以做局部重构，但要保持三个事实不变：最终用户 CLI 名仍为 `subx`；样本评估接口仍是 `subx-dev eval`；`PLANS.md` 必须始终是最新的恢复点。

## Concrete Steps

工作目录：`/Users/wangyg/Development/Working/subtitle-extractor`

1. 主 agent 启动新线程后，先读 `PLANS.md`、`AGENTS.md`、`README.md`，再决定子 agent 写入边界。
   期望：新线程无需回看旧聊天，也能知道当前基线、冻结点和分工。

2. 测试子 agent 运行：

       uv run --python 3.12 python -m unittest discover -s tests -v

   期望：当前 32 个测试全部通过。

3. 评估子 agent 先复现 Paddle 基线：

       uv run --python 3.12 subx samples/zh_single_dark/clip.mp4 --engine paddle --lang zh --workers 1 --sample-every 6 --output /tmp/subx-zh-paddle.srt

   期望：命令成功结束，终端打印 JSON stats，`elapsed_seconds` 约 97 秒量级，输出文件存在。

4. 评估子 agent 将 ONNX 问题缩小为最小复现，建议从 backend 级命令开始，而不是直接再跑完整流水线。当前已知 `.venv` 内对单张裁剪图调用 `OnnxBackend.recognize(...)` 能返回，且 `workers=2` 的真实 CLI 只带来有限收益；下一轮优先判断是否有必要继续试 `resize_max_width`、ROI 压缩或更小范围样本，而不是盲目扩大到全量 `all` 评估。
   期望：能明确区分主要成本在“单帧 ONNX 推理吞吐 / RapidOCR 后处理 / 多进程调度与回收”中的哪一类，并给出是否值得继续大规模对比的证据。

5. 文档子 agent 每完成一个里程碑，都要同步：

       README.md
       AGENTS.md
       PLANS.md

   期望：文档中的命令、当前状态、默认路线、已知阻塞保持一致。

补充协作约束：

- 主 agent 可以改任何文件，但应尽量避免和子 agent 写入重叠。
- 评估子 agent 只提交评估证据、复现步骤、结论建议，不直接拍板默认 backend。
- 实现子 agent、测试子 agent、文档子 agent 不应直接修改 `PLANS.md` 的决策性章节；如需更新，由主 agent 合并。

6. 在 ONNX 可运行之后，评估子 agent 再执行：

       uv run --python 3.12 subx-dev eval ./samples --engine all --json ./eval.json --report ./eval.md

   前置条件：只有在 ONNX 吞吐进入可接受区间，且至少在受控样本上不再明显劣于 Paddle 后再执行；当前不满足。
   期望：同时产出 Markdown 报告和 JSON 报告，并能看见各样本的 CER / WER / cue 指标 / elapsed_seconds。

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
