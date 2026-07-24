# 真实 OCR 替换 Mock 改造方案

设计日期：2026-07-23。

## 1. 目标与边界

本方案把 `demo/terminal_ocr_demo` 提供的 PaddleOCR 识别流程接入 DDOCR
后端，替换当前 `MockOcrService.create_job()` 中固定生成的三条结果。

约束如下：

- 保持现有 REST API 的路径、HTTP 方法、请求字段和响应字段不变。
- 保持现有 Vue 页面、OCR 结果类型和 Konva 展示逻辑不变。
- 保持现有数据库表和字段不变，不新增 Alembic 迁移。
- 结果继续使用项目约定的 `bbox: [x1, y1, x2, y2]`、`text: string`、
  `score/confidence: float`。
- 第一阶段只支持已经能够由 Pillow 解码的单页图片；PDF 页面渲染不属于本次
  “替换 Mock”范围。
- 第一阶段使用整张图片作为一个自动 ROI，不新增前端 ROI 绘制和 REST 字段。
- 不把 Streamlit `app.py` 接入业务服务；仅复用 `terminal_ocr_demo` 核心包。

### 1.1 “前端完全不变”的硬限制

当前 `src/api/client.ts` 将所有请求超时固定为 10 秒；`WorkspaceView.vue` 在
`POST /ocr/jobs` 返回后立即跳转并读取 pages/results，没有轮询 queued/running
任务。Demo 文档记录单方向识别约 15.82 秒，默认四方向通常更久。

因此，在前端完全不变的前提下，只能让 `POST /ocr/jobs` 阻塞等待 OCR 完成再返回，
但它很可能触发前端 10 秒超时。后台异步立即返回虽然符合 `202` 语义，却会让现有
页面过早读取空结果，并错误显示“识别完成”。

本方案区分两个执行模式：

1. **兼容模式（本次约束可实施）**：路由和页面不变，创建任务后由 worker 执行，
   请求线程等待 worker 结束再返回。仅当端到端耗时稳定小于 10 秒时可验收。
2. **正式模式（推荐后续实施）**：`POST /ocr/jobs` 立即返回 queued，前端利用现有
   `GET /ocr/jobs/{id}` 轮询直到终态。REST API 不变，但需要修改前端调用时序。

如果真实性能无法压到 10 秒内，则“真实 OCR”和“前端代码零修改”不能同时满足，
必须由产品/技术负责人解除其中一个约束。本文不会假定该矛盾不存在。

## 2. 当前 Mock 数据位置

### 2.1 直接生成固定识别结果

`backend/app/services/core.py` 是 Mock 数据的唯一直接生成位置：

- `MockOcrService.create_job()`：
  - 只接受 `model_id == "mock"`、`model_version == "1.0.0"`。
  - 固定构造 `XT-101`、`QF10I`、`24V DC` 三条结果。
  - 任务创建时直接标记为 `succeeded/completed/100`。
  - 同步创建一个 page，并调用 `_create_mock_results()`。
- `MockOcrService._create_mock_results()`：
  - 将固定 `bbox` 转成矩形 polygon。
  - 为结果生成 UUID。
  - 逐条调用 `OCRResultRepository.create()` 写入 `results` 表。
- `MockOcrService._build_page()`：
  - 创建固定单页结构。
  - 把 page 直接标记为 `succeeded`，`processing_ms` 固定为 20。

### 2.2 Mock 模型目录

`backend/app/api/routes.py` 的 `GET /models` 固定返回：

```text
mock / 1.0.0 / Mock OCR
```

为了保持 Vue 页面不变，第一阶段建议保留 `id=mock` 和 `version=1.0.0`，只把名称、
说明和预计耗时改为真实模型信息。这样前端现有默认模型 ID 和提交参数无需变化。
模型 ID 的语义会暂时与实现不一致，但这是零前端改动的兼容代价。

### 2.3 仅用于开发展示的前端 Mock

`src/mock.ts`、`src/mock/tasks.ts` 仍包含无 taskId 时的演示数据，但它们不参与
`POST /ocr/jobs` 的后端固定结果生成。本次接入不修改这些文件。

