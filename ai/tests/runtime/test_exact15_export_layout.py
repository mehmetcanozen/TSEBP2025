from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_package(name: str) -> dict:
    package_path = PROJECT_ROOT / "ai" / "models" / name / "model_package.json"
    return json.loads(package_path.read_text(encoding="utf-8"))


def test_audiosep_hive15cat_package_uses_canonical_exports_root() -> None:
    package = _load_package("AudioSepHive15Cat")
    root = "../Exports/AudioSepHive15Cat/audiosep_hive15cat_exact15/shared"

    for platform_name in ("desktop", "android"):
        platform = package["platforms"][platform_name]
        assert platform["artifact"] == f"{root}/frozensep_hive_15cat.onnx"
        assert platform["metadata_artifacts"] == [
            f"{root}/categories_15.txt",
            f"{root}/categories_15.yaml",
        ]

    serialized = json.dumps(package)
    assert '"artifact": "frozensep_hive_15cat.onnx"' not in serialized


def test_codecsep_dnrv2_15cat_package_uses_canonical_exports_root() -> None:
    package = _load_package("CodecSepDNRv2_15Cat")
    root = "../Exports/CodecSepDNRv2_15Cat/codecsep_dnrv2_15cat_exact15"

    desktop = package["platforms"]["desktop"]
    assert desktop["artifact"] == f"{root}/desktop/codecsep_dnrv2_15cat.onnx"
    assert desktop["metadata_artifacts"] == [
        f"{root}/shared/categories_15.txt",
        f"{root}/shared/categories_15.yaml",
        f"{root}/source/freeze_manifest.json",
        f"{root}/desktop/codecsep_dnrv2_15cat.onnx.json",
    ]

    android = package["platforms"]["android"]
    assert android["artifact"] == f"{root}/android/codecsep_dnrv2_15cat.pte"
    assert android["metadata_artifacts"] == [
        f"{root}/shared/categories_15.txt",
        f"{root}/shared/categories_15.yaml",
        f"{root}/source/freeze_manifest.json",
        f"{root}/android/codecsep_dnrv2_15cat.pte.json",
    ]

    serialized = json.dumps(package)
    assert '"artifact": "codecsep_dnrv2_15cat.onnx"' not in serialized
    assert '"artifact": "codecsep_dnrv2_15cat.pte"' not in serialized


def test_exact15_runtime_helpers_point_at_exports_root() -> None:
    from ai.ai_runtime.utils.paths import (
        get_audiosep_hive15cat_categories_path,
        get_audiosep_hive15cat_onnx_path,
        get_clapsep_hive15cat_onnx_path,
        get_codecsep_dnrv2_15cat_categories_path,
        get_codecsep_dnrv2_15cat_executorch_path,
        get_codecsep_dnrv2_15cat_freeze_spec_path,
        get_codecsep_dnrv2_15cat_onnx_path,
        get_model_exports_path,
    )

    exports_root = get_model_exports_path()
    paths = (
        get_audiosep_hive15cat_onnx_path(),
        get_audiosep_hive15cat_categories_path(),
        get_codecsep_dnrv2_15cat_onnx_path(),
        get_codecsep_dnrv2_15cat_executorch_path(),
        get_codecsep_dnrv2_15cat_categories_path(),
        get_codecsep_dnrv2_15cat_freeze_spec_path(),
        get_clapsep_hive15cat_onnx_path(),
    )

    for path in paths:
        assert path.is_relative_to(exports_root)

    assert get_audiosep_hive15cat_onnx_path().parts[-4:] == (
        "AudioSepHive15Cat",
        "audiosep_hive15cat_exact15",
        "shared",
        "frozensep_hive_15cat.onnx",
    )
    assert get_codecsep_dnrv2_15cat_onnx_path().parts[-4:] == (
        "CodecSepDNRv2_15Cat",
        "codecsep_dnrv2_15cat_exact15",
        "desktop",
        "codecsep_dnrv2_15cat.onnx",
    )
    assert get_codecsep_dnrv2_15cat_executorch_path().parts[-4:] == (
        "CodecSepDNRv2_15Cat",
        "codecsep_dnrv2_15cat_exact15",
        "android",
        "codecsep_dnrv2_15cat.pte",
    )


def test_codecsep_exporter_defaults_stay_out_of_package_manifest_folder() -> None:
    from ai.export import export_codecsep_dnrv2_15cat_pte_only
    from ai.export import freeze_codecsep_dnrv2_15cat
    from ai.ai_runtime.utils.paths import (
        get_codecsep_dnrv2_15cat_executorch_path,
        get_codecsep_dnrv2_15cat_freeze_spec_path,
        get_codecsep_dnrv2_15cat_frozen_checkpoint_path,
        get_codecsep_dnrv2_15cat_model_path,
        get_codecsep_dnrv2_15cat_onnx_path,
    )

    artifacts = freeze_codecsep_dnrv2_15cat.resolve_artifact_paths(
        get_codecsep_dnrv2_15cat_model_path()
    )
    assert artifacts.package_dir == get_codecsep_dnrv2_15cat_model_path()
    assert artifacts.onnx_path == get_codecsep_dnrv2_15cat_onnx_path()
    assert artifacts.executorch_path == get_codecsep_dnrv2_15cat_executorch_path()
    assert artifacts.freeze_spec_yaml == get_codecsep_dnrv2_15cat_freeze_spec_path()
    assert artifacts.frozen_checkpoint_path == get_codecsep_dnrv2_15cat_frozen_checkpoint_path()

    parser = export_codecsep_dnrv2_15cat_pte_only.build_arg_parser()
    args = parser.parse_args([])
    assert Path(args.executorch_output) == get_codecsep_dnrv2_15cat_executorch_path()
