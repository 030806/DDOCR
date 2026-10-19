"""Client for the YOLOX process bound to the same deployment host."""

from __future__ import annotations

import ipaddress
import math
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.utils.common import uid


class TerminalPairClient:
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        url = urlsplit(base_url)
        try:
            is_loopback = ipaddress.ip_address(url.hostname or "").is_loopback
        except ValueError:
            is_loopback = False
        if url.scheme != "http" or not is_loopback or url.username or url.password or url.path not in {"", "/"}:
            raise ValueError("YOLOX URL must be an HTTP loopback address, e.g. http://127.0.0.1:8765")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def detect(self, path: Path, width: int, height: int) -> list[dict]:
        with path.open("rb") as source, httpx.Client(timeout=self.timeout, follow_redirects=False, trust_env=False) as client:
            response = client.post(
                f"{self.base_url}/detect",
                files={"image": (path.name, source, "application/octet-stream")},
            )
            response.raise_for_status()
            payload = response.json()
        if payload.get("width") != width or payload.get("height") != height:
            raise ValueError("YOLOX image dimensions do not match the uploaded image")
        points = payload.get("points")
        if not isinstance(points, list):
            raise ValueError("YOLOX response has no points list")
        normalized = []
        for point in points:
            x, y = float(point["x"]), float(point["y"])
            score = float(point["score"])
            if not all(math.isfinite(value) for value in (x, y, score)):
                raise ValueError("YOLOX response contains a non-finite point")
            if not (0 <= x <= width and 0 <= y <= height and 0 <= score <= 1):
                raise ValueError("YOLOX response contains an out-of-range point")
            detection = {"id": uid(), "x": x, "y": y, "score": score, "source": "model"}
            if "bbox" in point:
                bbox = [float(value) for value in point["bbox"]]
                if len(bbox) != 4 or not all(math.isfinite(value) for value in bbox):
                    raise ValueError("YOLOX response contains an invalid box")
                x1, y1, x2, y2 = bbox
                if not (0 <= x1 <= x2 <= width and 0 <= y1 <= y2 <= height):
                    raise ValueError("YOLOX response box is outside the image")
                detection["bbox"] = bbox
            normalized.append(detection)
        return sorted(normalized, key=lambda point: (point["y"], point["x"]))
