# 公共 API 契约

本文件是公共 API 的唯一详细定义。通用硬规则见 [RULES.md](RULES.md)。

## 1. 状态与错误

任务执行状态：`queued | running | succeeded | partial_success | failed | cancelled`。

任务阶段：`queued | validating | rendering | preprocessing | detecting | recognizing | persisting | finalizing`。

审核状态：`not_required | needs_review | in_review | reviewed`。执行失败和需要复核不得混用。

文件状态：`uploading | validating | ready | rejected | deleted`。页面状态：`pending | running | succeeded | failed | skipped`。导出状态：`queued | running | succeeded | failed | expired`。

HTTP 错误：400 参数错误、401 未登录、403 无权限、404 不存在、409 幂等/修订冲突、413 文件过大、422 文件或参数不可处理、429 限流/配额、500/502/503 服务或推理异常。

除注册、登录、健康检查和模型目录外，当前 Mock Backend 的文件、OCR、结果、
纠正、留言和导出接口均要求 `Authorization: Bearer <access_token>`。资源按
`owner_id` 隔离，访问其他用户资源返回 404。

```json
{
  "error": {
    "code": "CORRECTION_REVISION_CONFLICT",
    "message": "识别结果已被其他用户修改",
    "details": {"current_revision": 4, "current_display_text": "QF101"}
  },
  "request_id": "req_019..."
}
```

## 2. 用户与偏好

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/register` | 注册本地账号并返回 Bearer 会话 |
| POST | `/api/v1/auth/login` | 使用联系电话和密码登录 |
| GET | `/api/v1/users/me` | 当前用户、角色和权限 |
| PATCH | `/api/v1/users/me` | 更新姓名、部门和联系电话 |
| GET | `/api/v1/users/me/preferences` | 获取跨设备偏好，可选 |
| PATCH | `/api/v1/users/me/preferences` | 部分更新跨设备偏好，可选 |
| POST | `/api/v1/auth/change-password` | 本地身份修改密码；OIDC 模式由身份系统提供 |
| POST | `/api/v1/auth/logout` | 注销会话/刷新令牌 |

用户至少返回：`id, name, employee_no, role_names, permissions, department, email, phone_masked, avatar_url, last_login_at`，可包含 `tenant_id`。

本地密码使用随机盐和 PBKDF2-SHA256 保存，任何响应均不得返回密码摘要。
注册时联系电话必填且唯一，邮箱为可选字段。登录和注册返回
`access_token, token_type, user`；用户资料、修改密码和退出
使用 `Authorization: Bearer <access_token>`。

偏好字段：`preferences_version, default_model_id, low_confidence_threshold, default_result_view_mode, show_confidence, default_export_mode, default_zoom`。服务端允许旧客户端缺少新增字段。

## 3. 模型目录

`GET /api/v1/models?status=available`

每项包含：`id, name, default_version, languages, capabilities, note, estimated_ms_per_page, status, input_limits, default_options`。速度是注明含义的预估指标，不是固定展示字符串。前端创建任务必须提交逻辑 ID 和明确版本。

```json
{
  "data": {"items": [{
    "id": "steel", "name": "钢材铭牌专用", "default_version": "2.0.3",
    "languages": ["zh-CN", "en"],
    "capabilities": ["text_detection", "text_recognition"],
    "note": "低对比度 / 喷码", "estimated_ms_per_page": 52,
    "status": "available",
    "input_limits": {"max_width_px": 10000, "max_height_px": 10000}
  }]},
  "request_id": "req_019..."
}
```

## 4. 文件上传

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/files/upload-sessions` | 创建对象存储直传会话 |
| POST | `/api/v1/files/{file_id}/complete` | 确认上传并触发校验 |
| GET | `/api/v1/files/{file_id}` | 查询状态和元数据 |
| GET | `/api/v1/files/{file_id}/content` | 读取已上传的原始文件内容 |
| DELETE | `/api/v1/files/{file_id}` | 逻辑删除未使用文件 |

创建请求：

```json
{"file_name":"QC_Report_0714.pdf","size_bytes":2516582,"media_type":"application/pdf","sha256":"optional"}
```

创建响应包含 `file_id, upload_url, upload_headers, expires_at, max_size_bytes`。文件详情至少包含原文件名、实际 MIME、大小、kind、页数、状态和失败原因。本地 Mock Backend 额外保存项目内相对路径 `storage_path`；图片保存 `width_px` 和 `height_px`。

## 5. OCR 任务

### 5.1 创建

`POST /api/v1/ocr/jobs`，成功返回 `202 Accepted`。

