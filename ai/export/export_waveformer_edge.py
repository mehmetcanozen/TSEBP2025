"""Package the validated Waveformer 100 ms edge export.

This is the current Waveformer deployment packager. It does not retrace the
model from the checkpoint; the existing validated streaming ONNX is treated as
the source of truth, then copied into the canonical Exports tree and optimized
for the desktop and Android runtimes.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_ROOT = PROJECT_ROOT / "ai" / "models"
WAVEFORMER_ROOT = MODELS_ROOT / "Waveformer"
PACKAGE_PATH = WAVEFORMER_ROOT / "model_package.json"
DEFAULT_OUT_ROOT = MODELS_ROOT / "Exports" / "Waveformer" / "waveformer_edge_100ms"
DEFAULT_CANONICAL_SOURCE_ONNX = DEFAULT_OUT_ROOT / "source" / "semantic_hearing_100ms_source.onnx"
DEFAULT_ANDROID_BUILD_CACHE_ONNX = (
    PROJECT_ROOT
    / "mobile-part"
    / "android"
    / "app"
    / "build"
    / "intermediates"
    / "assets"
    / "debug"
    / "mergeDebugAssets"
    / "suppression-model-bundle"
    / "semantic_hearing_100ms_windows.onnx"
)

MODEL_ID = "waveformer_edge_100ms"
RUNTIME_KIND = "onnx_streaming_target_extractor"
DESKTOP_ARTIFACT_RELATIVE = (
    "../Exports/Waveformer/waveformer_edge_100ms/desktop/"
    "semantic_hearing_100ms_desktop.onnx"
)
DESKTOP_METADATA_RELATIVE = (
    "../Exports/Waveformer/waveformer_edge_100ms/desktop/"
    "semantic_hearing_100ms_desktop.onnx.json"
)
ANDROID_ARTIFACT_RELATIVE = "../Exports/Waveformer/waveformer_edge_100ms/android/model_fixed.ort"
ANDROID_METADATA_RELATIVE = "../Exports/Waveformer/waveformer_edge_100ms/android/model_fixed.ort.json"
ANDROID_REQUIRED_OPS_RELATIVE = (
    "../Exports/Waveformer/waveformer_edge_100ms/android/required_operators.config"
)

INPUT_NAMES = ("mixture", "label_vector", "enc_buf", "dec_buf", "out_buf")
OUTPUT_NAMES = ("target_chunk", "enc_buf_out", "dec_buf_out", "out_buf_out")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_file_over(src: Path, dst: Path) -> None:
    """Overwrite dst contents without deleting the existing path first."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as source, dst.open("wb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def remove_file_best_effort(path: Path) -> None:
    for _ in range(5):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            gc.collect()
            time.sleep(0.1)


def remove_tree_best_effort(path: Path) -> None:
    def onerror(func: Any, failing_path: str, _exc_info: object) -> None:
        try:
            os.chmod(failing_path, stat.S_IWRITE)
        except OSError:
            pass
        try:
            func(failing_path)
        except OSError:
            pass

    for _ in range(5):
        if not path.exists():
            return
        try:
            shutil.rmtree(path, onerror=onerror)
            return
        except PermissionError:
            gc.collect()
            time.sleep(0.1)


def infer_metadata_path(onnx_path: Path) -> Path:
    return onnx_path.with_suffix(".onnx.json")


def resolve_source_paths(
    explicit_source_onnx: Path | None,
    explicit_source_metadata: Path | None,
    out_root: Path,
) -> tuple[Path, Path | None]:
    if explicit_source_onnx is not None:
        source_onnx = explicit_source_onnx.resolve()
        if not source_onnx.exists():
            raise SystemExit(f"Source ONNX does not exist: {source_onnx}")
    else:
        candidates = (
            out_root / "source" / "semantic_hearing_100ms_source.onnx",
            DEFAULT_ANDROID_BUILD_CACHE_ONNX,
        )
        source_onnx = next((path.resolve() for path in candidates if path.exists()), None)
        if source_onnx is None:
            lines = "\n".join(f"  - {path.resolve()}" for path in candidates)
            raise SystemExit(
                "No Waveformer source ONNX was found. Expected one of:\n"
                f"{lines}\n"
                "Restore one trusted 100 ms ONNX and pass it with --source-onnx."
            )

    if explicit_source_metadata is not None:
        source_metadata_path = explicit_source_metadata.resolve()
        if not source_metadata_path.exists():
            raise SystemExit(f"Source metadata does not exist: {source_metadata_path}")
    else:
        inferred = infer_metadata_path(source_onnx)
        source_metadata_path = inferred.resolve() if inferred.exists() else None

    return source_onnx, source_metadata_path


