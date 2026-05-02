import numpy as np
import pytest

from ai.ai_runtime.separation.waveformer_onnx_stream import (
    WaveformerOnnxStream,
    load_package,
)


def test_waveformer_onnx_package_contract_matches_manifest():
    package = load_package()
    assert package.model_path.name == "semantic_hearing_100ms_windows.onnx"
    assert package.sample_rate == 44_100
    assert package.chunk_samples == 4_416
    assert package.mix_channels == 2
    assert "dog" in package.categories
    assert package.state_tensors["enc_buf"] == (1, 256, 2046)


def test_waveformer_onnx_two_step_smoke_if_onnxruntime_available():
    pytest.importorskip("onnxruntime")
    runner = WaveformerOnnxStream()
    audit = runner.audit_contract(check_onnx=False)
    assert audit["ok"], audit["errors"]
    smoke = runner.smoke_two_step("dog")
    assert smoke["ok"]
    assert smoke["target_chunk_shape"] == [runner.package.chunk_samples]


def test_waveformer_onnx_suppression_keeps_length_if_onnxruntime_available():
    pytest.importorskip("onnxruntime")
    runner = WaveformerOnnxStream()
    audio = np.zeros((runner.package.sample_rate // 10,), dtype=np.float32)
    clean, stats = runner.suppress(audio, runner.package.sample_rate, ["dog"], 1.1)
    assert clean.shape == audio.shape
    assert stats["real_time_factor"] >= 0.0
    assert np.all(np.isfinite(clean))