```json
{
  "name": "轴承套圈质量复核",
  "file_id": "019...",
  "model_id": "steel",
  "model_version": "2.0.3",
  "pages": null,
  "options": {},
  "client_reference": null
}
```

响应包含 `id, status, stage, progress, created_at`。

### 区域 OCR 任务

`POST /api/v1/ocr/region-jobs` 创建独立区域 OCR 任务，成功返回 `202 Accepted`。该接口不修改普通任务创建接口，也不会修改来源任务结果。首期仅支持单页 PNG/JPG 图片，每页最多 20 个区域。

请求必须在 `file_id` 与 `source_job_id` 中二选一。使用 `file_id` 表示从刚上传并完成校验的文件创建；使用 `source_job_id` 表示复用一个 `succeeded` 或 `partial_success` 任务的原文件：

```json
{
  "name": "端子排-区域识别",
  "source_job_id": "019-source-job",
  "model_id": "mock",
  "model_version": "1.0.0",
  "pages": [{"page_no": 1, "regions": [
    {"client_id": "roi-1", "bbox": [320, 180, 980, 760]}
  ]}]
}
```

区域 bbox 使用原图像素坐标 `[x1,y1,x2,y2]`，必须完全位于图片内，宽高均不得小于 16 px。新任务复用原文件但生成独立 Job、Page 和 Result；来源任务状态、识别结果、纠正和留言保持不变。

`GET /api/v1/ocr/region-jobs/{job_id}/context` 返回区域任务来源和创建时固化的范围。任务创建后继续使用现有 `/ocr/jobs/{job_id}`、页面结果、纠正、留言和导出接口。原文件不可用返回 `409 SOURCE_FILE_UNAVAILABLE`；来源任务未完成返回 409；非法页面、模型或 bbox 返回 422。

### 5.2 列表与详情

`GET /api/v1/ocr/jobs` 支持：`query`（任务名/文件名）、`status`（多值）、`sort=created_at|-created_at`、`cursor`、`limit`（默认 20，最大 100）。

任务摘要包含：

```text
id, name, file{id,name,kind,media_type}, created_at,
model{id,name,version}, page_count, completed_pages, failed_pages,
status, stage, review_status, progress, duration_ms,
result_count, review_count, created_by{id,name}, error
```

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/ocr/jobs/{job_id}` | 详情和最新进度 |
| DELETE | `/api/v1/ocr/jobs/{job_id}` | 逻辑删除，204；默认不立即删除原文件 |
| POST | `/api/v1/ocr/jobs/{job_id}/cancel` | 取消排队或运行任务 |
| POST | `/api/v1/ocr/jobs/{job_id}/retry` | 重试失败任务或失败页面 |

详情补充 `total_pages, started_at, finished_at, updated_at/revision, error{code,message}`。

### 5.3 SSE

`GET /api/v1/ocr/jobs/{job_id}/events`

事件：`job.status_changed`、`job.progress`、`page.completed`、`page.failed`、`job.completed`、`job.failed`。

```json
{
  "job_id":"019...", "status":"running", "stage":"recognizing",
  "progress":67, "completed_pages":2, "total_pages":3,
  "updated_at":"2026-07-16T03:31:02Z"
}
```

## 6. 页面与 OCR 结果

### 6.1 页面列表

`GET /api/v1/ocr/jobs/{job_id}/pages`

每页包含 `id, page_no, label, status, image, result_count, review_count, processing_ms, error`。`image` 包含短期 `url, thumbnail_url, width_px, height_px, rotation, render_dpi` 及过期时间。

### 6.2 单页结果

`GET /api/v1/ocr/jobs/{job_id}/pages/{page_no}/results`

默认一次返回完整当前页，结构为：

```json
{
  "data": {
    "job_id": "019...", "page_id": "019...", "page_no": 1,
    "coordinate_system": {"origin":"top_left","unit":"pixel","width_px":2480,"height_px":3508},
    "items": [{
      "id":"019...", "reading_order":1, "type":"text_line",
      "text":"QF10I", "confidence":0.884,
      "bbox":[840,520,1040,590],
      "polygon":[[840,520],[1040,520],[1040,590],[840,590]],
      "display_text":"QF101", "is_corrected":true, "revision":2,
      "current_correction":{
        "id":"019...", "text":"QF101",
        "created_by":{"id":"019...","name":"张三"},
        "created_at":"2026-07-16T03:35:00Z"
      },
      "comment_count":1,
      "comments":[{
        "id":"019...", "content":"字符 I 误识别",
        "author":{"id":"019...","name":"张三"},
        "created_at":"2026-07-16T03:36:00Z", "updated_at":null
      }]
    }]
  },
  "request_id":"req_019..."
}
```

可选扩展字段：`normalized_polygon, angle, attributes`。若单页超过约 5000 项，可提供 gzip/轻量完整框响应，不能用普通分页导致画布漏框。

### 6.3 结果复核状态

`POST /api/v1/ocr/results/review-status` 批量更新结果状态，请求体为
`result_ids` 和 `review_status`。状态支持 `unreviewed | confirmed | false_positive | deleted`。
接口按当前用户校验所有结果归属并在同一事务内更新；重复提交同一状态是幂等的。
`false_positive` 和 `deleted` 都是可恢复的软状态，所有服务端导出必须排除这两类结果。

### 6.4 检测框批量编辑

`POST /api/v1/ocr/jobs/{job_id}/pages/{page_no}/result-edits` 在一个事务中保存已有框坐标更新、人工新建框和软删除。请求包含 `updates[{result_id,bbox,polygon?,base_revision}]`、`creates[{client_id,bbox,polygon?,text}]` 和 `deletes[{result_id}]`。

- 新框文字必填且不触发 OCR，服务端以 `attributes.source=manual` 标记来源。
- bbox 使用原图像素坐标 `[x1,y1,x2,y2]`，必须位于页面内且最小为 4×4 px。
- polygon 为可选的四点原图像素坐标，点序为左上、右上、右下、左下。提供 polygon 时服务端保存真实四点，并根据四点 min/max 重新计算 bbox；不提供时服务端根据 bbox 生成水平四边形，保持旧客户端兼容。
- 坐标更新使用 `geometry_revision` 乐观锁，冲突返回 `409 GEOMETRY_REVISION_CONFLICT`。
- 所有操作写入 `result_geometry_revisions` 审计表；删除沿用 `review_status=deleted`，不会进入导出。

## 7. 人工纠正

以下纠正和留言接口要求 `Authorization: Bearer <access_token>`；创建人/作者
由服务端当前会话生成，客户端不得提交作者字段。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/ocr/results/{result_id}/corrections` | 新增纠正 |
| GET | `/api/v1/ocr/results/{result_id}/corrections` | 查询原文和修订历史 |
| POST | `/api/v1/ocr/results/{result_id}/corrections/{correction_id}/revert` | 新增一条撤销修订 |