## 3. 当前完整调用链

### 3.1 上传与文件就绪

1. `WorkspaceView.vue::runOcr()` 调用
   `src/api/ocr.ts::uploadAndCreateOcrTask()`。
2. `POST /files/upload-sessions` 进入
   `routes.create_upload()` → `MockOcrService.create_upload()` →
   `FileRepository.create()`，在 `files` 表建立 uploading 记录。
3. `PUT /files/{file_id}/content` 进入
   `routes.upload_content()` → `MockOcrService.save_content()`，把字节写入
   `DDOCR_DATA_DIR/uploads/{file_id}`，并把文件更新为 validating。
4. `POST /files/{file_id}/complete` 进入
   `routes.complete()` → `MockOcrService.complete()`，Pillow 读取图片尺寸，
   `FileRepository.update()` 把文件更新为 ready。

### 3.2 当前任务创建与结果写入

1. 前端调用 `POST /ocr/jobs`，请求体包含 name、file_id、model_id、model_version、
   options。
2. `routes.create_job()` 完成登录和 owner 校验，调用
   `MockOcrService.create_job()`。
3. service 校验文件 ready 和固定 mock 模型版本。
4. service 在内存中生成 job/page/result UUID 及固定结果。
5. `OCRJobRepository.create()` 写入 `ocr_jobs`。
6. `PageRepository.create()` 写入 `pages`。
7. `_create_mock_results()` 逐条调用 `OCRResultRepository.create()` 写入 `results`。
8. service 返回 `{id,status,stage,progress,created_at}`，路由保持 HTTP 202。

当前没有独立 task worker，也没有真实的状态更新：任务从未以 queued/running 状态
持久化，创建时即为 succeeded。

### 3.3 当前读取与前端映射

1. 创建成功后前端跳转 `/workspace/{taskId}`。
2. `WorkspaceView.vue` 同时调用 `getTask()` 和 `getOcrPages()`。
3. `GET /ocr/jobs/{id}` 读取 `OCRJobRepository.get()`。
4. `GET /ocr/jobs/{id}/pages` 读取 page，并为图片补上受保护的文件 URL。
5. `GET /ocr/jobs/{id}/pages/{page_no}/results` 按 page.result_ids 读取结果，
   再由 `public_result()` 拼入 correction、display_text 和 comments。
6. `src/api/ocr.ts::mapApiResult()` 将后端的 `confidence` 映射成前端 `score`，
   `bbox` 原样用于 Konva。

真实 OCR 接入后，第 3.3 节的接口、响应和前端映射全部保持不变。

## 4. 目标后端调用链

兼容模式下的目标链路如下：

```text
POST /ocr/jobs
  -> OcrService.create_job()
  -> 创建 queued job + queued page
  -> OcrTaskWorker.submit_and_wait(job_id)
      -> job: running/loading_model
      -> OcrAdapter.recognize_file(path, page, options)
          -> OcrEngine.recognize(image, rois)
              -> terminal_ocr_demo.run_pipeline(...)
          -> polygon_to_bbox(...)
          -> AdapterResult[]
      -> ResultWriteRepository.replace_page_results(...)
      -> page: succeeded 或 failed
      -> job: succeeded / partial_success / failed
  -> 返回既有五字段 job 响应
```

正式异步模式仅把 `submit_and_wait()` 换成 `submit()`；其他层不变。

## 5. 建议新增文件

### 5.1 `backend/app/ocr/__init__.py`

OCR 集成包入口。只导出稳定的后端接口类型，避免 service 直接依赖 demo 的所有
内部类。

### 5.2 `backend/app/ocr/contracts.py`

定义后端内部契约，不对外改变 REST：

- `OcrRegion(roi_id, bbox)`：原图像素 ROI。
- `AdapterDetection(text, confidence, polygon, bbox, roi_id, review_required,
  attributes)`。
- `AdapterPageResult(detections, roi_errors, processing_ms)`。
- `OcrAdapterProtocol`：便于测试时注入 fake adapter。

内部 DTO 与 demo DTO 隔离，后续模型升级不污染 service 和 repository。

