# 前后端第一阶段联调

本阶段只将任务查询和 OCR 结果查询接入 FastAPI。文件上传、Konva 展示、
纠正、留言和导出仍沿用前端现有逻辑。

## 配置

axios 默认使用 `/api/v1` 作为 `baseURL`。Vite 开发服务器会将 `/api`
代理到 `http://127.0.0.1:8000`，因此浏览器联调不需要额外配置 CORS。

后端地址不同时，在启动前端前设置：

```powershell
$env:VITE_BACKEND_BASE_URL = "http://127.0.0.1:8000"
```

如已有网关直接暴露 API，也可用 `VITE_API_BASE_URL` 覆盖 axios 的
`baseURL`。

## 启动

终端一：

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

终端二：

```powershell
npm install
npm run dev
```

打开 Vite 输出的地址，进入“任务记录”。列表调用
`GET /api/v1/ocr/jobs`。点击任务后依次调用：

- `GET /api/v1/ocr/jobs/{job_id}`
- `GET /api/v1/ocr/jobs/{job_id}/pages`
- `GET /api/v1/ocr/jobs/{job_id}/pages/{page_no}/results`

Mock Backend 在任务表为空时会自动创建“端子排 OCR 联调示例”。重启后端并
刷新任务记录即可看到该任务；已有任务时不会重复创建。

## 验证数据来源

1. 先按 `backend/README.md` 的 Swagger 步骤创建一个任务。
2. 打开浏览器开发者工具的 Network，刷新“任务记录”。
3. 确认存在 `/api/v1/ocr/jobs` 请求，响应中的任务 ID 与页面列表一致。
4. 点击该任务，确认页面结果请求返回 `XT-101`、`QF10I` 和 `24V DC`。
5. 停止 FastAPI 后刷新，任务页会显示查询失败提示且不会回退到
   `src/mock/tasks.ts`；这可以进一步证明任务列表来自 FastAPI。

工作台无任务 ID 的默认页仍保留原 mock 数据，以确保本阶段不改动上传
入口和现有演示流程。