新增请求：`{"corrected_text":"QF101","base_revision":2}`，文本上限 500 字符。响应包含 `id, result_id, corrected_text, revision, created_by, created_at`。版本不匹配返回 409 及当前 revision/display_text。相同幂等键不得产生重复修订。

## 8. 留言

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/ocr/results/{result_id}/comments` | 游标分页查询 |
| POST | `/api/v1/ocr/results/{result_id}/comments` | 新增 |
| PATCH | `/api/v1/ocr/results/{result_id}/comments/{comment_id}` | 修改本人留言 |
| DELETE | `/api/v1/ocr/results/{result_id}/comments/{comment_id}` | 逻辑删除本人留言 |

请求仅允许 `{"content":"..."}`，上限 300 字符。author 和时间由服务端生成；新增、修改和删除响应返回最新 `comment_count`。

## 9. 导出

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/ocr/jobs/{job_id}/exports` | 创建后台导出 |
| GET | `/api/v1/ocr/jobs/{job_id}/exports/{export_id}` | 查询状态和短期下载地址 |

创建请求：`{"format":"xlsx","mode":"full","scope":"all_pages"}`。`mode` 支持 `simple | full`。下载地址生成前校验任务权限并明确过期时间。

`mode=simple` 生成“精简结果”工作表，仅包含编号和最终识别结果（优先使用纠正文本）；`mode=full` 保留页码、阅读顺序、原文、最终文本、置信度、BBox 和留言。

## 10. 忘记密码 MVP

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/forgot-password` | 使用联系电话和员工编号申请一次性验证码，统一返回 202 |
| POST | `/api/v1/auth/reset-password` | 使用联系电话、验证码和新密码完成重置，成功返回 204 |

验证码为 6 位数字，有效期 10 分钟，最多允许 5 次错误尝试；再次申请会使旧验证码失效。重置成功后撤销该用户全部已有会话。仅当 `DDOCR_EXPOSE_PASSWORD_RESET_CODE=true` 时，申请响应的 `data` 包含 `development_code` 供本地联调。生产环境必须关闭该配置并接入短信发送服务。
