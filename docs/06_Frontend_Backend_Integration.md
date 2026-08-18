# 前后端第一阶段联调

当前已将任务查询、OCR 结果查询、文件上传和 OCR 任务创建接入 FastAPI。
Konva 展示、纠正、留言和导出仍沿用前端现有逻辑。

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
cd F:\codex\DDOCR\backend
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1  / .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
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

## 上传并创建任务

1. 在工作台点击“替换文件”，选择不超过 200 MB 的 PDF、PNG、JPG 或 JPEG。
2. 文件选择后进入预览检查：图片支持左转、右转，PDF 支持浏览器内预览；可删除或保存。图片旋转会应用到最终上传文件，只有保存后的文件才能创建 OCR 任务。
   保存后可通过上传栏的“预览文件”按钮再次打开预览；预览区域支持纵向和横向滚动，以检查大尺寸图片的完整内容。
3. 点击“开始识别”。
4. 前端依次调用：

   - `POST /api/v1/files/upload-sessions`
   - `PUT /api/v1/files/{file_id}/content`
   - `POST /api/v1/files/{file_id}/complete`
   - `POST /api/v1/ocr/jobs`

4. 创建成功后自动进入 `/workspace/{job_id}`，并通过结果查询 API 加载该
   任务结果。Mock Backend 当前只接受 `model_id=mock` 和
   `model_version=1.0.0`；前端现有模型选择 UI 暂时保留，待真实模型目录
   联调阶段再替换。

## 上传图片与 Konva 背景

上传文件保存在项目内的 `backend/data/uploads/`。SQLite 文件记录的
`storage_path` 保存 `uploads/{file_id}` 相对路径，同时保存图片的
`width_px` 和 `height_px`，不写入开发机绝对路径。

图片内容通过 `GET /api/v1/files/{file_id}/content` 读取。页面查询接口的
`image.url` 返回该地址。该接口要求 Bearer Token，因此前端先通过 axios 下载
Blob，再创建临时 Object URL 交给 Konva。PNG/JPG/JPEG 背景保持
图片宽高比居中适配 700 × 760 画布；OCR bbox 使用同一缩放和偏移。没有
图片 URL 的旧 Mock 页面继续显示原有模拟背景。

当前 PDF 文件仍可上传和创建任务，但不会直接作为浏览器图片展示；PDF
逐页渲染需要后续单独接入。

## 登录、注册与个人信息

未登录访问业务路由会跳转 `/auth`。登录使用联系电话和密码；注册时联系电话
必填且唯一，邮箱可选。注册成功后自动登录；登录令牌保存在
`ddocr.auth.token`，axios 自动附加 Bearer 请求头。用户和会话分别保存为
SQLite 的 `user` 与 `session` 记录。

右上角菜单通过 `GET /api/v1/users/me` 展示姓名、角色、员工编号、部门、
邮箱、脱敏电话和最近登录时间。个人资料更新、修改密码和退出分别调用：

- `PATCH /api/v1/users/me`
- `POST /api/v1/auth/change-password`
- `POST /api/v1/auth/logout`

## 验证数据来源

1. 先按 `backend/README.md` 的 Swagger 步骤创建一个任务。
2. 打开浏览器开发者工具的 Network，刷新“任务记录”。
3. 确认存在 `/api/v1/ocr/jobs` 请求，响应中的任务 ID 与页面列表一致。
4. 点击该任务，确认页面结果请求返回 `XT-101`、`QF10I` 和 `24V DC`。
5. 停止 FastAPI 后刷新，任务页会显示查询失败提示且不会回退到
   `src/mock/tasks.ts`；这可以进一步证明任务列表来自 FastAPI。

工作台无任务 ID 的默认页仍保留原 mock 数据，以确保本阶段不改动上传
入口和现有演示流程。

## 忘记密码联调

登录页点击“忘记密码？”，先提交联系电话和员工编号至 `POST /api/v1/auth/forgot-password`，再将 6 位验证码和新密码提交至 `POST /api/v1/auth/reset-password`。本地可在 `backend/.env` 设置 `DDOCR_EXPOSE_PASSWORD_RESET_CODE=true`，页面会显示开发验证码。重置成功后返回登录状态，旧密码和重置前签发的 Bearer Token 均失效。生产环境不得暴露开发验证码，需替换为短信发送流程。

## 任务记录导出

任务记录页不再读取 `src/mock.ts`。点击导出后，前端使用所选真实任务 ID 调用 `POST /api/v1/ocr/jobs/{job_id}/exports`，确认导出状态后从 `/api/v1/ocr/jobs/{job_id}/exports/{export_id}/download` 下载后端生成的 Excel。任务记录页固定使用精简模式，Excel 仅包含“编号”和“端子排最终识别结果”，结果值优先采用人工纠正后的文本；下载请求自动携带当前 Bearer Token。