### 5.3 `backend/app/ocr/geometry.py`

负责项目侧的坐标适配：

- `full_image_roi(width, height)`：第一阶段生成
  `[0, 0, width, height]` 整图 ROI。
- `normalize_roi_bbox()`：统一方向、裁剪到图片边界并拒绝零面积框；供后续
  `options.rois` 扩展复用。
- `polygon_to_bbox(polygon, width, height)`：从任意有效点集计算
  `[min_x, min_y, max_x, max_y]`，裁剪到原图边界。
- 拒绝 NaN、Infinity、少于两个有效点和退化框。

输出 bbox 使用 float，以符合现有数据库 Float 字段；不把 polygon 简化为整数，
避免缩放/旋转逆变换造成精度损失。

### 5.4 `backend/app/ocr/engine.py`（OcrEngine）

管理 PaddleOCR 引擎生命周期和并发：

- 应用启动后首次使用时延迟初始化 `PaddleOCREngine`。
- 初始化前调用 `configure_paddlex_cache()`。
- 持有单实例互斥锁，因为 demo 明确不保证同一 engine 并发调用安全。
- 封装 `run_pipeline()`，不让 service 直接导入 demo pipeline。
- 支持构造函数注入 fake engine，普通单元测试不加载 Paddle、不下载模型。
- 把模型初始化错误与推理错误转换为内部异常类型。

建议类名为 `TerminalOcrEngine`，避免与 Paddle 类同名。这里所说的 OcrEngine 是
DDOCR 的模型执行封装，而不是 REST service。

### 5.5 `backend/app/ocr/adapter.py`（OcrAdapter）

这是 demo 输出到 DDOCR 数据结构的防腐层：

1. 用 Pillow 读取上传文件并强制 RGB。
2. 第一阶段调用 `full_image_roi()`；不读取前端 ROI。
3. 调用 `TerminalOcrEngine.run()`。
4. 对每条 demo detection：
   - `text` 使用 `output_text`；未解决结果保留空字符串。
   - `confidence is None` 时写 `0.0`，并记录
     `attributes.confidence_missing=true`。
   - confidence 裁剪到 `[0, 1]`，原始异常值放入 attributes。
   - polygon 保留原图四点或多点坐标。
   - 调用 `polygon_to_bbox()` 产生项目 bbox。
   - `review_required = is_unresolved or text == ""`。
5. 保留 roi_id、rotation、scale、cluster_id、规则状态和候选代码等审计信息到
   `attributes`。当前 repository 尚未写 attributes，需同步增强。
6. 丢弃无法生成有效 bbox 的候选，并在页级错误/统计中留痕。

`detection_id=det_0001` 只在 demo 单次调用内有效，不能作为数据库 ID；service 或
worker 必须继续使用 `uid()` 生成持久化结果 ID。

### 5.6 `backend/app/workers/ocr_task.py`（task worker）

负责任务编排，不负责 OCR 算法：

- `run(job_id)`：读取 job/file/page，执行状态迁移，调用 adapter，写结果和终态。
- `submit_and_wait(job_id)`：兼容当前零前端改动模式。
- 后续可增加 `submit(job_id)`，对接线程池、进程池或外部队列。
- 捕获可预期异常并写 `error_code/error_message`，不得让任务永久停在 running。
- 记录 started_at、finished_at、processing_ms、result_count、review_count。
- 在同一进程内限制并发；CPU OCR 推荐独立进程 worker，每个进程独占一个 engine。

线程池只适用于过渡阶段。生产部署不应依赖 FastAPI `BackgroundTasks` 保存关键任务，
因为进程重启会丢失内存中的待执行任务。

### 5.7 `backend/app/ocr/errors.py`

定义稳定的内部错误码，例如：

- `OCR_UNSUPPORTED_MEDIA_TYPE`
- `OCR_IMAGE_DECODE_FAILED`
- `OCR_MODEL_LOAD_FAILED`
- `OCR_INFERENCE_FAILED`
- `OCR_INVALID_GEOMETRY`
- `OCR_LIBRARY_MISSING`

