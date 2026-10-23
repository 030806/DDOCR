"""Inspect the actual OCR recognition model and CTC candidates on one photo.

Run from the backend directory after setting the same DDOCR_OCR_* environment
variables as the service:
    python scripts/check_ocr_candidates.py --image /path/to/photo.jpg
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ocr.adapter import OcrAdapter  # noqa: E402
from app.ocr.engine import TerminalOcrEngine  # noqa: E402
from app.ocr.settings import OcrSettings  # noqa: E402
from app.vendor.terminal_ocr_demo.rules import ALLOWED_CHARACTERS  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error(f"image does not exist: {args.image}")

    settings = OcrSettings.from_env()
    if settings.backend != "onnx":
        parser.error("CTC model-candidate capture currently requires DDOCR_OCR_BACKEND=onnx")
    engine = TerminalOcrEngine(settings)
    try:
        onnx_engine = engine.load()
        ocr = onnx_engine._load()
        recognizer = getattr(ocr.text_rec, "_recognizer", ocr.text_rec)
        characters = tuple(recognizer.postprocess_op.character)
        model = {
            "backend": settings.backend,
            "recognition_model": str(settings.onnx_rec_model_path) if settings.onnx_rec_model_path else "RapidOCR bundled default",
            "recognition_keys": str(settings.onnx_rec_keys_path) if settings.onnx_rec_keys_path else "model metadata or RapidOCR default",
            "character_count_including_blank": len(characters),
            "missing_allowed_characters": sorted(
                ALLOWED_CHARACTERS.difference(char.upper() for char in characters)
            ),
            "ctc_candidate_capture_active": hasattr(ocr.text_rec, "_recognizer"),
        }
        result = OcrAdapter(engine).recognize_file(args.image)
        detections = [
            {
                "raw_text": item.attributes.get("raw_text"),
                "output_text": item.text,
                "raw_top1_score": item.confidence,
                "review_required": item.review_required,
                "match_method": (item.attributes.get("assessment") or {}).get("match_method"),
                "model_raw_log_probability": item.attributes.get("model_raw_log_probability"),
                "model_candidates": item.attributes.get("model_candidates", []),
            }
            for item in result.detections
        ]
        print(json.dumps({"model": model, "detections": detections}, ensure_ascii=False, indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
