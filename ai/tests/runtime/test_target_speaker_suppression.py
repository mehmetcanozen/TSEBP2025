from __future__ import annotations

import numpy as np
import pytest

from ai.ai_runtime.suppression import SemanticSuppressor


class FailingDetector:
    def classify(self, audio, sample_rate):
        raise AssertionError("target_speaker mode should not run category detection")


class FakeTargetSpeakerSeparator:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def extract(
        self,
        audio,
        sample_rate,
        reference_audio,
        reference_sample_rate,
        reference_path=None,
    ):
        self.calls.append(
            {
                "sample_rate": sample_rate,
                "reference_sample_rate": reference_sample_rate,
                "reference_audio": np.asarray(reference_audio, dtype=np.float32).copy(),
                "reference_path": reference_path,
            },
        )
        return np.asarray(audio, dtype=np.float32) * 0.30


class FakeMasking:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def apply(self, *, mix, unwanted, aggressiveness, sample_rate, **kwargs):
        self.calls.append(
            {
                "mix": np.asarray(mix, dtype=np.float32).copy(),
                "unwanted": np.asarray(unwanted, dtype=np.float32).copy(),
                "aggressiveness": aggressiveness,
                "sample_rate": sample_rate,
                "kwargs": kwargs,
            },
        )
        return np.asarray(mix, dtype=np.float32) - np.asarray(unwanted, dtype=np.float32)


def test_target_speaker_backend_directly_subtracts_extracted_speaker(monkeypatch):
    target_separator = FakeTargetSpeakerSeparator()
    masking = FakeMasking()
    suppressor = SemanticSuppressor(
        detector=FailingDetector(),
        target_speaker=target_separator,
        separator_backend="target_speaker",
    )
    monkeypatch.setattr(suppressor, "_get_masking_strategy", lambda *_args: masking)

    audio = np.ones(1024, dtype=np.float32)
    reference = np.linspace(-0.2, 0.2, 64, dtype=np.float32)

    result = suppressor.suppress(
        audio=audio,
        sample_rate=16000,
        suppress_categories=["typing"],
        target_speaker_reference_audio=reference,
        target_speaker_reference_sample_rate=8000,
        target_speaker_scale=0.5,
        return_details=True,
    )

    assert target_separator.calls[0]["sample_rate"] == 16000
    assert target_separator.calls[0]["reference_sample_rate"] == 8000
    assert masking.calls == []
    np.testing.assert_allclose(result["clean_audio"], audio * 0.85, atol=1e-6)
    np.testing.assert_allclose(result["removed_audio"], audio * 0.15, atol=1e-6)
    assert result["backend"] == "target_speaker"


def test_target_speaker_backend_can_opt_into_spectral_masking(monkeypatch):
    target_separator = FakeTargetSpeakerSeparator()
    masking = FakeMasking()
    suppressor = SemanticSuppressor(
        detector=FailingDetector(),
        target_speaker=target_separator,
        separator_backend="target_speaker",
    )
    monkeypatch.setattr(suppressor, "_get_masking_strategy", lambda *_args: masking)

    audio = np.ones(1024, dtype=np.float32)
    reference = np.linspace(-0.2, 0.2, 64, dtype=np.float32)

    result = suppressor.suppress(
        audio=audio,
        sample_rate=16000,
        target_speaker_reference_audio=reference,
        target_speaker_reference_sample_rate=8000,
        target_speaker_reconstruction="spectral_mask",
        return_details=True,
    )

    assert len(masking.calls) == 1
    np.testing.assert_allclose(masking.calls[0]["unwanted"], audio * 0.30)
    assert masking.calls[0]["kwargs"]["mask_floor"] == pytest.approx(0.05)
    assert masking.calls[0]["kwargs"]["max_suppression_ratio"] == pytest.approx(0.90)
    assert masking.calls[0]["kwargs"]["speech_dominance_threshold"] == pytest.approx(2.0)
    np.testing.assert_allclose(result["clean_audio"], audio * 0.70, atol=1e-6)
    np.testing.assert_allclose(result["removed_audio"], audio * 0.30, atol=1e-6)
    assert result["backend"] == "target_speaker"


def test_target_speaker_engine_alias_reaches_separator(monkeypatch):
    captured: dict[str, object] = {}
    suppressor = SemanticSuppressor(
        detector=FailingDetector(),
        separator_backend="target_speaker",
    )

    def fake_get_target_speaker_separator(**kwargs):
        captured.update(kwargs)
        return FakeTargetSpeakerSeparator()

    monkeypatch.setattr(
        suppressor,
        "_get_target_speaker_separator",
        fake_get_target_speaker_separator,
    )

    audio = np.ones(128, dtype=np.float32)
    reference = np.ones(32, dtype=np.float32)

    suppressor.suppress(
        audio=audio,
        sample_rate=16000,
        target_speaker_reference_audio=reference,
        target_speaker_reference_sample_rate=16000,
        target_speaker_engine="tsextractt",
    )

    assert captured["engine"] == "tsextract"


def test_target_speaker_backend_requires_reference():
    suppressor = SemanticSuppressor(
        detector=FailingDetector(),
        target_speaker=FakeTargetSpeakerSeparator(),
        separator_backend="target_speaker",
    )

    with pytest.raises(ValueError, match="requires target_speaker_reference"):
        suppressor.suppress(audio=np.ones(16, dtype=np.float32), sample_rate=16000)
