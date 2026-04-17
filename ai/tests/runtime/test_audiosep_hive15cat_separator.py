from __future__ import annotations

import numpy as np
import pytest

from ai.ai_runtime.separation.audiosep_hive15cat_separator import AudioSepHive15CatSeparator


class FakeOnnxSession:
    def run(self, _outputs, inputs):
        mixture = np.asarray(inputs["mixture"], dtype=np.float32)
        category_idx = int(np.asarray(inputs["category_idx"], dtype=np.int64)[0])
        scale = 0.25 * float(category_idx + 1)
        return [mixture * scale]


def make_separator() -> AudioSepHive15CatSeparator:
    separator = AudioSepHive15CatSeparator.__new__(AudioSepHive15CatSeparator)
    separator.categories = ["keyboard typing", "phone ringing", "alarm"]
    separator._category_lookup = {
        label.casefold(): index for index, label in enumerate(separator.categories)
    }
    separator.sample_rate = 32
    separator.segment_seconds = 1.0
    separator.segment_samples = 32
    separator.overlap_samples = 8
    separator._session = FakeOnnxSession()
    return separator


def test_resolve_category_rejects_unknown_label():
    separator = make_separator()
    assert separator.resolve_category("alarm") == 2
    assert separator.resolve_category("ALARM") == 2

    with pytest.raises(ValueError, match="Unknown AudioSepHive15Cat category"):
        separator.resolve_category("traffic")


def test_separate_resamples_stereo_and_preserves_length():
    separator = make_separator()
    left = np.linspace(-0.5, 0.5, 24, dtype=np.float32)
    right = np.linspace(0.5, -0.5, 24, dtype=np.float32)
    audio = np.column_stack([left, right])

    separated = separator.separate(
        audio=audio,
        sample_rate=16,
        categories=["alarm"],
    )

    assert separated.shape == audio.shape
    assert separated.dtype == np.float32
    np.testing.assert_allclose(separated[:, 0], separated[:, 1], atol=1e-6)


def test_overlap_add_windowing_does_not_create_boundary_spikes():
    separator = make_separator()
    audio = np.ones(80, dtype=np.float32)

    separated = separator.separate(
        audio=audio,
        sample_rate=32,
        categories=["keyboard typing"],
    )

    assert separated.shape == audio.shape
    np.testing.assert_allclose(separated, np.full_like(audio, 0.25), atol=1e-4)
    assert np.max(np.abs(np.diff(separated))) < 1e-4