这些错误写入现有 `ocr_jobs.error_code/error_message` 和 `pages.error` 字段，不新增表。

### 5.8 核心模型代码位置

建议把 `demo/terminal_ocr_demo` 复制为
`backend/app/vendor/terminal_ocr_demo/`，作为版本化 vendor 包；不要让生产代码通过
`sys.path` 引用仓库根目录的 demo。只复制核心 `.py` 和编号库，不复制 Streamlit、
研发脚本、样图、output 历史文件或 `__pycache__`。

编号库建议放到：

```text
backend/app/vendor/terminal_ocr_demo/resources/terminal_id_library.csv
```

并由 DDOCR 配置传入绝对路径，修复 demo 当前 `output`/`outputs` 不一致问题。

## 6. 需要修改的文件

### 6.1 `backend/app/services/core.py`

建议将 `MockOcrService` 重命名为 `OcrService`，并临时保留别名以降低测试改动；其余
认证、文件、纠错、评论和导出职责不动。

`create_job()` 改为：

1. 保持文件归属和 ready 校验。
2. 继续接受前端当前提交的 `mock@1.0.0` 兼容标识。
3. 生成 job/page UUID。
4. 创建 `queued` job 和 `queued` page，result_ids 初始为空。
5. 调用 worker 的兼容模式入口并等待完成。
6. 重新读取 job，返回原有五个响应字段。

删除或停止调用：

- 固定 `mock_results`。
- `_create_mock_results()`。
- 固定成功版 `_build_page()`；改为构建 queued page，最终状态由 worker 更新。

service 构造函数新增 `ocr_adapter`、`ocr_worker` 可注入参数，使测试不依赖真实模型。

### 6.2 `backend/app/repositories/file_job.py`

`OCRJobRepository` 当前只有 create/get/all，必须增加：

- `update_state(job_id, *, status, stage, progress, started_at, finished_at,
  completed_pages, failed_pages, result_count, review_count, error_code,
  error_message)`。
- 可选 `claim(job_id)`：条件更新 `queued → running`，避免任务被重复执行。

同时调整 `_job_dict()`，在内部需要时带出已有 error 字段；公开 REST 是否返回这些字段
遵循当前接口契约，不能擅自新增必需字段。

所有状态更新必须使用 repository，而不是修改从数据库读取出的 dict 后假定自动持久化。

### 6.3 `backend/app/repositories/page_result.py`

`PageRepository` 增加：

- `update_state()`：更新 status、result_ids、result_count、review_count、
  processing_ms 和 error。

`OCRResultRepository` 增加：

- `create_many(items)`：一个事务批量写入一页结果。
- 或更推荐 `replace_page_results(page_id, items)`：在一个事务内保证结果集合和
  page.result_ids 一致。第一版任务只执行一次时可先使用 create_many。

修改现有 `create()`/新增批量写入，使其写入 schema 已存在但当前被忽略的：

- `attributes`
- `angle`（能可靠确定时）

数据库结构不变；这些列已经存在。

### 6.4 `backend/app/main.py`

- 应用启动时组装 `TerminalOcrEngine`、`OcrAdapter` 和 `OcrTaskWorker`，注入 service。
- 标题和描述从 Mock Backend 改为真实 OCR Backend。
- 在应用 shutdown 时关闭 worker/executor。
- `create_app()` 增加可选 adapter/worker factory 注入点，确保测试使用 fake。
- 必须在导入 PaddleOCR 之前配置 PaddleX 缓存目录。

不要在模块 import 阶段立即加载真实模型，否则测试收集、Alembic 和普通管理命令都会
触发重型初始化甚至联网下载。

### 6.5 `backend/app/api/routes.py`

REST 路径和响应结构保持不变，只做以下内部调整：

- service 类型从 `MockOcrService` 改为 `OcrService`。
- `GET /models` 仍返回兼容 ID `mock@1.0.0`，但名称、note、预计耗时改为真实模型。
- `POST /ocr/jobs` 仍返回 HTTP 202 和原有 data 字段。

正式异步模式启用前，不改变路由行为。启用后该路由只创建并提交任务，不等待完成，
但届时必须同步解决前端轮询问题。