def expected_contract(package: dict[str, Any], platform_name: str = "desktop") -> dict[str, Any]:
    platform = package["platforms"][platform_name]
    categories = [item["id"] for item in package["categories"]]
    chunk_samples = int(platform["chunk_samples"])
    mix_channels = int(platform.get("mix_channels", 1))
    state_tensors = {
        name: [int(value) for value in shape]
        for name, shape in platform["state_tensors"].items()
    }
    return {
        "runtime_kind": platform["runtime_kind"],
        "sample_rate": int(platform["sample_rate"]),
        "chunk_samples": chunk_samples,
        "chunk_ms": chunk_samples / float(platform["sample_rate"]) * 1000.0,
        "mix_channels": mix_channels,
        "categories": categories,
        "state_tensors": state_tensors,
        "inputs": {
            "mixture": [1, mix_channels, chunk_samples],
            "label_vector": [1, len(categories)],
            "enc_buf": state_tensors["enc_buf"],
            "dec_buf": state_tensors["dec_buf"],
            "out_buf": state_tensors["out_buf"],
        },
        "outputs": list(OUTPUT_NAMES),
    }


def shape_values(shape: list[Any] | tuple[Any, ...]) -> list[Any]:
    values: list[Any] = []
    for value in shape:
        values.append(int(value) if isinstance(value, int) else value)
    return values


