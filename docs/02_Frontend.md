# 前端架构与后端接入

## 1. 当前结论

现有组件层级、Konva 独立渲染、结果面板和弹窗/抽屉边界可以保留。`WorkspaceView` 继续负责编排，但 HTTP、状态机和缓存应移到 service/composable。

当前需要修正的生产边界：

- 缺少统一 HTTP client、错误模型、鉴权刷新、请求取消和 request_id。
- `OcrItem`、`MockPage`、`ModelOption` 位于 Mock 文件，应迁移到领域类型。
- 全局可变 `pages` 会造成跨任务数据污染。
- Mock 类型适合演示，不得直接作为生产 API 类型。

## 2. 推荐新增结构

```text
src/api/http.ts                 统一请求、鉴权、错误、取消和 request_id
src/api/models.ts               模型目录 API
src/api/files.ts                上传 API
src/api/jobs.ts                 任务与 SSE API
src/api/results.ts              页面与 OCR 结果 API
src/api/review.ts               纠正与留言 API
src/api/users.ts                用户与偏好 API
src/composables/useOcrJob.ts     当前任务状态机和页面加载
src/types/api.ts                通用响应与错误类型
src/types/ocr.ts                页面、结果和坐标类型
```

UI 组件继续通过 props/emits 工作，不在组件内部散落 HTTP 调用。

## 3. 前端状态边界

后端持久化：上传文件、模型版本、任务及进度、标准页图、OCR 原始结果、纠正历史、留言、删除状态、用户权限和后台导出。

前端会话状态：当前结果 ID、当前页、搜索词、低置信度开关、请求加载状态。

本地或可选用户偏好：列表/原位模式、缩放、分割面板宽度、默认模型、低置信度阈值、是否显示置信度和导出类型。

签名 URL、任务事实状态、作者和服务端时间不得保存为客户端事实来源。

## 4. `useOcrJob` 建议接口

```text
job
pages
currentPage
currentPageResults
selectedResultId
isLoading
isSubmittingCorrection
isSubmittingComment
loadJob()
loadPage(pageNo)
createJob()
cancelJob()
retryJob()
```

数据按 `job_id + page_no` 隔离和缓存。路由切换时取消旧页面请求和 SSE。纠正与留言允许乐观更新，但失败必须回滚；409 必须用服务端最新修订覆盖缓存后提示冲突。

## 5. API 到 UI 的兼容映射

| API | 当前 UI | 迁移要求 |
|---|---|---|
| `confidence` | `score` | 适配层可短期映射，长期统一为 confidence |
| `display_text` | `corrected || text` | UI 最终显示 display_text |
| `comment.author.name` | `comment.author` | UI 不得自行生成作者 |
| `comment.created_at` | `comment.time` | 仅展示层格式化 |
| `image.width_px/height_px` | 固定画布尺寸 | 必须用 API 尺寸替换固定值 |

`id`、`text`、`bbox` 和从 1 开始的页码可保留。模型选择必须提交 `model_id` 与明确的 `model_version`，不能提交展示字符串。

## 6. Mock 退出策略

- Mock 仅引用 `src/types` 的正式领域类型。
- 每完成一个真实 API，将对应数据源切换到 `src/api`，不重写现有 UI。
- 真实任务按路由 ID 加载，禁止继续使用全局共享结果数组。
- 接口接入完成后保留 Mock 作为开发演示/测试 fixture，而非生产回退数据源。

## 7. 工作台真实数据初始化

- `/workspace` 始终以空页面集、空结果选中状态启动，不从 `mock.ts` 注入默认页面、OCR 结果或文件信息。
- `/workspace/:taskId` 通过 `GET /ocr/jobs/{job_id}`、`GET /ocr/jobs/{job_id}/pages` 及分页结果接口加载真实任务。
- 页面图像继续通过鉴权 HTTP 请求转换为 Blob URL，离开任务时释放。
- 上传区通过 `GET /models` 读取可用模型，创建任务时提交服务器返回的 `model_id` 和 `model_version`。
- 任务加载失败时回到空工作台，不使用 Mock 数据降级。
- `mock.ts` 保留供后续统一清理，不再是工作台运行时数据源。