### 6.6 `backend/requirements.txt`

加入经过当前 Python 3.11 环境验证的真实推理依赖。不能直接照抄 demo 全部依赖：

- 生产必需：PaddlePaddle、PaddleOCR/PaddleX、兼容版本的 NumPy、OpenCV、Pillow。
- 不应加入：Streamlit、drawable-canvas、仅研发报告使用的依赖。

当前后端固定 `Pillow==11.2.1`，demo 固定 `Pillow==10.4.0`；需要在隔离环境完成依赖
求解和真实推理验证后再决定版本，不能在设计阶段武断覆盖。

### 6.7 配置文件

建议新增 `backend/app/ocr/settings.py` 或扩展环境配置，读取：

```text
DDOCR_OCR_DEVICE=cpu
DDOCR_OCR_MODEL_CACHE=<ASCII 可写路径>
DDOCR_OCR_CODE_LIBRARY=<绝对路径>
DDOCR_OCR_SCALE=2.0
DDOCR_OCR_ROTATIONS=0,90,180,270
DDOCR_OCR_MAX_CONCURRENCY=1
DDOCR_OCR_EXECUTION_MODE=blocking
```

默认值不能依赖当前工作目录。

### 6.8 测试文件

修改现有断言固定三条 Mock 数据的测试：

- `backend/tests/test_api.py`
- `backend/tests/test_page_result_relational.py`
- `backend/tests/test_file_job_relational.py`

这些测试应注入 deterministic fake adapter，不调用 PaddleOCR。认证、owner 隔离、纠错、
评论和导出断言继续复用 fake 产生的持久化结果。

## 7. 新增测试清单

- `backend/tests/test_ocr_geometry.py`
  - polygon 转 bbox。
  - 负数/越界坐标裁剪。
  - 浮点精度。
  - NaN、Infinity、空 polygon、退化框拒绝。
  - 整图 ROI。
- `backend/tests/test_ocr_adapter.py`
  - demo 五字段到 DDOCR 字段映射。
  - `confidence=None → 0.0` 并留审计标志。
  - 空 text 保留且计入 review。
  - detection_id 不作为数据库 ID。
  - 无效 polygon 被隔离。
- `backend/tests/test_ocr_engine.py`
  - 模型延迟加载一次。
  - 同实例调用被串行化。
  - fake engine 不触发 Paddle import/download。
  - pipeline roi_errors 透传。
- `backend/tests/test_ocr_worker.py`
  - queued → running → succeeded。
  - 部分 ROI 失败 → partial_success。
  - 解码/加载/推理失败 → failed，错误被持久化。
  - 结果、page 和 job 计数一致。
  - 重复 claim 不会执行两次。
- `backend/tests/test_real_ocr_api_contract.py`
  - 原有上传与任务 API 的请求/响应字段不变。
  - pages/results 响应仍包含原有字段。
  - bbox 为四元组且 confidence 在 `[0,1]`。
  - 真实结果仍可纠错、评论和导出。
- `backend/tests/integration/test_paddleocr_smoke.py`
  - 使用一张脱敏小样图做真实模型 smoke test。
  - 通过环境标志显式启用，普通 CI 默认跳过。
  - 模型必须预缓存，测试不得隐式联网。

## 8. 状态机与失败语义

不新增数据库字段，使用现有列：

| 阶段 | job.status | job.stage | progress | page.status |
|---|---|---|---:|---|
| 已创建 | queued | queued | 0 | queued |
| 读取图片 | running | decoding | 10 | running |
| 加载模型 | running | loading_model | 20 | running |
| OCR 推理 | running | recognizing | 30～80 | running |
| 结果适配/写入 | running | persisting | 90 | running |
| 全部成功 | succeeded | completed | 100 | succeeded |
| 局部成功 | partial_success | completed | 100 | partial_success |
| 全局失败 | failed | failed | 100 | failed |

`review_count` 定义为 `is_unresolved`、空 text 或业务规则要求人工复核的结果数。
不要继续使用当前固定值 1。

失败时遵循：

