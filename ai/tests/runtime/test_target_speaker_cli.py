from __future__ import annotations

import numpy as np

from ai.ai_runtime.batch import batch_processor


def test_batch_main_builds_target_speaker_suppressor(monkeypatch, tmp_path):
    captured: dict = {}

    class FakeSuppressor:
        def __init__(self, **kwargs):
            captured["suppressor_kwargs"] = kwargs

    class FakeProcessor:
        def __init__(self, suppressor=None):
            captured["processor_suppressor"] = suppressor

        def process_file(self, **kwargs):
            captured["process_kwargs"] = kwargs
            return {
                "input_file": str(kwargs["input_path"]),
                "output_file": str(kwargs["output_path"]),
                "sample_rate": 16000,
                "duration_seconds": 1.0,
                "original_rms": 1.0,
                "cleaned_rms": 0.6,
                "rms_reduction_db": -4.4,
                "suppressed_categories": kwargs["suppress_categories"],
                "noise_audio": None,
            }

    monkeypatch.setattr(batch_processor, "SemanticSuppressor", FakeSuppressor)
    monkeypatch.setattr(batch_processor, "BatchProcessor", FakeProcessor)

    reference = tmp_path / "person.wav"
    batch_processor.main(
        [
            "--input",
            str(tmp_path / "mix.wav"),
            "--output",
            str(tmp_path / "clean.wav"),
            "--target-speaker-reference",
            str(reference),
            "--target-speaker-device",
            "cpu",
            "--target-speaker-engine",
            "tsextractt",
            "--target-speaker-scale",
            "0.9",
        ],
    )

    assert captured["suppressor_kwargs"]["separator_backend"] == "target_speaker"
    assert captured["suppressor_kwargs"]["target_speaker_device"] == "cpu"
    assert captured["suppressor_kwargs"]["target_speaker_engine"] == "tsextract"
    assert captured["process_kwargs"]["target_speaker_reference_path"] == str(reference)
    assert captured["process_kwargs"]["target_speaker_device"] == "cpu"
    assert captured["process_kwargs"]["target_speaker_engine"] == "tsextract"
    assert captured["process_kwargs"]["target_speaker_reconstruction"] == "direct_subtract"
    assert captured["process_kwargs"]["target_speaker_scale"] == 0.9
    assert captured["process_kwargs"]["suppress_categories"] == []


def test_batch_processor_target_speaker_uses_full_file_inference(monkeypatch, tmp_path):
    calls: list[np.ndarray] = []
    audio = np.linspace(-0.5, 0.5, 16000, dtype=np.float32)

    class FakeSuppressor:
        separator_backend = "target_speaker"

        def suppress(self, **kwargs):
            captured = np.asarray(kwargs["audio"], dtype=np.float32)
            calls.append(captured.copy())
            return captured * 0.5

    monkeypatch.setattr(batch_processor.sf, "read", lambda *_args, **_kwargs: (audio, 16000))
    monkeypatch.setattr(batch_processor.sf, "write", lambda *_args, **_kwargs: None)

    processor = batch_processor.BatchProcessor(suppressor=FakeSuppressor())
    processor.process_file(
        input_path=tmp_path / "mix.wav",
        output_path=tmp_path / "clean.wav",
        suppress_categories=[],
        chunk_size_seconds=0.1,
        target_speaker_reference_path=str(tmp_path / "speaker.wav"),
    )

    assert len(calls) == 1
    assert calls[0].shape == audio.shape
