"""ROI scaling and right-angle orientation variants."""

from dataclasses import dataclass

from PIL import Image
import cv2
import numpy as np


@dataclass(frozen=True)
class ProcessedVariant:
    image: Image.Image
    rotation: int
    scale: float
    unrotated_size: tuple[int, int]


def generate_variants(
    image: Image.Image,
    scale: float,
    rotations: tuple[int, ...],
    illumination: str = "none",
) -> list[ProcessedVariant]:
    if scale <= 0:
        raise ValueError("Scale must be positive")
    if illumination not in {"none", "he", "clahe"}:
        raise ValueError("Unknown illumination mode")

    normalized_rotations: list[int] = []
    for rotation in rotations:
        normalized = rotation % 360
        if normalized not in {0, 90, 180, 270}:
            raise ValueError("Only right-angle rotations are supported")
        if normalized not in normalized_rotations:
            normalized_rotations.append(normalized)

    scaled_size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    rgb = image.convert("RGB")
    if illumination != "none":
        lab = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2LAB)
        if illumination == "he":
            lab[:, :, 0] = cv2.equalizeHist(lab[:, :, 0])
        else:
            lab[:, :, 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
        rgb = Image.fromarray(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))
    scaled = rgb.resize(scaled_size, Image.Resampling.BICUBIC)
    return [
        ProcessedVariant(
            image=scaled.rotate(rotation, expand=True) if rotation else scaled.copy(),
            rotation=rotation,
            scale=scale,
            unrotated_size=scaled_size,
        )
        for rotation in normalized_rotations
    ]
