# 关系型存储迁移报告

## 迁移结果

| 里程碑 | 模块 | 关系表 | Alembic 版本 |
|---|---|---|---|
| 2 | 认证、会话 | `tenants`、`users`、`sessions` | `622436c321e7` |
| 3 | 文件、OCR 任务 | `files`、`ocr_jobs` | `3670a613f7e1` |
| 4 | OCR 页面、结果 | `pages`、`results` | `444de64a7889` |
| 5 | 纠正、评论 | `corrections`、`comments` | `e78094b5441f` |
| 6 | 导出、幂等响应 | `exports`、`idempotency_records` | `cae54d372859` |

所有数据迁移均使用冲突更新或冲突忽略语义，可以安全重复执行数据导入逻辑。API 路径与响应契约保持不变。

## 已移除的 Store 用法

应用业务代码已经移除全部 `Store.get()`、`Store.put()`、`Store.all()` 调用。以下对象类型不再写入 `objects`：

`user`、`session`、`file`、`job`、`page`、`result`、`correction`、`comment`、`export`、`idempotency`。

## 保留的 objects 引用

- `app/models/store.py` 保留通用表模型和兼容读写实现，供历史数据检查与必要的回滚工具使用。
- Alembic 迁移脚本读取 `objects`，用于一次性导入历史数据。
- 迁移验收测试查询 `objects`，确认新业务请求不再产生通用对象记录。
- `objects` 表不会删除，当前运行时业务模块不再依赖该表。

`Store` 目前仍提供 SQLAlchemy engine 以及上传/导出本地目录路径；这些基础设施用途不读取或写入 `objects`。
