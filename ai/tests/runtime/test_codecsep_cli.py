"""Lightweight CLI tests for CodecSep-enabled entry points."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from ai.ai_runtime.audio import recorder_cleaner
from ai.ai_runtime.batch import batch_processor
from ai.scripts.demos import demo_custom_realtime, demo_debug_realtime, demo_realtime


def test_batch_main_builds_codecsep_suppressor(monkeypatch, tmp_path, capsys):
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
                "cleaned_rms": 0.5,
                "rms_reduction_db": -6.0,
                "suppressed_categories": kwargs["suppress_categories"],
                "noise_audio": None,
            }

    monkeypatch.setattr(batch_processor, "SemanticSuppressor", FakeSuppressor)
    monkeypatch.setattr(batch_processor, "BatchProcessor", FakeProcessor)

    batch_processor.main(
        [
            "--input", str(tmp_path / "in.wav"),
            "--output", str(tmp_path / "out.wav"),
            "--suppress", "typing",
            "--separator-backend", "codecsep",
            "--masking-method", "cirm",
            "--codecsep-checkpoint", str(tmp_path / "codecsep_run"),
            "--codecsep-device", "cpu",
            "--codecsep-sfx-prompt", "custom typing prompt",
            "--codecsep-fixed-merge-policy", "sum",
            "--codecsep-negative-prompt", "speech, talking, voice",
            "--codecsep-preserve-prompt", "speech, talking, voice",
        ],
    )

    assert captured["suppressor_kwargs"]["separator_backend"] == "codecsep"
    assert captured["suppressor_kwargs"]["masking_method"] == "cirm"
    assert captured["suppressor_kwargs"]["codecsep_checkpoint_path"] == str(tmp_path / "codecsep_run")
    assert captured["suppressor_kwargs"]["codecsep_device"] == "cpu"
    assert captured["process_kwargs"]["codecsep_prompt_overrides"] == {
        "sfx": ["custom typing prompt"],
    }
    assert captured["process_kwargs"]["codecsep_negative_prompts"] == ["speech, talking, voice"]
    assert captured["process_kwargs"]["codecsep_preserve_prompts"] == ["speech, talking, voice"]
    assert captured["process_kwargs"]["codecsep_mode"] == "fixed_category"
    assert captured["process_kwargs"]["codecsep_query_strategy"] == "single_pass"
    assert captured["process_kwargs"]["codecsep_multistep_steps"] == 0
    assert captured["process_kwargs"]["codecsep_stereo_mode"] == "mono_shared"
    assert captured["process_kwargs"]["codecsep_fixed_merge_policy"] == "sum"
    assert captured["process_kwargs"]["suppress_categories"] == ["typing"]
    assert "Processing Complete" in capsys.readouterr().out


def test_recorder_main_builds_codecsep_profile_and_suppressor(monkeypatch, tmp_path):
    captured: dict = {}

    class FakeProfileManager:
        def __init__(self):
            self.created = None

        def create_profile(self, **kwargs):
            self.created = SimpleNamespace(
                id="temp-profile",
                suppressions=dict(kwargs["suppressions"]),
                suppression_params=dict(kwargs.get("suppression_params") or {}),
            )
            captured["profile_kwargs"] = kwargs
            return self.created

        def delete_profile(self, profile_id):
            captured["deleted_profile_id"] = profile_id
            return True

    class FakeSuppressor:
        def __init__(self, **kwargs):
            captured["suppressor_kwargs"] = kwargs
            self.category_map = {"typing": {"detection_threshold": 0.5}}

        def suppress(self, *args, **kwargs):
            return kwargs["audio"]

    class FakeControlEngine:
        def __init__(self, profile_manager=None, suppressor=None):
            self.profile_manager = profile_manager
            self.suppressor = suppressor
            self.current_profile = None

        def set_profile(self, profile):
            self.current_profile = profile

        def set_mode(self, mode):
            captured["mode"] = mode

    class DummyInputStream:
        def __init__(self, *args, **kwargs):
            captured["input_stream_kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(recorder_cleaner, "ProfileManager", FakeProfileManager)
    monkeypatch.setattr(recorder_cleaner, "SemanticSuppressor", FakeSuppressor)
    monkeypatch.setattr(recorder_cleaner, "ControlEngine", FakeControlEngine)
    monkeypatch.setattr(recorder_cleaner.sd, "InputStream", DummyInputStream)
    monkeypatch.setattr(recorder_cleaner.sd, "query_devices", lambda kind=None: {"max_input_channels": 1})

    recorder_cleaner.main(
        [
            "--duration", "0",
            "--suppress", "typing",
            "--separator-backend", "codecsep",
            "--masking-method", "cirm",
            "--codecsep-checkpoint", str(tmp_path / "codecsep_run"),
            "--codecsep-device", "cpu",
            "--codecsep-sfx-prompt", "custom typing prompt",
            "--codecsep-mode", "audiocaps_native",
            "--codecsep-query-strategy", "single_pass",
            "--codecsep-fixed-merge-policy", "sum",
        ],
    )

    assert captured["suppressor_kwargs"]["separator_backend"] == "codecsep"
    assert captured["suppressor_kwargs"]["masking_method"] == "cirm"
    assert captured["profile_kwargs"]["suppression_params"]["codecsep_checkpoint_path"] == str(tmp_path / "codecsep_run")
    assert captured["profile_kwargs"]["suppression_params"]["codecsep_device"] == "cpu"
    assert captured["profile_kwargs"]["suppression_params"]["codecsep_prompt_overrides"] == {
        "sfx": ["custom typing prompt"],
    }
    assert captured["profile_kwargs"]["suppression_params"]["codecsep_mode"] == "audiocaps_native"
    assert captured["profile_kwargs"]["suppression_params"]["codecsep_query_strategy"] == "single_pass"
    assert captured["profile_kwargs"]["suppression_params"]["codecsep_multistep_steps"] == 0
    assert captured["profile_kwargs"]["suppression_params"]["codecsep_stereo_mode"] == "mono_shared"
    assert captured["profile_kwargs"]["suppression_params"]["codecsep_fixed_merge_policy"] == "sum"
    assert captured["deleted_profile_id"] == "temp-profile"


def test_demo_parsers_accept_codecsep_args():
    custom_args = demo_custom_realtime.build_parser().parse_args(
        ["--separator-backend", "codecsep", "--codecsep-sfx-prompt", "typing"],
    )
    debug_args = demo_debug_realtime.build_parser().parse_args(
        ["--separator-backend", "codecsep", "--codecsep-device", "cpu"],
    )
    realtime_args = demo_realtime.build_parser().parse_args(
        ["--separator-backend", "codecsep", "--codecsep-checkpoint", "C:/tmp/run"],
    )

    assert custom_args.separator_backend == "codecsep"
    assert custom_args.codecsep_sfx_prompt == ["typing"]
    assert custom_args.codecsep_mode == "fixed_category"
    assert custom_args.codecsep_query_strategy == "single_pass"
    assert debug_args.codecsep_device == "cpu"
    assert debug_args.codecsep_multistep_steps == 0
    assert realtime_args.codecsep_checkpoint == "C:/tmp/run"
    assert custom_args.codecsep_fixed_merge_policy == "wiener_mask"


def test_demo_parsers_accept_audiosep15_args():
    custom_args = demo_custom_realtime.build_parser().parse_args(
        [
            "--separator-backend", "audiosep_hive15cat",
            "--audiosep15-model", "C:/tmp/frozensep_hive_15cat.onnx",
            "--audiosep15-realtime-hop", "1.25",
        ],
    )
    debug_args = demo_debug_realtime.build_parser().parse_args(
        ["--separator-backend", "audiosep_hive15cat", "--audiosep15-device", "cpu"],
    )
    realtime_args = demo_realtime.build_parser().parse_args(
        ["--separator-backend", "audiosep_hive15cat", "--audiosep15-realtime-hop", "0.75"],
    )

    assert custom_args.separator_backend == "audiosep_hive15cat"
    assert custom_args.audiosep15_model == "C:/tmp/frozensep_hive_15cat.onnx"
    assert custom_args.audiosep15_realtime_hop == 1.25
    assert debug_args.audiosep15_device == "cpu"
    assert realtime_args.separator_backend == "audiosep_hive15cat"


def test_demo_realtime_rejects_audiosep15_backend():
    with pytest.raises(SystemExit):
        demo_realtime.main(["--separator-backend", "audiosep_hive15cat", "--duration", "0"])


def test_batch_main_builds_audiosep15_suppressor(monkeypatch, tmp_path):
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
                "cleaned_rms": 0.7,
                "rms_reduction_db": -3.0,
                "suppressed_categories": kwargs["suppress_categories"],
                "noise_audio": None,
            }

    monkeypatch.setattr(batch_processor, "SemanticSuppressor", FakeSuppressor)
    monkeypatch.setattr(batch_processor, "BatchProcessor", FakeProcessor)

    batch_processor.main(
        [
            "--input", str(tmp_path / "in.wav"),
            "--output", str(tmp_path / "out.wav"),
            "--suppress", "keyboard typing",
            "--separator-backend", "audiosep_hive15cat",
            "--masking-method", "cirm",
            "--audiosep15-model", str(tmp_path / "frozensep_hive_15cat.onnx"),
            "--audiosep15-device", "cpu",
            "--audiosep15-realtime-hop", "1.25",
        ],
    )

    assert captured["suppressor_kwargs"]["separator_backend"] == "audiosep_hive15cat"
    assert captured["suppressor_kwargs"]["masking_method"] == "cirm"
    assert captured["suppressor_kwargs"]["audiosep_hive15cat_model_path"] == str(
        tmp_path / "frozensep_hive_15cat.onnx"
    )
    assert captured["suppressor_kwargs"]["audiosep_hive15cat_device"] == "cpu"
    assert captured["process_kwargs"]["audiosep_hive15cat_realtime_hop_seconds"] == 1.25
    assert captured["process_kwargs"]["suppress_categories"] == ["keyboard typing"]


def test_recorder_main_builds_audiosep15_profile_and_suppressor(monkeypatch, tmp_path):
    captured: dict = {}

    class FakeProfileManager:
        def __init__(self):
            self.created = None

        def create_profile(self, **kwargs):
            self.created = SimpleNamespace(
                id="temp-profile",
                suppressions=dict(kwargs["suppressions"]),
                suppression_params=dict(kwargs.get("suppression_params") or {}),
            )
            captured["profile_kwargs"] = kwargs
            return self.created

        def delete_profile(self, profile_id):
            captured["deleted_profile_id"] = profile_id
            return True

    class FakeSuppressor:
        def __init__(self, **kwargs):
            captured["suppressor_kwargs"] = kwargs
            self.category_map = {"keyboard typing": {"detection_threshold": -1}}

        def suppress(self, *args, **kwargs):
            return kwargs["audio"]

    class FakeControlEngine:
        def __init__(self, profile_manager=None, suppressor=None):
            self.profile_manager = profile_manager
            self.suppressor = suppressor
            self.current_profile = None

        def set_profile(self, profile):
            self.current_profile = profile

        def set_mode(self, mode):
            captured["mode"] = mode

    class DummyInputStream:
        def __init__(self, *args, **kwargs):
            captured["input_stream_kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(recorder_cleaner, "ProfileManager", FakeProfileManager)
    monkeypatch.setattr(recorder_cleaner, "SemanticSuppressor", FakeSuppressor)
    monkeypatch.setattr(recorder_cleaner, "ControlEngine", FakeControlEngine)
    monkeypatch.setattr(recorder_cleaner.sd, "InputStream", DummyInputStream)
    monkeypatch.setattr(recorder_cleaner.sd, "query_devices", lambda kind=None: {"max_input_channels": 1})

    recorder_cleaner.main(
        [
            "--duration", "0",
            "--suppress", "keyboard typing",
            "--separator-backend", "audiosep_hive15cat",
            "--masking-method", "cirm",
            "--audiosep15-model", str(tmp_path / "frozensep_hive_15cat.onnx"),
            "--audiosep15-device", "cpu",
            "--audiosep15-realtime-hop", "1.25",
        ],
    )

    assert captured["suppressor_kwargs"]["separator_backend"] == "audiosep_hive15cat"
    assert captured["suppressor_kwargs"]["masking_method"] == "cirm"
    assert captured["suppressor_kwargs"]["audiosep_hive15cat_model_path"] == str(
        tmp_path / "frozensep_hive_15cat.onnx"
    )
    assert captured["suppressor_kwargs"]["audiosep_hive15cat_device"] == "cpu"
    assert captured["profile_kwargs"]["suppression_params"]["audiosep_hive15cat_model_path"] == str(
        tmp_path / "frozensep_hive_15cat.onnx"
    )
    assert captured["profile_kwargs"]["suppression_params"]["audiosep_hive15cat_device"] == "cpu"
    assert (
        captured["profile_kwargs"]["suppression_params"]["audiosep_hive15cat_realtime_hop_seconds"]
        == 1.25
    )
    assert captured["deleted_profile_id"] == "temp-profile"


def test_batch_main_accepts_explicit_codecsep_product_target_without_suppress(monkeypatch, tmp_path):
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
                "cleaned_rms": 0.75,
                "rms_reduction_db": -2.5,
                "suppressed_categories": kwargs["suppress_categories"],
                "noise_audio": None,
            }

    monkeypatch.setattr(batch_processor, "SemanticSuppressor", FakeSuppressor)
    monkeypatch.setattr(batch_processor, "BatchProcessor", FakeProcessor)

    batch_processor.main(
        [
            "--input", str(tmp_path / "in.wav"),
            "--output", str(tmp_path / "out.wav"),
            "--separator-backend", "codecsep",
            "--codecsep-product-category", "dog_barking",
            "--codecsep-fixed-merge-policy", "sum",
        ],
    )

    assert captured["process_kwargs"]["suppress_categories"] == []
    assert captured["process_kwargs"]["codecsep_product_categories"] == ["dog_barking"]
    assert captured["process_kwargs"]["codecsep_fixed_merge_policy"] == "sum"

def test_batch_processor_processes_stereo_codecsep_mono_shared_by_default(monkeypatch, tmp_path):
    calls: list[np.ndarray] = []
    written: dict = {}

    class FakeSuppressor:
        separator_backend = "codecsep"

        def suppress(self, **kwargs):
            audio = np.asarray(kwargs["audio"], dtype=np.float32)
            calls.append(audio.copy())
            removed = audio * 0.25
            if kwargs.get("return_details"):
                return {"clean_audio": audio - removed, "removed_audio": removed}
            return audio - removed

    stereo = np.column_stack(
        [
            np.linspace(-1.0, 1.0, 16, dtype=np.float32),
            np.linspace(1.0, -1.0, 16, dtype=np.float32),
        ],
    )

    monkeypatch.setattr(batch_processor.sf, "read", lambda *_args, **_kwargs: (stereo, 16000))

    def fake_write(path, data, sample_rate):
        written["path"] = path
        written["data"] = np.asarray(data)
        written["sample_rate"] = sample_rate

    monkeypatch.setattr(batch_processor.sf, "write", fake_write)

    processor = batch_processor.BatchProcessor(suppressor=FakeSuppressor())
    processor.process_file(
        input_path=tmp_path / "in.wav",
        output_path=tmp_path / "out.wav",
        suppress_categories=["pets"],
    )

    assert len(calls) == 1
    np.testing.assert_allclose(calls[0], stereo.mean(axis=1))
    assert written["data"].shape == stereo.shape


def test_batch_processor_supports_codecsep_per_channel_override(monkeypatch, tmp_path):
    calls: list[np.ndarray] = []

    class FakeSuppressor:
        separator_backend = "codecsep"

        def suppress(self, **kwargs):
            audio = np.asarray(kwargs["audio"], dtype=np.float32)
            calls.append(audio.copy())
            return audio * 0.5

    stereo = np.column_stack(
        [
            np.linspace(-1.0, 1.0, 16, dtype=np.float32),
            np.linspace(1.0, -1.0, 16, dtype=np.float32),
        ],
    )

    monkeypatch.setattr(batch_processor.sf, "read", lambda *_args, **_kwargs: (stereo, 16000))
    monkeypatch.setattr(batch_processor.sf, "write", lambda *_args, **_kwargs: None)

    processor = batch_processor.BatchProcessor(suppressor=FakeSuppressor())
    processor.process_file(
        input_path=tmp_path / "in.wav",
        output_path=tmp_path / "out.wav",
        suppress_categories=["pets"],
        codecsep_stereo_mode="per_channel",
    )

    assert len(calls) == 2
    np.testing.assert_allclose(calls[0], stereo[:, 0])
    np.testing.assert_allclose(calls[1], stereo[:, 1])
