"""GPU inference process for terminal-pair centers.

Run this only on the deployment host, bound to 127.0.0.1. DDOCR sends uploaded
images over loopback; browsers never call this service.
"""

from __future__ import annotations

import io
import ipaddress
import os
from pathlib import Path
from threading import Lock

import cv2
import numpy as np
import torch
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
from yolox.data.data_augment import ValTransform
from yolox.exp import get_exp
from yolox.utils import postprocess


ROOT = Path(__file__).resolve().parents[1]
EXP_FILE = Path(os.getenv("YOLOX_EXP_FILE", str(Path(__file__).with_name("terminal_pair_yolox_s.py"))))
WEIGHTS = Path(os.getenv(
    "YOLOX_WEIGHTS",
    str(ROOT / "model_weights" / "terminal_pair_yolox_s" / "best_ckpt.pth"),
))
MAX_IMAGE_BYTES = 209_715_200
CONFIDENCE = float(os.getenv("YOLOX_CONFIDENCE", "0.30"))
NMS = float(os.getenv("YOLOX_NMS", "0.65"))
DEVICE = os.getenv("YOLOX_DEVICE", "cuda:0")
app = FastAPI(title="DDOCR terminal-pair YOLOX")
_model = None
_preproc = ValTransform(legacy=False)
_lock = Lock()


@app.middleware("http")
async def local_requests_only(request: Request, call_next):
    try:
        is_local = ipaddress.ip_address(request.client.host if request.client else "").is_loopback
    except ValueError:
        is_local = False
    if not is_local:
        return JSONResponse(status_code=403, content={"detail": "Loopback access only"})
    return await call_next(request)


@app.on_event("startup")
def load_model() -> None:
    global _model
    if not WEIGHTS.is_file():
        raise RuntimeError(f"YOLOX checkpoint is missing: {WEIGHTS}")
    if not EXP_FILE.is_file():
        raise RuntimeError(f"YOLOX experiment file is missing: {EXP_FILE}")
    exp = get_exp(str(EXP_FILE), None)
    if exp.num_classes != 1 or tuple(exp.test_size) != (1024, 1024):
        raise RuntimeError("YOLOX experiment does not match the trained terminal-pair model")
    model = exp.get_model()
    checkpoint = torch.load(str(WEIGHTS), map_location="cpu")
    model.load_state_dict(checkpoint["model"], strict=True)
    model.eval().to(DEVICE)
    _model = model


@app.get("/health")
def health() -> dict:
    return {"status": "ok" if _model is not None else "loading"}


@app.post("/detect")
def detect(image: UploadFile = File(...)) -> dict:
    if _model is None:
        raise HTTPException(503, "YOLOX model is not ready")
    raw = image.file.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image is too large")
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            if opened.width * opened.height > 100_000_000:
                raise HTTPException(413, "Image dimensions are too large")
            opened.load()
            rgb = np.asarray(opened.convert("RGB"))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(422, "Invalid image") from exc
    height, width = rgb.shape[:2]
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    ratio = min(1024 / height, 1024 / width)
    processed, _ = _preproc(bgr, None, (1024, 1024))
    tensor = torch.from_numpy(processed).unsqueeze(0).float().to(DEVICE)
    with _lock, torch.no_grad():
        output = postprocess(
            _model(tensor), 1, CONFIDENCE, NMS, class_agnostic=True,
        )[0]
    points = []
    if output is not None:
        for row in output.cpu().numpy():
            x1, y1, x2, y2 = (float(value) / ratio for value in row[:4])
            points.append({
                "x": max(0.0, min(float(width), (x1 + x2) / 2)),
                "y": max(0.0, min(float(height), (y1 + y2) / 2)),
                "score": float(row[4] * row[5]),
                "bbox": [
                    max(0.0, min(float(width), x1)),
                    max(0.0, min(float(height), y1)),
                    max(0.0, min(float(width), x2)),
                    max(0.0, min(float(height), y2)),
                ],
            })
    points.sort(key=lambda point: (point["y"], point["x"]))
    return {"width": width, "height": height, "points": points}
