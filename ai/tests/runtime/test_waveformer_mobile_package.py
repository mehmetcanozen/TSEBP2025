import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PACKAGE_PATH = ROOT / "ai" / "models" / "Waveformer" / "model_package.json"


def test_waveformer_android_uses_validated_streaming_contract():
    package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
    desktop = package["platforms"]["desktop"]
    android = package["platforms"]["android"]

    assert android["runtime_kind"] == "onnx_streaming_target_extractor"
    assert desktop["artifact"].endswith(
        "../Exports/Waveformer/waveformer_edge_100ms/desktop/semantic_hearing_100ms_desktop.onnx"
    )
    assert android["artifact"].endswith(
        "../Exports/Waveformer/waveformer_edge_100ms/android/model_fixed.ort"
    )
    assert android["sample_rate"] == 44_100
    assert android["chunk_samples"] == 4_416
    assert android["mix_channels"] == 2
    assert android["state_tensors"] == desktop["state_tensors"]
    assert "required_operators.config" in android["metadata_artifacts"][-1]


def test_waveformer_android_metadata_names_match_export_contract():
    package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
    android = package["platforms"]["android"]
    metadata_path = PACKAGE_PATH.parent / android["metadata_artifacts"][0]
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert (PACKAGE_PATH.parent / android["artifact"]).exists()
    assert (PACKAGE_PATH.parent / android["metadata_artifacts"][-1]).exists()
    assert metadata["sample_rate"] == android["sample_rate"]
    assert metadata["chunk_samples"] == android["chunk_samples"]
    assert metadata["format"] == "ort"
    assert [item["name"] for item in metadata["inputs"]] == [
        "mixture",
        "label_vector",
        "enc_buf",
        "dec_buf",
        "out_buf",
    ]
    assert [item["name"] for item in metadata["outputs"]] == [
        "target_chunk",
        "enc_buf_out",
        "dec_buf_out",
        "out_buf_out",
    ]
    assert metadata["inputs"][0]["shape"] == [
        1,
        android["mix_channels"],
        android["chunk_samples"],
    ]
