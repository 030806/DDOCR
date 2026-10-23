"""Compare baseline OCR, global HE and CLAHE on the same image set.

Example from the backend directory:
    python scripts/compare_illumination.py --images /data/test_photos \
        --truth /data/test_photos/ground_truth.csv --output /data/he_results.csv

ground_truth.csv has columns ``file_name,codes``; separate multiple expected
codes with ``|``. An omitted truth file still writes predictions for review.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ocr.adapter import OcrAdapter  # noqa: E402
from app.ocr.engine import TerminalOcrEngine  # noqa: E402
from app.ocr.settings import OcrSettings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--truth", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    images = sorted(path for path in args.images.iterdir()
                    if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"})
    if not images:
        parser.error("No supported images found in --images")

    truth: dict[str, list[str]] = {}
    if args.truth:
        with args.truth.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                truth[row["file_name"]] = [code.strip() for code in row["codes"].split("|") if code.strip()]

    rows = []
    settings = OcrSettings.from_env()
    for mode in ("none", "he", "clahe"):
        engine = TerminalOcrEngine(replace(settings, illumination=mode))
        adapter = OcrAdapter(engine)
        try:
            for image in images:
                try:
                    result = adapter.recognize_file(image)
                    codes = [item.text for item in result.detections if item.text]
                    expected = truth.get(image.name)
                    rows.append({
                        "file_name": image.name, "mode": mode,
                        "predicted_codes": "|".join(codes),
                        "expected_codes": "|".join(expected) if expected is not None else "",
                        "exact_code_multiset": "" if expected is None else int(Counter(codes) == Counter(expected)),
                        "review_count": sum(item.review_required for item in result.detections),
                        "processing_ms": result.processing_ms, "error": "",
                    })
                except Exception as exc:
                    rows.append({"file_name": image.name, "mode": mode, "predicted_codes": "",
                                 "expected_codes": "", "exact_code_multiset": "",
                                 "review_count": "", "processing_ms": "",
                                 "error": f"{type(exc).__name__}: {exc}"})
        finally:
            engine.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} comparisons to {args.output}")


if __name__ == "__main__":
    main()
