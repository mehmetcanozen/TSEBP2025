"""ControlEngine tests for CodecSep-related suppression params."""

from __future__ import annotations

import numpy as np

from ai.ai_runtime.profiles import ControlEngine, ProfileManager


class CaptureSuppressor:
    def __init__(self):
        self.calls: list[dict] = []

    def suppress(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs["audio"]


def test_control_engine_forwards_codecsep_suppression_params(tmp_path):
    manager = ProfileManager(profiles_dir=tmp_path / "profiles")
    profile = manager.create_profile(
        name="CodecSep Profile",
        suppressions={"typing": True},
        suppression_params={
            "separator_backend": "codecsep",
            "masking_method": "cirm",
            "detection_threshold": -1,
            "aggressiveness": 1.8,
            "codecsep_checkpoint_path": "C:/tmp/codecsep",
            "codecsep_device": "cpu",
            "codecsep_prompt_overrides": {"sfx": ["keyboard typing"]},
            "codecsep_negative_prompts": ["speech, talking, voice"],
            "codecsep_preserve_prompts": ["speech, talking, voice"],
            "codecsep_mode": "audiocaps_native",
            "codecsep_query_strategy": "single_pass",
            "codecsep_multistep_steps": 0,
            "codecsep_stereo_mode": "mono_shared",
            "codecsep_fixed_merge_policy": "sum",
        },
    )
    suppressor = CaptureSuppressor()
    engine = ControlEngine(profile_manager=manager, suppressor=suppressor)
    engine.set_profile(profile)

    audio = np.zeros(1600, dtype=np.float32)
    out = engine.process_audio(audio, 16000)

    assert np.array_equal(out, audio)
    assert len(suppressor.calls) == 1
    call = suppressor.calls[0]
    assert call["suppress_categories"] == ["typing"]
    assert call["separator_backend"] == "codecsep"
    assert call["masking_method"] == "cirm"
    assert call["codecsep_checkpoint_path"] == "C:/tmp/codecsep"
    assert call["codecsep_device"] == "cpu"
    assert call["codecsep_prompt_overrides"] == {"sfx": ["keyboard typing"]}
    assert call["codecsep_negative_prompts"] == ["speech, talking, voice"]
    assert call["codecsep_preserve_prompts"] == ["speech, talking, voice"]
    assert call["codecsep_mode"] == "audiocaps_native"
    assert call["codecsep_query_strategy"] == "single_pass"
    assert call["codecsep_multistep_steps"] == 0
    assert call["codecsep_stereo_mode"] == "mono_shared"
    assert call["codecsep_fixed_merge_policy"] == "sum"


def test_control_engine_forwards_audiosep_hive15cat_suppression_params(tmp_path):
    manager = ProfileManager(profiles_dir=tmp_path / "profiles")
    profile = manager.create_profile(
        name="AudioSep15 Profile",
        suppressions={"keyboard typing": True},
        suppression_params={
            "separator_backend": "audiosep_hive15cat",
            "masking_method": "cirm",
            "detection_threshold": -1,
            "aggressiveness": 1.9,
            "audiosep_hive15cat_model_path": "C:/tmp/frozensep_hive_15cat.onnx",
            "audiosep_hive15cat_device": "cpu",
            "audiosep_hive15cat_realtime_hop_seconds": 1.25,
        },
    )
    suppressor = CaptureSuppressor()
    engine = ControlEngine(profile_manager=manager, suppressor=suppressor)
    engine.set_profile(profile)

    audio = np.zeros(1600, dtype=np.float32)
    out = engine.process_audio(audio, 16000)

    assert np.array_equal(out, audio)
    assert len(suppressor.calls) == 1
    call = suppressor.calls[0]
    assert call["suppress_categories"] == ["keyboard typing"]
    assert call["separator_backend"] == "audiosep_hive15cat"
    assert call["masking_method"] == "cirm"
    assert call["audiosep_hive15cat_model_path"] == "C:/tmp/frozensep_hive_15cat.onnx"
    assert call["audiosep_hive15cat_device"] == "cpu"
    assert call["audiosep_hive15cat_realtime_hop_seconds"] == 1.25
