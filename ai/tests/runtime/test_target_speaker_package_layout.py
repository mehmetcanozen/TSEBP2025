from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_target_speaker_model_package_uses_canonical_export_root() -> None:
    package_path = PROJECT_ROOT / "ai" / "models" / "TargetSpeakerWindows" / "model_package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))

    root = "../Exports/TargetSpeakerWindows/target_speaker_windows_desktop"
    desktop = package["platforms"]["desktop"]

    assert desktop["artifact"] == f"{root}/desktop/windows_bundle_manifest.json"
    assert desktop["metadata_artifacts"] == [
        f"{root}/desktop/tsextract_onnx/tsextract_fp32.manifest.json",
        f"{root}/desktop/tsextract_onnx/tsextract_fp32.validation.json",
        f"{root}/desktop/clearvoice_native/manifest.json",
    ]
    assert package["validation_summary"]["validation_artifact"] == (
        f"{root}/desktop/tsextract_onnx/tsextract_fp32.validation.json"
    )

    serialized = json.dumps(package)
    assert "../Exports/" + "target_speaker_windows" not in serialized
    assert "windows_bundle" + "_slim" not in serialized
    assert "clearvoice_native" + "_slim" not in serialized


def test_target_speaker_exporter_defaults_stay_out_of_speaker_separator() -> None:
    from ai.export import export_target_speaker_windows as exporter

    expected_root = (
        exporter.AI_ROOT
        / "models"
        / "Exports"
        / "TargetSpeakerWindows"
        / "target_speaker_windows_desktop"
    )
    assert exporter.DEFAULT_EXPORT_ROOT == expected_root
    assert exporter.DEFAULT_SOURCE_TSEXTRACT_ONNX == expected_root / "source" / "tsextract_fp32.onnx"
    assert exporter.DEFAULT_DESKTOP_BUNDLE == expected_root / "desktop"
    assert exporter.DEFAULT_CLEARVOICE_BUNDLE == expected_root / "desktop" / "clearvoice_native"

    assert "SpeakerSeperator" not in str(exporter.DEFAULT_EXPORT_ROOT)
    assert "windows_bundle" + "_slim" not in str(exporter.DEFAULT_DESKTOP_BUNDLE)


def test_target_speaker_runtime_defaults_use_canonical_export_root() -> None:
    from ai.ai_runtime.separation import exported_target_speaker
    from ai.ai_runtime.separation import target_speaker_separator
    from ai.ai_runtime.utils.paths import (
        get_target_speaker_clearvoice_bundle_path,
        get_target_speaker_tsextract_desktop_onnx_path,
        get_target_speaker_tsextract_source_onnx_path,
        get_target_speaker_windows_export_root_path,
    )

    assert (
        target_speaker_separator.DEFAULT_TARGET_SPEAKER_EXPORT_ROOT
        == get_target_speaker_windows_export_root_path()
    )
    assert (
        target_speaker_separator.DEFAULT_TSEXTRACT_ONNX
        == get_target_speaker_tsextract_source_onnx_path()
    )
    assert (
        target_speaker_separator.DEFAULT_TSEXTRACT_BUNDLE_ONNX
        == get_target_speaker_tsextract_desktop_onnx_path()
    )
    assert (
        target_speaker_separator.DEFAULT_CLEARVOICE_BUNDLE
        == get_target_speaker_clearvoice_bundle_path()
    )
    assert exported_target_speaker.DEFAULT_EXPORT_ROOT == get_target_speaker_windows_export_root_path()
    assert exported_target_speaker.DEFAULT_TSEXTRACT_BUNDLE_ONNX == (
        get_target_speaker_tsextract_desktop_onnx_path()
    )

    runtime_files = (
        PROJECT_ROOT / "ai" / "ai_runtime" / "separation" / "target_speaker_separator.py",
        PROJECT_ROOT / "ai" / "ai_runtime" / "separation" / "exported_target_speaker.py",
        PROJECT_ROOT / "ai" / "ai_runtime" / "utils" / "paths.py",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in runtime_files)

    canonical_root = get_target_speaker_windows_export_root_path()
    assert canonical_root.parts[-3:] == (
        "Exports",
        "TargetSpeakerWindows",
        "target_speaker_windows_desktop",
    )
    assert 'AI_ROOT / "models" / "exports"' not in combined
    assert "windows_bundle" + "_slim" not in combined
    assert "Exports/" + "target_speaker_windows" not in combined


def test_target_speaker_default_engine_is_packaged_tsextract_onnx() -> None:
    from ai.ai_runtime.utils.target_speaker import DEFAULT_TARGET_SPEAKER_ENGINE

    assert DEFAULT_TARGET_SPEAKER_ENGINE == "tsextract_onnx"
