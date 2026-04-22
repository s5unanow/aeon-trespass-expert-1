"""Tests for the blank-crop gate in ``image_extractor`` (S5U-700).

Red-before confirmation: at main @ bdb4b1b the gate ``_is_blank_crop``
did not exist. The 122x105 crop of p0046.img0000 (mean luminance 243.8,
variance 32.1) shipped to the reader as a near-empty white rectangle.
These tests fail to import ``_is_blank_crop`` at that commit.
"""

from __future__ import annotations

import io

from PIL import Image

from atr_pipeline.services.pdf.image_extractor import _is_blank_crop


def _encode_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _solid_color(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    img = Image.new("RGB", size, color=color)
    return _encode_jpeg(img)


def _gradient(size: tuple[int, int]) -> bytes:
    w, h = size
    img = Image.new("RGB", size, color=(255, 255, 255))
    pixels = img.load()
    assert pixels is not None
    for y in range(h):
        for x in range(w):
            v = int((x + y) / (w + h) * 255)
            pixels[x, y] = (v, v, v)
    return _encode_jpeg(img)


class TestIsBlankCrop:
    def test_near_white_low_variance_is_blank(self) -> None:
        """Mean≥240, variance<50 → rejected (p0046.img0000 shape)."""
        # Slight noise near white — mean ~250, variance ~4
        img = Image.new("RGB", (100, 100), color=(250, 250, 250))
        assert _is_blank_crop(_encode_jpeg(img)) is True

    def test_gradient_high_variance_passes(self) -> None:
        """A real image with visible content passes."""
        assert _is_blank_crop(_gradient((100, 100))) is False

    def test_pure_black_logo_not_rejected(self) -> None:
        """Adversarial: dark logo (mean ~0) — not blank. Passes."""
        assert _is_blank_crop(_solid_color((100, 100), (0, 0, 0))) is False

    def test_pure_red_solid_not_rejected(self) -> None:
        """Adversarial: saturated solid colour has mean ~76 (gray weighting)
        — not bright enough to trigger the gate."""
        assert _is_blank_crop(_solid_color((100, 100), (255, 0, 0))) is False

    def test_decode_failure_does_not_reject(self) -> None:
        """Fail-open: undecodable bytes are not flagged as blank."""
        assert _is_blank_crop(b"not-an-image") is False

    def test_empty_bytes_does_not_reject(self) -> None:
        """Fail-open: empty input is not flagged."""
        assert _is_blank_crop(b"") is False
