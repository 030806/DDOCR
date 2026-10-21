# YOLOX 端子对检测部署与验证

本说明对应 [接入方案](13_YOLOX_端子对计数与PPOCR接入方案.md)。DDOCR 后端和 YOLOX 推理服务运行在**同一台远端 GPU 服务器**的不同 Python 环境中。浏览器只连接 DDOCR。YOLOX 服务仅监听 `127.0.0.1`，后端也只接受回环地址作为其服务 URL。

## 模型与版本

- YOLOX 源码：已随 DDOCR 放在 `third_party/YOLOX`，版本 `0.3.0`，Git 提交 `6ddff4824372906469a7fae2dc3206c7aa4bbaee`。仅包含源码，不包含训练数据、训练输出或编译产物；检测模型代码目录 `yolox/` 无本地改动。
- 实验配置：`backend/yolox_service/terminal_pair_yolox_s.py`。YOLOX-S，单类 `terminal_pair`，测试输入 `1024×1024`。
- 权重：`backend/model_weights/terminal_pair_yolox_s/best_ckpt.pth`。该文件已从用户提供的训练输出复制并校验哈希，SHA-256 为 `EAA7652748ADFA3A8BDDCF84BABB9EEAC4AA84CFCCC0928F3FE65B50E7406642`。Git 已忽略 `*.pth`；压缩交付目录时须确认该文件已包含在包内。
- 后处理初始值：置信度 `0.30`、NMS `0.65`，可用环境变量调整。验证集 AP 不能代替逐图计数准确率，现场图片仍需人工核对蓝点。

## 远端服务器安装

先按现有 DDOCR 流程部署前端、后端和数据库，并在 `backend` 目录执行 `python -m alembic upgrade head`。本次迁移 `a1_terminal_pair_points` 为页面新增原始检测点、有效点和修订号字段。

再为 YOLOX 创建独立 Python 环境。安装与部署 GPU 兼容的 PyTorch，并在该环境中安装 DDOCR 内置的 YOLOX 0.3.0 源码及其依赖；训练环境使用的版本是 PyTorch `2.1.2+cu121`。安装顺序必须先有 PyTorch，再安装 YOLOX 的依赖。这里采用普通安装，使运行时不依赖源码安装时的绝对路径。推理服务额外依赖见 `backend/yolox_service/requirements.txt`。

示例（先在服务器进入 DDOCR 根目录，目录可位于任意位置）：

```bash
DDOCR_ROOT="$(pwd -P)"
conda activate yolox
python -m pip install -r "$DDOCR_ROOT/third_party/YOLOX/requirements.txt"
python -m pip install -v "$DDOCR_ROOT/third_party/YOLOX" --no-build-isolation --no-deps
python -m pip install -r "$DDOCR_ROOT/backend/yolox_service/requirements.txt"
python -c "import yolox; print(yolox.__version__)"

cd "$DDOCR_ROOT/backend"
export YOLOX_DEVICE=cuda:0
export YOLOX_CONFIDENCE=0.30
export YOLOX_NMS=0.65
python -m uvicorn yolox_service.app:app --host 127.0.0.1 --port 8765
```

模型配置和权重默认从 `backend/yolox_service/`、`backend/model_weights/` 相对定位，无须填写服务器绝对路径。若改用 `pip install -e` 可编辑安装，则移动 DDOCR 目录后需在新位置重新安装 YOLOX。

YOLOX 服务启动时加载权重；权重缺失、模型结构不匹配或 GPU 不可用会使启动失败。确认 `curl http://127.0.0.1:8765/health` 返回 `{"status":"ok"}` 后，在 **DDOCR 后端环境**设置 `DDOCR_YOLOX_URL=http://127.0.0.1:8765` 并重启 DDOCR。后端和 YOLOX 服务均应由部署平台管理进程及日志。没有配置这个地址时，既有 OCR 可以继续运行，但页面会显示“端子检测服务未配置”，无法自动生成端子号。

## 接口及页面行为

- DDOCR 工作线程在图片任务启动后并行发起整图 YOLOX 检测和 PPOCR 识别。PPOCR 按当前选区运行；重新识别复用原选区；PDF 仍只走原 OCR 路径。
- YOLOX 服务 `POST /detect` 接收图片，返回原图像素坐标下的中心点及置信度。DDOCR 保存原始点和有效点，页面只画蓝色中心点，不画 YOLOX 框。
- `GET /api/v1/ocr/jobs/{job_id}/pages` 增加 `terminal_model_points`、`terminal_points`、`terminal_error`、`terminal_revision` 字段，不改变已有 OCR 结果接口。历史页面的 `terminal_points=null` 表示没有端子检测记录；`[]` 表示模型正常运行但检出 0 个。
- `PUT /api/v1/ocr/jobs/{job_id}/pages/{page_no}/terminal-points` 接收全部有效点与 `base_revision`，用于增删和移动蓝点；并发修订冲突返回 409。原始模型点不受人工修正影响。
- 表格行数为 `max(有效蓝点数, 有效线号数)`。端子号只填前 N 行，多出的线号仍出现在表格中。图片任务导出的 Excel 另含“端子对照表”工作表。

## 上线核查

### 重启后查看历史端子点

识别成功的原始点和有效点分别保存到数据库 `pages.terminal_model_points`、`pages.terminal_points`，人工点击“保存端子点”后写入有效点并递增 `terminal_revision`。重启后从任务记录打开同一任务即可读取，无须重新运行 YOLOX；尚未保存的编辑草稿不会保留。`terminal_points=null` 的旧任务或检测失败任务不显示端子编辑按钮，`[]` 表示检测完成但没有有效点，仍支持编辑补点。

新识别需要分别启动 DDOCR 与 YOLOX；IDE 重启不会自动启动独立 YOLOX 进程，终端的 `$env:YOLOX_DEVICE` 也需重新设置。DDOCR 从 `backend/.env` 读取 `DDOCR_YOLOX_URL`；保持数据库地址不变。启动后先检查 `http://127.0.0.1:8765/health`。历史结果缺失时核对当前任务 ID、页面接口的 `terminal_points`/`terminal_error`，不要把未检测的旧任务当作已有结果丢失。

结果表格每行均提供选择框，包括端子数多于 OCR 线号数时的空线号行；“全选当前”和已选数量按表格行计算。删除、恢复仅处理所选行关联的 OCR 结果，空线号行不提交给 OCR 复核接口。端子点的删除仍在图片端子点编辑中进行。

端子点编辑：点击原图空白处时，新点落在鼠标点击对应的原图位置，坐标转换包含查看器缩放和图片居中偏移。图片外的画布留白不生成端子点。新增后点击“保存端子点”持久化修改。

1. 上传一张真实现场图片，分别测试整图 OCR 与选区 OCR。确认两种情况下 YOLOX 蓝点数一致，OCR 结果随选区变化。
2. 点击重新识别，确认 OCR 沿用原选区、YOLOX 仍检测整图。
3. 补一个蓝点、删一个蓝点、拖动一个蓝点，保存并刷新；确认有效点、端子号和表格同步变化，原始点数量不变。
4. 核查 `N>M` 与 `M>N` 的表格和 Excel，以及 YOLOX 服务中断时 OCR 结果仍可查看。

本地已通过模拟检测器的接口测试；由于本机未安装与部署 GPU 对应的 PyTorch 环境，真实权重的推理冒烟测试须在远端 GPU 服务器完成。
