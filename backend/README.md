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

测试使用临时 SQLite 数据库，不会读写开发环境中的 `ddocr`。生产 PostgreSQL 表只通过 Alembic 管理，应用启动不会隐式建表。

健康检查：`GET http://127.0.0.1:8000/health`；Swagger：`http://127.0.0.1:8000/docs`。
