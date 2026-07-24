# 真实 OCR API 端到端验收报告

验收日期：2026-07-23。

## 1. 验收结论

真实 OCR API 的后端链路已经完整跑通。本报告中的 151.23 秒数据来自异步 Worker
落地前的同步基线；当前 `POST /ocr/jobs` 已立即返回 HTTP 202，由后台 Worker
继续完成同一套真实推理与持久化流程：

```text
注册并登录
  → 创建 Upload Session
  → 上传 PNG 文件
  → Complete
  → POST /ocr/jobs
  → OcrTaskWorker
  → TerminalOcrEngine / PP-OCRv5 CPU 推理
  → OcrAdapter 数据转换
  → ocr_jobs / pages / results 关系表
  → GET Job / Pages / Results
```

真实集成测试结果：

```text
backend/tests/integration/test_real_ocr_api.py
1 passed, 2 warnings in 151.23s
```

测试使用已缓存的 `PP-OCRv5_mobile_det` 和 `PP-OCRv5_mobile_rec`，不是 Fake
Engine，也没有 Mock OCR 结果注入。两条 warning 分别是 PaddleOCR 模型名使 `lang`
参数被忽略，以及本机未安装 ccache；均不影响 CPU 推理结果。

## 2. 实际测试输入

测试从项目样图 `samples/电缆端子2.png` 裁剪模型提供方已验证的区域：

```text
[540, 180, 1100, 1180]
```

裁剪后的上传图片尺寸为 560×1000。为控制同步验收时间，测试明确使用：

```text
scale=2.0
rotations=(0,)
device=cpu
```

生产默认配置仍为四方向旋转，本次测试没有修改生产默认值。

## 3. HTTP 链路验收结果

| 步骤 | 接口 | 预期 | 结果 |
|---|---|---:|---|
| 注册验收用户 | `POST /api/v1/auth/register` | 201 | 通过 |
| 创建上传会话 | `POST /api/v1/files/upload-sessions` | 201 | 通过 |
| 上传文件内容 | `PUT /api/v1/files/{id}/content` | 200 | 通过 |
| 完成上传 | `POST /api/v1/files/{id}/complete` | 200/ready | 通过 |
| 创建 OCR 任务 | `POST /api/v1/ocr/jobs` | 202 | 通过 |
| 查询任务 | `GET /api/v1/ocr/jobs/{id}` | 200/succeeded | 通过 |
| 查询页面 | `GET /api/v1/ocr/jobs/{id}/pages` | 200/succeeded | 通过 |
| 查询结果 | `GET /api/v1/ocr/jobs/{id}/pages/1/results` | 200 | 通过 |

任务最终状态验证：

- `status == "succeeded"`
- `stage == "completed"`
- `progress == 100`
- `completed_pages == 1`
- `failed_pages == 0`
- `result_count > 0`

页面最终状态验证：

- `status == "succeeded"`
- `page_no == 1`
- `result_count > 0`
- 页面结果数、任务结果数和 Results API 数量一致

## 4. OCR 结果契约验收

每条真实 OCR 结果均验证：

- `text is not None`
- `confidence ∈ [0, 1]`
- `bbox` 是四元素数组
- `bbox` 满足 `0 ≤ x1 < x2 ≤ width`
- `bbox` 满足 `0 ≤ y1 < y2 ≤ height`
- `polygon` 至少包含两个合法二维点
- polygon 坐标处于原图范围内
- `revision == 0`
- `comments == []`
- `display_text == text`
- `is_corrected == false`

## 5. 数据库验收

测试使用独立临时 SQLite 数据库，并直接查询 SQLAlchemy 表。验证结果：

- `ocr_jobs`：恰好写入 1 条本次任务，状态 succeeded，result_count 正确。
- `pages`：恰好写入 1 条本次页面，状态 succeeded，result_count 正确。
- `results`：写入数量大于 0，且与 Job、Page、Results API 数量完全一致。
- 每条数据库结果 `current_revision == 0`。
- 每条数据库结果 confidence 均在 `[0, 1]`。

本次验收没有修改数据库结构或 Alembic migration。

## 6. 当前 Vue 所需字段

测试逐条验证 `src/api/ocr.ts::mapApiResult()` 使用的字段全部存在：

```text
id
text
confidence
bbox
display_text
is_corrected
comments
revision
```

因此，真实结果查询响应已经能够被当前 `mapApiResult()` 映射，Konva 所需 bbox 与结果
列表所需文字、置信度、revision 和 comments 均满足现有格式，不需要修改 Vue DTO。

## 7. 已经真正跑通的能力

- 图片上传及归属验证。
- 图片尺寸解析与受保护原图访问记录。
- 进程内 Worker 异步调用真实 `TerminalOcrEngine`。
- PaddleOCR detection 和 recognition CPU 推理。
- ROI 预处理、坐标映射、编号规则及空间后处理。
- Demo DTO 到 DDOCR DTO 的转换。
- polygon 到 bbox 转换。
- 真实 OCR 结果写入关系表。
- Job、Page、Result REST 查询。
- 前端结果字段兼容。

## 8. 仍然保留的兼容命名或尚未验收的部分

- API 模型标识和 Service 类名仍保留早期 Mock 命名，但 OCR 数据源已经是真实 Engine。
- 已有进程内单线程 Worker 和异步状态更新；任务恢复、自动重试和取消执行尚未实现。
- Repository 当前没有持久化 Adapter 提供的完整 `attributes` 审计数据。
- 本次使用 SQLite 验收；生产 PostgreSQL 的真实 OCR 写入尚未单独执行验收。
- 本次只验收 PNG 单页图片；PDF 渲染和多页任务没有实现。
- 本次只验证结果存在与结构合法，没有进行识别准确率、召回率或业务真值验收。
- correction/comment/export 在既有测试中有覆盖，但本次真实 OCR 用例没有重复验证这些
  下游操作。

## 9. 可以交给前端联调的范围

现在可以开始联调：

- 已完成任务的 Job 详情查询。
- Pages 查询和原图展示。
- Results 查询。
- 真实文字、confidence 和 bbox 的 Vue 映射。
- Konva 真实结果框展示。
- 基于真实结果 ID 的现有纠错和评论功能。

前端异步闭环现已完成：创建任务后立即进入 Workspace，每 1 秒轮询 Job；识别期间不读取
Results，`succeeded/partial_success` 后再加载 Pages/Results；失败或取消时停止轮询并
展示错误。因此 10 秒 Axios 超时不再限制真实 OCR 的后台推理时长。

## 10. 当前仍未实施事项

- Worker、异步状态机和 Vue 轮询已经落地。
- 未实现跨进程队列、进程重启恢复、自动重试和真正的取消执行。
- 未修改 REST API。
- 未修改 Repository。
- 未修改数据库 schema。
