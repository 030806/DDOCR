# DDOCR Mock Backend

第一阶段 FastAPI 后端，严格使用 `/api/v1` 和 `snake_case`，提供上传、Mock OCR 任务、状态与结果查询、纠正、留言及 Excel 导出。数据保存在 `backend/data/mock.db`，文件与导出物分别位于 `data/uploads`、`data/exports`。未接入真实 OCR、Celery、PostgreSQL 或对象存储。

## 启动

需要 Python 3.11：

```powershell
cd backend
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：`GET http://127.0.0.1:8000/health`。

## 测试

```powershell
cd backend
python -m pytest -q
```

测试覆盖完整主链路、`bbox` 格式、纠正 revision 冲突、留言保存和 Excel 下载。

## Swagger 验证

1. 启动服务并打开 `http://127.0.0.1:8000/docs`。
2. 调用 `POST /api/v1/files/upload-sessions` 创建上传会话。
3. 使用返回的 `upload_url`（Swagger 中对应 `PUT /api/v1/files/{file_id}/content`）上传任意字节。
4. 调用 `POST /api/v1/files/{file_id}/complete`。
5. 使用 `model_id=mock`、`model_version=1.0.0` 创建 OCR 任务。
6. 查询任务、页面和结果，再用结果 ID 验证纠正、留言和导出接口。

OpenAPI JSON 位于 `http://127.0.0.1:8000/openapi.json`。本地 `PUT content` 是首期对对象存储签名上传的替代，后续可替换存储适配器而不改变其余业务接口。