- 全局失败不写半页结果，page 和 job 都进入 failed。
- demo 的单 ROI 错误若仍有有效结果，写入成功结果并标记 partial_success。
- 结果批量写入、page 汇总更新应尽量处于同一事务。
- job 终态更新可以是后续独立事务，但必须有兜底异常处理。

## 9. 数据映射规则

| Demo 字段 | DDOCR 字段 | 规则 |
|---|---|---|
| `detection_id` | 不持久化为 ID | 数据库 ID 使用 `uid()` |
| `roi_id` | `results.attributes.roi_id` | 保留审计关联 |
| `text` | `results.text` | 允许空字符串，不能丢弃未解决框 |
| `confidence` | `results.confidence` | None 规范为 0.0；限制到 0～1 |
| `polygon` | `results.polygon` | 保留原图像素浮点坐标 |
| `polygon` | `results.bbox` | 计算 min/max 四元组 |
| `rotation` | `results.angle` 或 attributes | 使用模型候选的旋转角 |
| assessment/audit | `results.attributes` | 使用现有 JSON 列，不改 schema |

前端仍通过 `mapApiResult()` 得到：

```text
id         <- results.id
text       <- results.text
score      <- results.confidence
bbox       <- results.bbox
revision   <- results.current_revision
corrected  <- display_text（存在纠正时）
comments   <- comments 关系表
```

## 10. 修改与新增文件总表

### 10.1 新增文件

| 文件 | 职责 | 对应前端接口 |
|---|---|---|
| `backend/app/ocr/__init__.py` | OCR 包稳定出口 | 间接服务全部 OCR API |
| `backend/app/ocr/contracts.py` | 内部 DTO/Protocol | `POST /ocr/jobs`、results GET |
| `backend/app/ocr/geometry.py` | 整图 ROI、ROI 校验、polygon→bbox | results GET 的 bbox |
| `backend/app/ocr/engine.py` | 模型生命周期、锁和 pipeline 调用 | `POST /ocr/jobs` |
| `backend/app/ocr/adapter.py` | Demo→DDOCR 结果防腐层 | jobs/pages/results |
| `backend/app/ocr/errors.py` | 内部错误分类 | job/pages 状态查询 |
| `backend/app/ocr/settings.py` | 模型与运行参数配置 | `GET /models` 间接展示 |
| `backend/app/workers/__init__.py` | worker 包入口 | 无直接前端调用 |
| `backend/app/workers/ocr_task.py` | 状态编排、推理、持久化 | `POST/GET /ocr/jobs*` |
| `backend/app/vendor/terminal_ocr_demo/*` | 经验证的模型核心代码 | 仅后端内部 |
| `backend/app/vendor/terminal_ocr_demo/resources/terminal_id_library.csv` | 合法编号库 | 影响 results text/review |
| `backend/tests/test_ocr_geometry.py` | 坐标适配测试 | results bbox 契约 |
| `backend/tests/test_ocr_adapter.py` | 输出映射测试 | results 字段契约 |
| `backend/tests/test_ocr_engine.py` | 引擎生命周期测试 | job 创建稳定性 |
| `backend/tests/test_ocr_worker.py` | 状态和持久化测试 | jobs/pages/results |
| `backend/tests/test_real_ocr_api_contract.py` | REST 回归测试 | 当前 Vue 使用的全部 OCR API |
| `backend/tests/integration/test_paddleocr_smoke.py` | 可选真实模型冒烟 | `POST /ocr/jobs` |

### 10.2 修改文件