def read_onnx_opsets(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() != ".onnx":
        return []
    try:
        import onnx
    except ImportError:
        return []
    model = onnx.load(str(path))
    return [
        {"domain": item.domain or "ai.onnx", "version": int(item.version)}
        for item in model.opset_import
    ]


def validate_contract(
    artifact_path: Path,
    package: dict[str, Any],
    *,
    platform_name: str = "desktop",
    check_onnx: bool = False,
) -> dict[str, Any]:
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise SystemExit("onnxruntime is required to package Waveformer edge exports.") from exc

    contract = expected_contract(package, platform_name)
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
    session = ort.InferenceSession(
        str(artifact_path),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )

    actual_inputs = {
        item.name: {
            "shape": shape_values(item.shape),
            "dtype": item.type,
        }
        for item in session.get_inputs()
    }
    actual_outputs = [item.name for item in session.get_outputs()]
    errors: list[str] = []

    if contract["runtime_kind"] != RUNTIME_KIND:
        errors.append(f"runtime_kind must be {RUNTIME_KIND}, got {contract['runtime_kind']}")

    for name in INPUT_NAMES:
        expected_shape = contract["inputs"][name]
        actual = actual_inputs.get(name)
        if actual is None:
            errors.append(f"missing input '{name}'")
            continue
        if actual["shape"] != expected_shape:
            errors.append(
                f"input '{name}' shape mismatch: expected {expected_shape}, got {actual['shape']}"
            )
        if actual["dtype"] != "tensor(float)":
            errors.append(f"input '{name}' dtype mismatch: expected tensor(float), got {actual['dtype']}")

    if actual_outputs != list(OUTPUT_NAMES):
        errors.append(f"output names mismatch: expected {list(OUTPUT_NAMES)}, got {actual_outputs}")

    if check_onnx:
        try:
            import onnx

            model = onnx.load(str(artifact_path))
            onnx.checker.check_model(model)
        except Exception as exc:  # pragma: no cover - optional strict validation
            errors.append(f"onnx checker failed: {exc!r}")

    category_index = (
        contract["categories"].index("dog")
        if "dog" in contract["categories"]
        else 0
    )
    state = {
        name: np.zeros(shape, dtype=np.float32)
        for name, shape in contract["state_tensors"].items()
    }
    first = np.zeros(
        (1, contract["mix_channels"], contract["chunk_samples"]),
        dtype=np.float32,
    )
    second = first.copy()
    second[0, 0, 0] = np.float32(0.25)
    label = np.zeros((1, len(contract["categories"])), dtype=np.float32)
    label[0, category_index] = 1.0

    outputs_first = session.run(
        list(OUTPUT_NAMES),
        {
            "mixture": first,
            "label_vector": label,
            "enc_buf": state["enc_buf"],
            "dec_buf": state["dec_buf"],
            "out_buf": state["out_buf"],
        },
    )
    state = {
        "enc_buf": np.asarray(outputs_first[1], dtype=np.float32),
        "dec_buf": np.asarray(outputs_first[2], dtype=np.float32),
        "out_buf": np.asarray(outputs_first[3], dtype=np.float32),
    }
    outputs_second = session.run(
        list(OUTPUT_NAMES),
        {
            "mixture": second,
            "label_vector": label,
            "enc_buf": state["enc_buf"],
            "dec_buf": state["dec_buf"],
            "out_buf": state["out_buf"],
        },
    )
    for index, output in enumerate(outputs_second):
        array = np.asarray(output)
        if not np.all(np.isfinite(array)):
            errors.append(f"output '{OUTPUT_NAMES[index]}' contains non-finite values")

    target = np.asarray(outputs_second[0], dtype=np.float32)
    if int(target.size) != contract["mix_channels"] * contract["chunk_samples"]:
        errors.append(
            "target_chunk size mismatch: expected "
            f"{contract['mix_channels'] * contract['chunk_samples']}, got {target.size}"
        )
    for state_name, output_index in (("enc_buf", 1), ("dec_buf", 2), ("out_buf", 3)):
        actual_shape = list(np.asarray(outputs_second[output_index]).shape)
        expected_shape = contract["state_tensors"][state_name]
        if actual_shape != expected_shape:
            errors.append(
                f"output '{state_name}_out' shape mismatch: expected {expected_shape}, got {actual_shape}"
            )

    result = {
        "artifact": project_relative(artifact_path),
        "ok": not errors,
        "errors": errors,
        "providers": list(session.get_providers()),
        "sample_rate": contract["sample_rate"],
        "chunk_samples": contract["chunk_samples"],
        "mix_channels": contract["mix_channels"],
        "category_count": len(contract["categories"]),
        "inputs": [
            {"name": name, "shape": contract["inputs"][name], "dtype": "float32"}
            for name in INPUT_NAMES
        ],
        "outputs": [{"name": name} for name in OUTPUT_NAMES],
        "opsets": read_onnx_opsets(artifact_path),
    }
    if errors:
        raise SystemExit("Waveformer export contract validation failed:\n" + "\n".join(errors))
    return result


def make_sidecar(
    *,
    artifact_path: Path,
    format_name: str,
    role: str,
    package: dict[str, Any],
    package_version: str,
    contract: dict[str, Any],
    validation: dict[str, Any],
    source_onnx: Path,
    source_metadata_path: Path | None,
    source_metadata: dict[str, Any],
) -> dict[str, Any]:
    canonical = dict(source_metadata)
    canonical.update(
        {
            "format": format_name,
            "artifact_role": role,
            "model_id": package["model_id"],
            "package_version": package_version,
            "runtime_kind": RUNTIME_KIND,
            "output": project_relative(artifact_path),
            "artifact_sha256": sha256_file(artifact_path),
            "artifact_bytes": artifact_path.stat().st_size,
            "sample_rate": contract["sample_rate"],
            "chunk_samples": contract["chunk_samples"],
            "chunk_ms": contract["chunk_ms"],
            "mix_channels": contract["mix_channels"],
            "labels": contract["categories"],
            "state_tensors": contract["state_tensors"],
            "inputs": validation["inputs"],
            "outputs": validation["outputs"],
            "source_artifact": {
                "path": project_relative(source_onnx),
                "sha256": sha256_file(source_onnx),
                "metadata": project_relative(source_metadata_path) if source_metadata_path else None,
                "original_output": source_metadata.get("output"),
            },
            "packaged_at": utc_now(),
            "check": {
                "ok": validation["ok"],
                "contract_source": "ai/models/Waveformer/model_package.json",
                "packager": "ai/export/export_waveformer_edge.py",
                "providers": validation["providers"],
                "opsets": validation["opsets"],
            },
        }
    )
    return canonical


def optimize_desktop_onnx(source_onnx: Path, output_path: Path) -> None:
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise SystemExit("onnxruntime is required to optimize the desktop ONNX.") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output_path.with_name(f".{output_path.name}.{uuid4().hex}.tmp")
    try:
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
        options.optimized_model_filepath = str(temp_output)
        session = ort.InferenceSession(
            str(source_onnx),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        del session
        if not temp_output.exists():
            raise SystemExit(f"ONNX Runtime did not write the optimized desktop model: {temp_output}")
        copy_file_over(temp_output, output_path)
    finally:
        remove_file_best_effort(temp_output)


def convert_android_ort(source_onnx: Path, output_path: Path, required_ops_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temp_root = output_path.parent / f"_waveformer_ort_{uuid4().hex}"
    try:
        temp_root.mkdir(parents=True, exist_ok=False)
        input_path = temp_root / "semantic_hearing_100ms_android.onnx"
        conversion_out = temp_root / "converted"
        conversion_out.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_onnx, input_path)

        command = [
            sys.executable,
            "-m",
            "onnxruntime.tools.convert_onnx_models_to_ort",
            "--output_dir",
            str(conversion_out),
            "--optimization_style",
            "Fixed",
            "--enable_type_reduction",
            "--save_optimized_onnx_model",
            "--target_platform",
            "arm",
            str(input_path),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise SystemExit(
                "ORT format conversion failed.\n"
                f"command: {' '.join(command)}\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )

        ort_files = sorted(conversion_out.rglob("*.ort"))
        if not ort_files:
            raise SystemExit(
                "ORT conversion completed but no .ort file was produced.\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )
        config_files = [
            path
            for path in sorted(conversion_out.rglob("*.config"))
            if "required" in path.name.lower() and "operator" in path.name.lower()
        ]
        if not config_files:
            raise SystemExit(
                "ORT conversion completed but no required-operators config was produced.\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )

        copy_file_over(ort_files[0], output_path)
        copy_file_over(config_files[0], required_ops_path)
        rewrite_required_ops_header(required_ops_path, output_path)
    finally:
        remove_tree_best_effort(temp_root)


def rewrite_required_ops_header(required_ops_path: Path, artifact_path: Path) -> None:
    """Replace converter temp-path comments with stable package provenance."""
    text = required_ops_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    operator_lines = [line for line in lines if not line.startswith("#")]
    stable_lines = [
        "# Required operators for "
        + project_relative(artifact_path),
        "# Generated by ai/export/export_waveformer_edge.py",
        *operator_lines,
    ]
    required_ops_path.write_text("\n".join(stable_lines) + "\n", encoding="utf-8")


def update_package(
    package_path: Path,
    *,
    package_version: str,
    desktop_path: Path,
    desktop_metadata_path: Path,
    android_path: Path,
    android_metadata_path: Path,
    required_ops_path: Path,
) -> dict[str, Any]:
    package = read_json(package_path)
    package["package_version"] = package_version
    package["description"] = (
        "Streaming Waveformer target extractor using the validated 100 ms ONNX "
        "contract, canonical ai/models/Exports packaging, a desktop optimized "
        "ONNX artifact, and an Android ORT-format artifact."
    )
    package["optimized_model_path"] = DESKTOP_ARTIFACT_RELATIVE

    validation_summary = package.setdefault("validation_summary", {})
    validation_summary["status"] = "onnx_contract_validated_cpu_and_android_ort_packaged"
    validation_summary["audit_script"] = "ai/scripts/audit_waveformer_onnx.py"
    validation_summary["last_audit"] = {
        "provider": "CPUExecutionProvider",
        "opset": 20,
        "two_step_stateful_smoke": "passed",
        "desktop_artifact": project_relative(desktop_path),
        "android_artifact": project_relative(android_path),
        "required_operators_config": project_relative(required_ops_path),
    }

    desktop = package["platforms"]["desktop"]
    desktop["runtime_kind"] = RUNTIME_KIND
    desktop["artifact"] = DESKTOP_ARTIFACT_RELATIVE
    desktop["metadata_artifacts"] = [DESKTOP_METADATA_RELATIVE]

    android = package["platforms"]["android"]
    android["runtime_kind"] = RUNTIME_KIND
    android["artifact"] = ANDROID_ARTIFACT_RELATIVE
    android["metadata_artifacts"] = [
        ANDROID_METADATA_RELATIVE,
        ANDROID_REQUIRED_OPS_RELATIVE,
    ]
    android["bundle_kind"] = "suppression_model_bundle"

    write_json(package_path, package)
    return package


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Package the validated Waveformer edge ONNX export.")
    parser.add_argument(
        "--source-onnx",
        type=Path,
        default=None,
        help=(
            "Validated source ONNX. Defaults to the canonical Exports source copy, "
            "then the generated Android build-cache copy."
        ),
    )
    parser.add_argument(
        "--source-metadata",
        type=Path,
        default=None,
        help="Optional metadata for --source-onnx. Defaults to <source>.json when present.",
    )
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--package-path", type=Path, default=PACKAGE_PATH)
    parser.add_argument(
        "--package-version",
        default="waveformer_edge_100ms_exports_20260505",
    )
    parser.add_argument("--write-package", action="store_true")
    parser.add_argument(
        "--check-onnx",
        action="store_true",
        help="Also run onnx.checker on ONNX artifacts during contract validation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_root = args.out_root.resolve()
    package_path = args.package_path.resolve()
    source_onnx, source_metadata_path = resolve_source_paths(
        args.source_onnx,
        args.source_metadata,
        out_root,
    )

    package = read_json(package_path)
    if package.get("model_id") != MODEL_ID:
        raise SystemExit(f"Expected package model_id {MODEL_ID}, got {package.get('model_id')}")

    source_metadata = read_json(source_metadata_path) if source_metadata_path else {}
    source_dir = out_root / "source"
    desktop_dir = out_root / "desktop"
    android_dir = out_root / "android"
    source_copy = source_dir / "semantic_hearing_100ms_source.onnx"
    source_sidecar = source_dir / "semantic_hearing_100ms_source.onnx.json"
    desktop_onnx = desktop_dir / "semantic_hearing_100ms_desktop.onnx"
    desktop_sidecar = desktop_dir / "semantic_hearing_100ms_desktop.onnx.json"
    android_ort = android_dir / "model_fixed.ort"
    android_sidecar = android_dir / "model_fixed.ort.json"
    android_required_ops = android_dir / "required_operators.config"

    source_dir.mkdir(parents=True, exist_ok=True)
    desktop_dir.mkdir(parents=True, exist_ok=True)
    android_dir.mkdir(parents=True, exist_ok=True)

    source_validation = validate_contract(
        source_onnx,
        package,
        platform_name="desktop",
        check_onnx=args.check_onnx,
    )
    if source_onnx != source_copy.resolve():
        shutil.copy2(source_onnx, source_copy)
    source_copy_validation = validate_contract(
        source_copy,
        package,
        platform_name="desktop",
        check_onnx=args.check_onnx,
    )
    source_contract = expected_contract(package, "desktop")
    write_json(
        source_sidecar,
        make_sidecar(
            artifact_path=source_copy,
            format_name="onnx",
            role="canonical_source",
            package=package,
            package_version=args.package_version,
            contract=source_contract,
            validation=source_copy_validation,
            source_onnx=source_onnx,
            source_metadata_path=source_metadata_path,
            source_metadata=source_metadata,
        ),
    )

    optimize_desktop_onnx(source_copy, desktop_onnx)
    desktop_validation = validate_contract(
        desktop_onnx,
        package,
        platform_name="desktop",
        check_onnx=args.check_onnx,
    )
    write_json(
        desktop_sidecar,
        make_sidecar(
            artifact_path=desktop_onnx,
            format_name="onnx",
            role="desktop_cpu_optimized",
            package=package,
            package_version=args.package_version,
            contract=source_contract,
            validation=desktop_validation,
            source_onnx=source_onnx,
            source_metadata_path=source_metadata_path,
            source_metadata=source_metadata,
        ),
    )

    convert_android_ort(source_copy, android_ort, android_required_ops)
    android_validation = validate_contract(
        android_ort,
        package,
        platform_name="desktop",
        check_onnx=False,
    )
    write_json(
        android_sidecar,
        make_sidecar(
            artifact_path=android_ort,
            format_name="ort",
            role="android_ort_fixed",
            package=package,
            package_version=args.package_version,
            contract=source_contract,
            validation=android_validation,
            source_onnx=source_onnx,
            source_metadata_path=source_metadata_path,
            source_metadata=source_metadata,
        ),
    )

    if args.write_package:
        package = update_package(
            package_path,
            package_version=args.package_version,
            desktop_path=desktop_onnx,
            desktop_metadata_path=desktop_sidecar,
            android_path=android_ort,
            android_metadata_path=android_sidecar,
            required_ops_path=android_required_ops,
        )

    summary = {
        "ok": True,
        "model_id": package["model_id"],
        "package_version": args.package_version,
        "source": {
            "input": project_relative(source_onnx),
            "artifact": project_relative(source_copy),
            "metadata": project_relative(source_sidecar),
            "sha256": sha256_file(source_copy),
            "validation": source_validation,
        },
        "desktop": {
            "artifact": project_relative(desktop_onnx),
            "metadata": project_relative(desktop_sidecar),
            "sha256": sha256_file(desktop_onnx),
            "validation": desktop_validation,
        },
        "android": {
            "artifact": project_relative(android_ort),
            "metadata": project_relative(android_sidecar),
            "required_operators": project_relative(android_required_ops),
            "sha256": sha256_file(android_ort),
            "validation": android_validation,
        },
        "package_written": bool(args.write_package),
        "package_path": project_relative(package_path),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
