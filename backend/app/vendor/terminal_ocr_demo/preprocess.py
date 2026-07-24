"""ROI scaling and right-angle orientation variants."""

from dataclasses import dataclass

from PIL import Image


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
) -> list[ProcessedVariant]:
    if scale <= 0:
        raise ValueError("Scale must be positive")

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
    scaled = image.convert("RGB").resize(scaled_size, Image.Resampling.BICUBIC)
    return [
        ProcessedVariant(
            image=scaled.rotate(rotation, expand=True) if rotation else scaled.copy(),
            rotation=rotation,
            scale=scale,
            unrotated_size=scaled_size,
        )
        for rotation in normalized_rotations
    ]