| 文件 | 修改职责 | 对应前端接口 |
|---|---|---|
| `backend/app/services/core.py` | 删除固定结果，创建 queued 任务并调用 worker | `POST /ocr/jobs` 及下游查询 |
| `backend/app/repositories/file_job.py` | job 状态、计数、错误更新与 claim | `GET /ocr/jobs`、`GET /ocr/jobs/{id}` |
| `backend/app/repositories/page_result.py` | page 更新、结果批量写入、attributes | pages/results GET、纠错、评论、导出 |
| `backend/app/main.py` | 组装 adapter/engine/worker 和生命周期 | 所有 OCR API |
| `backend/app/api/routes.py` | 替换 service 类型、模型展示信息 | `GET /models`、`POST /ocr/jobs` |
| `backend/requirements.txt` | 增加经验证的推理依赖 | 后端运行环境 |
| `backend/tests/test_api.py` | fake adapter 替代固定三结果假设 | 全流程 API |
| `backend/tests/test_page_result_relational.py` | 验证真实适配结果写关系表 | pages/results GET |
| `backend/tests/test_file_job_relational.py` | 验证任务状态仍写关系表 | jobs API |
| `backend/README.md` | 环境、模型缓存、启动和测试 | 部署说明 |
| `docs/03_Backend.md` | adapter、worker、状态机 | 后端设计说明 |
| `docs/04_API.md` | 明确现有接口的真实执行语义 | 前端 REST 契约 |
| `docs/05_Deploy.md` | Paddle、模型预下载、worker 部署 | 部署运维 |
| `docs/06_Frontend_Backend_Integration.md` | 记录兼容模式限制 | Vue/FastAPI 联调 |

本阶段不修改 `src/` 下任何 Vue/TypeScript 文件，也不修改数据库 schema 或迁移文件。

## 11. 事务与并发建议

当前 repositories 每个方法自行打开事务。为了避免“结果已写但 page.result_ids 未更新”，
批量持久化应新增一个明确的事务边界。可采用两种方式：

1. 在 `PageResultRepository` 中增加组合方法，在同一 SQLAlchemy Session 内批量插入
   results 并更新 page；推荐。
2. 增加 Unit of Work，把 Session 从 worker 传给 repositories；更完整，但改造范围较大。

第一阶段选择方案 1，不改现有 correction/comment repository。

同一 job 必须通过条件更新 claim；同一个 `TerminalOcrEngine` 必须加锁。多进程部署时，
进程内锁不能防止跨进程并发，应以每 worker 进程一个 engine、数据库 claim 控制任务
归属。

## 12. 实施顺序

1. 冻结并清理 vendor 模型核心，修复编号库绝对路径。
2. 实现 contracts、geometry 及其单元测试。
3. 实现 adapter，使用 fake demo engine 完成映射测试。
4. 扩展 job/page/result repositories 和事务测试。
5. 实现 worker 状态机和失败恢复测试。
6. 修改 service，删除固定结果并注入 fake adapter，使所有现有 API 测试先通过。
7. 在 main 中接入延迟加载的真实 engine。
8. 在隔离环境安装真实依赖，预下载模型并执行显式 smoke test。
9. 测量上传完成到 `POST /ocr/jobs` 返回的 P50/P95；验证是否低于前端 10 秒。
10. 若无法满足 10 秒，停止“前端零修改”上线，转入正式异步模式并单独设计前端轮询。

## 13. 验收标准

- 现有 REST 路径、方法、请求体和响应字段无破坏性变化。
- `src/` 无修改，现有 Vue 页面能展示数据库中的真实 OCR bbox 和文字。
- schema 和 Alembic migration 无修改。
- 固定 `XT-101/QF10I/24V DC` 生成逻辑已移除。
- 普通测试使用 fake adapter，离线且不加载 Paddle。
- 显式集成测试能够用预缓存模型识别脱敏样图。
- job/page/result 的状态与计数一致，失败任务不会停在 running。
- polygon 和 bbox 均为原图像素坐标，bbox 满足 `[x1,y1,x2,y2]`。
- 空文字结果仍被持久化并计入 review_count。
- 真实结果继续支持现有纠错、评论和导出。
- 兼容模式端到端耗时必须稳定低于前端 10 秒；否则该模式验收失败，必须启用前端轮询。

## 14. 明确不在本次范围内

- Vue/Konva 人工 ROI 绘制。
- 新增或修改 REST API。
- PDF 逐页渲染与多页任务。
- 修改数据库结构。
- 训练或微调 PaddleOCR 模型。
- 修改端子编号正则和合法库业务口径。
- Streamlit 页面接入生产系统。
- 生产级分布式队列选型与部署；本方案只为其保留 worker 边界。
