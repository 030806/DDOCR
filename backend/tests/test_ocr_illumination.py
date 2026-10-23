import numpy as np
import pytest
from PIL import Image

from app.vendor.terminal_ocr_demo.preprocess import generate_variants


def test_he_and_clahe_preserve_geometry_but_change_luminance():
    pixels = np.full((64, 64, 3), 25, dtype=np.uint8)
    pixels[:, 32:] = 60
    image = Image.fromarray(pixels)
    baseline = generate_variants(image, 1.0, (0,), "none")[0].image
    for mode in ("he", "clahe"):
        variant = generate_variants(image, 1.0, (0,), mode)[0].image
        assert variant.size == baseline.size
        assert not np.array_equal(np.asarray(variant), np.asarray(baseline))


def test_unknown_illumination_mode_is_rejected():
    with pytest.raises(ValueError, match="illumination"):
        generate_variants(Image.new("RGB", (10, 10)), 1.0, (0,), "unknown")
