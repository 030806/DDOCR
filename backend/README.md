# DDOCR Backend

FastAPI 后端，REST 接口统一位于 `/api/v1`。业务数据存储在 PostgreSQL，上传文件和导出文件仍保存在 `DDOCR_DATA_DIR` 指定的本地目录。

## PostgreSQL 配置

复制环境变量示例并填写密码（`.env` 已被 Git 忽略）：

```powershell
Copy-Item .env.example .env
```

关键配置：

```dotenv
DDOCR_DATABASE_URL=postgresql+psycopg://postgres:your-password@localhost:5432/ddocr
DDOCR_DATA_DIR=./data
```

数据库 `ddocr` 需提前创建。首次启动或模型变更后执行迁移：

```powershell
cd backend
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m alembic upgrade head
```

查看当前迁移版本：

```powershell
python -m alembic current
```

## 启动与测试

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
python -m pytest -q
```

## 真实 OCR 运行环境

`requirements.txt` 同时包含 FastAPI、关系数据库、测试工具和真实 PaddleOCR 推理依赖。
后端直接使用的 Pydantic 也已显式锁定。安装后建议执行 `python -m pip check`。

真实 OCR 默认使用 CPU、2 倍缩放和四方向识别，可通过环境变量调整：

```dotenv
DDOCR_OCR_DEVICE=cpu
DDOCR_OCR_SCALE=2.0
DDOCR_OCR_ROTATIONS=0,90,180,270
DDOCR_OCR_MAX_CONCURRENCY=1
DDOCR_OCR_EXECUTION_MODE=async
```

模型代码和端子编号库位于 `app/vendor/terminal_ocr_demo/`，不依赖仓库根目录的
`demo/` 或启动时的当前工作目录。PaddleOCR/PaddleX 首次导入和模型加载可能较慢。

真实模型测试默认不执行，需要分别设置 `DDOCR_RUN_PADDLE_SMOKE=1` 或
`DDOCR_RUN_REAL_OCR_API=1` 后运行对应 integration 测试。

`POST /api/v1/ocr/jobs` 创建 queued 任务后立即返回 HTTP 202。进程内单线程 Worker
异步执行真实 OCR；客户端应轮询 Job，成功后再读取 Pages/Results。

测试使用临时 SQLite 数据库，不会读写开发环境中的 `ddocr`。生产 PostgreSQL 表只通过 Alembic 管理，应用启动不会隐式建表。

认证模块已经使用 `tenants`、`users`、`sessions` 关系表作为唯一数据源。迁移 `622436c321e7` 会幂等导入旧 `objects(kind='user'/'session')` 数据；文件、OCR 任务及结果在后续里程碑迁移。

文件和 OCR 任务模块使用 `files`、`ocr_jobs` 关系表作为唯一数据源。迁移 `3670a613f7e1` 会幂等导入旧 `objects(kind='file'/'job')` 数据。

OCR 页面和结果使用 `pages`、`results` 关系表作为唯一数据源。迁移 `444de64a7889` 会幂等导入旧 `objects(kind='page'/'result')` 数据。导出和幂等记录仍由兼容存储承载。

OCR 纠正和评论使用 `corrections`、`comments` 关系表作为唯一数据源。迁移 `e78094b5441f` 会幂等导入旧 `objects(kind='correction'/'comment')` 数据，作者外键和编辑/删除权限保持不变。

导出和幂等响应使用 `exports`、`idempotency_records` 关系表作为唯一数据源。迁移 `cae54d372859` 会幂等导入旧 `objects(kind='export'/'idempotency')` 数据。业务代码不再读写通用 `objects` 表。

健康检查：`GET http://127.0.0.1:8000/health`；Swagger：`http://127.0.0.1:8000/docs`。
