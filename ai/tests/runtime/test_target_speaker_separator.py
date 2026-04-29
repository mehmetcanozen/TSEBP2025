from __future__ import annotations

import numpy as np

from ai.ai_runtime.separation.target_speaker_separator import TargetSpeakerSeparator


def test_target_speaker_separator_preserves_stereo_layout(monkeypatch):
    separator = TargetSpeakerSeparator(device="cpu", engine="tsextract")
    separator.sample_rate = 8
    captured: dict[str, np.ndarray] = {}

    def fake_run_model(mixture_model_sr, reference_model_sr):
        captured["mixture"] = np.asarray(mixture_model_sr, dtype=np.float32)
        captured["reference"] = np.asarray(reference_model_sr, dtype=np.float32)
        return np.asarray(mixture_model_sr, dtype=np.float32) * 0.25, (1, 2)

    monkeypatch.setattr(separator, "_run_model", fake_run_model)

    audio = np.column_stack(
        [
            np.linspace(-1.0, 1.0, 16, dtype=np.float32),
            np.linspace(1.0, -1.0, 16, dtype=np.float32),
        ],
    )
    reference = np.linspace(-0.5, 0.5, 8, dtype=np.float32)

    result = separator.extract_with_details(
        audio=audio,
        sample_rate=16,
        reference_audio=reference,
        reference_sample_rate=8,
    )

    assert captured["mixture"].shape == (8,)
    assert captured["reference"].shape == (8,)
    assert result.audio.shape == audio.shape
    assert result.sample_rate == 16
    assert result.model_sample_rate == 8
    assert result.engine == "tsextract"
    assert result.speaker_logits_shape == (1, 2)
    np.testing.assert_allclose(result.audio[:, 0], result.audio[:, 1], atol=1e-6)


def test_target_speaker_separator_preserves_mono_length(monkeypatch):
    separator = TargetSpeakerSeparator(device="cpu", engine="tsextract")
    separator.sample_rate = 8
    monkeypatch.setattr(
        separator,
        "_run_model",
        lambda mixture_model_sr, _reference_model_sr: (
            np.ones_like(mixture_model_sr, dtype=np.float32) * 0.2,
            None,
        ),
    )

    audio = np.zeros(17, dtype=np.float32)
    reference = np.ones(5, dtype=np.float32)

    output = separator.extract(
        audio=audio,
        sample_rate=16,
        reference_audio=reference,
        reference_sample_rate=8,
    )

    assert output.shape == audio.shape
    assert output.dtype == np.float32


def test_target_speaker_separator_clearvoice_alias_uses_native_pipeline(monkeypatch):
    separator = TargetSpeakerSeparator(device="cpu", engine="quality")
    captured: dict[str, object] = {}

    def fake_run_clearvoice(**kwargs):
        captured.update(kwargs)
        return np.ones(8, dtype=np.float32) * 0.1, 8

    monkeypatch.setattr(separator, "_run_clearvoice", fake_run_clearvoice)

    audio = np.zeros(16, dtype=np.float32)
    output = separator.extract(
        audio=audio,
        sample_rate=16,
        reference_path="speaker.wav",
    )

    assert separator.engine == "clearvoice"
    assert captured["reference_path"] == "speaker.wav"
    assert output.shape == audio.shape
    assert output.dtype == np.float32
