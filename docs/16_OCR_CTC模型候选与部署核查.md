# OCR 模型概率候选与部署核查

状态：代码已接入默认的 RapidOCR / ONNX 后端；尚未在远端真实识别模型和现场照片上完成效果验收。更新日期：2026-10-27。

## 当前行为

RapidOCR 1.4.4 的文本识别器在同一次模型前向计算中得到 `[批次, 时间步, 字符类别]` 的 CTC 输出。项目内的 `CandidateTextRecognizer` 在 RapidOCR 常规解码前读取该输出，对含非法字符的文本使用与该模型绑定的字符表和 blank 类生成最多 5 个**完整文本**候选，并计算原始首选文本的 CTC 序列对数概率。候选不是根据整条 OCR 置信度猜出的“第二个字符”，也不需要再做一次模型推理。原 RapidOCR 检测框、首选文本和分数保持不变。

后处理仅在以下条件**同时成立**时采用模型候选：原始文本有且只有一个非法字符；候选长度相同且仅在该字符处不同；候选所有字符均在大写 `A–Z`、数字 `0–9`、`-`、`/` 内；候选本身是编号库或现有完整格式规则认可的线号；其 CTC 序列概率至少是原始文本的 `DDOCR_OCR_CTC_MIN_RELATIVE_PROBABILITY` 倍。采用后仍标记为待人工复核，并保存原文、候选文本及对数概率。低于门槛、多个非法字符、候选不满足编号规则或模型输出与字符表不匹配时，删除原始文本中的非法字符并提示人工核对；如果没有合法字符剩余，则显示单个 `#`。字典中的 `-` 与 `/` 不会被删除，但现有完整编号规则尚未确认它们的位置，因此不能仅凭这两个字符自动确认一个新线号。

结果 `confidence` 继续表示 RapidOCR 对**原始首选文本**的聚合分数，不能解释成替换后文本的概率。候选及原始文本的 CTC 对数概率写入结果 `attributes`，`assessment.match_method=model_probability_correction` 表示采用了候选。

## 模型来源必须核对

`DDOCR_OCR_BACKEND` 未设置时默认 `onnx`。当前 ONNX 初始化若不提供模型路径，使用 `rapidocr-onnxruntime==1.4.4` 自带的识别模型。`DemoConfig.rec_model_name=PP-OCRv5_mobile_rec` 只作用于 `paddle` 路径，**不代表 ONNX 路径已使用 PPOCR 微调权重**。部署人员如要使用项目训练得到的权重，需要提供兼容 RapidOCR 1.4.4 预处理及 CTC `[B,T,C]` 输出的 ONNX 识别模型，并确认字符表与类别数量、顺序一致。

在服务器的 `backend/.env` 中可配置：

```dotenv
DDOCR_OCR_BACKEND=onnx
DDOCR_OCR_ONNX_REC_MODEL_PATH=/absolute/path/to/terminal_rec.onnx
DDOCR_OCR_ONNX_REC_KEYS_PATH=/absolute/path/to/rec_keys.txt
DDOCR_OCR_CTC_MIN_RELATIVE_PROBABILITY=0.5
```

两个路径必须同时配置或同时不填；不填时运行 RapidOCR 自带模型。自定义 `rec_keys_path` 必须与 ONNX 模型配套，避免模型类别数相同但字符顺序不同而产生错误替换。模型字符表必须包含所需的合法字符，否则后处理字典无法让模型凭空识别该字符。路径只在服务器自身解析，与开发者电脑的盘符无关。若改用 `paddle` 后端，当前仍只接收首选文本和整条分数，不执行这一模型概率候选步骤。

## 远端核查与验收

从 `backend` 目录、使用与服务相同的 Python 环境和环境变量，运行：

```bash
python scripts/check_ocr_candidates.py --image /absolute/path/to/test_photo.jpg
```

脚本打印后端、实际配置的识别模型路径、字符表类别数、缺失的合法字符以及每个最终检测结果的原文、输出、候选分数和复核状态。先检查 `ctc_candidate_capture_active=true`、模型路径符合预期、字符表没有意外缺失，再观察含括号或中文误识的照片。代码单元测试覆盖 CTC blank/重复字符、候选排序、批次顺序映射、低概率拒绝及待复核标记；仍须用人工确认的现场图片比较整条线号正确率、误替换率和推理耗时，才能调整 `0.5` 这一初始门槛或决定正式启用的模型权重。

当前实现依赖固定版本 RapidOCR 的内部识别器结构。升级 RapidOCR 或替换成非 CTC 模型时必须先运行上述核查及单元测试；不兼容时系统保留原首选文本流程，不应宣称候选替换已生效。

参考：[RapidOCR 1.4.4 识别器源码](https://github.com/RapidAI/RapidOCR/blob/v1.4.4/python/rapidocr_onnxruntime/ch_ppocr_rec/text_recognize.py)、[CTC 解码源码](https://github.com/RapidAI/RapidOCR/blob/v1.4.4/python/rapidocr_onnxruntime/ch_ppocr_rec/utils.py)。
