from __future__ import annotations

import numpy as np
import pytest

from ai.ai_runtime.separation.codecsep_dnrv2_15cat_separator import (
    CodecSepDNRv2_15CatSeparator,
)


class FakeOnnxSession:
    def run(self, _outputs, inputs):
        mixture = np.asarray(inputs["mixture"], dtype=np.float32)
        category_idx = int(np.asarray(inputs["category_idx"], dtype=np.int64)[0])
        scale = 0.1 * float(category_idx + 1)
        return [mixture * scale]


def make_separator() -> CodecSepDNRv2_15CatSeparator:
    separator = CodecSepDNRv2_15CatSeparator.__new__(CodecSepDNRv2_15CatSeparator)
    separator.model_label = "CodecSepDNRv2_15Cat"
    separator.categories = ["speech", "keyboard typing", "alarm"]
    separator._category_lookup = {
        label.casefold(): index for index, label in enumerate(separator.categories)
    }
    separator.sample_rate = 16
    separator.segment_seconds = 2.0
    separator.overlap_seconds = 0.5
    separator.segment_samples = 32
    separator.overlap_samples = 8
    separator._session = FakeOnnxSession()
    return separator


def test_resolve_category_rejects_unknown_label():
    separator = make_separator()
    assert separator.resolve_category("alarm") == 2
    assert separator.resolve_category("ALARM") == 2

    with pytest.raises(ValueError, match="Unknown CodecSepDNRv2_15Cat category"):
        separator.resolve_category("traffic")


def test_separate_resamples_stereo_and_preserves_length():
    separator = make_separator()
    left = np.linspace(-0.4, 0.4, 24, dtype=np.float32)
    right = np.linspace(0.4, -0.4, 24, dtype=np.float32)
    audio = np.column_stack([left, right])

    separated = separator.separate(
        audio=audio,
        sample_rate=8,
        categories=["alarm"],
    )

    assert separated.shape == audio.shape
    assert separated.dtype == np.float32
    np.testing.assert_allclose(separated[:, 0], separated[:, 1], atol=1e-6)


def test_overlap_add_windowing_uses_package_overlap_seconds():
    separator = make_separator()
    audio = np.ones(80, dtype=np.float32)

    separated = separator.separate(
        audio=audio,
        sample_rate=16,
        categories=["speech"],
    )

    assert separated.shape == audio.shape
    np.testing.assert_allclose(separated, np.full_like(audio, 0.1), atol=1e-4)
    assert np.max(np.abs(np.diff(separated))) < 1e-4
