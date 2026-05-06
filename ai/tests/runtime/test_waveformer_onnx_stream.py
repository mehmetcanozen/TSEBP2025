import numpy as np
import pytest

from ai.ai_runtime.separation.waveformer_onnx_stream import (
    WaveformerOnnxStream,
    load_package,
)


def test_waveformer_onnx_package_contract_matches_manifest():
    from ai.ai_runtime.utils.paths import (
        get_waveformer_android_ort_path,
        get_waveformer_android_required_operators_path,
        get_waveformer_desktop_metadata_path,
        get_waveformer_desktop_onnx_path,
        get_waveformer_export_root_path,
        get_waveformer_source_onnx_path,
    )

    package = load_package()
    assert package.model_path == get_waveformer_desktop_onnx_path()
    assert package.metadata_paths == (get_waveformer_desktop_metadata_path(),)
    assert get_waveformer_source_onnx_path().parent == get_waveformer_export_root_path() / "source"
    assert get_waveformer_android_ort_path() == (
        get_waveformer_export_root_path() / "android" / "model_fixed.ort"
    )
    assert get_waveformer_android_required_operators_path().name == "required_operators.config"
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
