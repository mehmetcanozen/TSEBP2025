"""Smoke-test runtime for exported selected-speaker Windows artifacts.

This module is intentionally separate from the training/export script. It runs
the artifacts the way a consumer would use them:

* TSExtract through ONNX Runtime.
* ClearVoice through the packaged native bundle entrypoint/source.

Usage:
    python -m ai.ai_runtime.separation.exported_target_speaker test-bundle ...
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path
from typing import Any, Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[3]
AI_ROOT = PROJECT_ROOT / "ai"
DEFAULT_EXPORT_ROOT = AI_ROOT / "models" / "exports" / "target_speaker_windows"
DEFAULT_BUNDLE = DEFAULT_EXPORT_ROOT / "windows_bundle_slim"
DEFAULT_TEST_OUT = AI_ROOT / "data" / "audio" / "processed" / "target_speaker_export_tests"
DEFAULT_TSEXTRACT_ONNX = DEFAULT_EXPORT_ROOT / "tsextract" / "tsextract_fp32.onnx"
DEFAULT_TSEXTRACT_BUNDLE_ONNX = DEFAULT_BUNDLE / "tsextract_onnx" / "tsextract_fp32.onnx"
DEFAULT_CLEARVOICE_BUNDLE = DEFAULT_BUNDLE / "clearvoice_native"


class ExportedTSExtractOnnx:
    """Run the exported TSExtract ONNX artifact with ONNX Runtime."""

    def __init__(
        self,
        model_path: Path,
        *,
        manifest_path: Optional[Path] = None,
        device: str = "cpu",
    ) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise ImportError("onnxruntime is required to test TSExtract ONNX.") from exc

        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"TSExtract ONNX not found: {self.model_path}")

        self.manifest_path = manifest_path or self.model_path.with_suffix(".manifest.json")
        self.manifest = read_json_if_exists(self.manifest_path)
        self.sample_rate = int(self.manifest.get("sample_rate_hz", 8000) or 8000)
        self.mixture_samples = int(self.manifest.get("mixture_samples", 80000) or 80000)
        self.reference_samples = int(self.manifest.get("reference_samples", 24000) or 24000)

        providers = resolve_onnx_providers(ort, device)
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(self.model_path),
            sess_options=options,
            providers=providers,
        )

    def extract(self, mixture_path: Path, reference_path: Path) -> dict[str, Any]:
        mixture, mixture_sample_rate = load_audio(mixture_path, target_sample_rate=self.sample_rate)
        reference, reference_sample_rate = load_audio(reference_path, target_sample_rate=self.sample_rate)
        mixture, mixture_original_samples = pad_or_trim_audio(mixture, self.mixture_samples)
        reference, reference_original_samples = pad_or_trim_audio(reference, self.reference_samples)

        reference_length = np.asarray(
            [min(reference_original_samples, self.reference_samples)],
            dtype=np.int64,
        )
        inputs = {
            "mixture": mixture.reshape(1, -1).astype(np.float32, copy=False),
            "reference": reference.reshape(1, -1).astype(np.float32, copy=False),
            "reference_length": reference_length,
        }

        started = time.perf_counter()
        output = self.session.run(None, inputs)[0]
        runtime_seconds = time.perf_counter() - started
        target = np.asarray(output, dtype=np.float32).reshape(-1)

        return {
            "engine": "tsextract_onnx",
            "target": target,
            "sample_rate": self.sample_rate,
            "runtime_seconds": runtime_seconds,
            "input": {
                "mixture": str(mixture_path),
                "reference": str(reference_path),
                "mixture_sample_rate_hz": mixture_sample_rate,
                "reference_sample_rate_hz": reference_sample_rate,
                "mixture_original_samples_resampled": mixture_original_samples,
                "reference_original_samples_resampled": reference_original_samples,
                "mixture_samples": self.mixture_samples,
                "reference_samples": self.reference_samples,
                "reference_length": int(reference_length[0]),
            },
            "onnx": str(self.model_path),
            "manifest": str(self.manifest_path) if self.manifest_path.exists() else None,
            "providers": list(self.session.get_providers()),
        }


class ClearVoiceNativeBundle:
    """Run a packaged ClearVoice native Windows bundle."""

    def __init__(
        self,
        bundle_dir: Path,
        *,
        python_executable: Optional[Path] = None,
        device: str = "cpu",
        allow_download: bool = False,
        timeout_seconds: float = 0.0,
    ) -> None:
        self.bundle_dir = Path(bundle_dir)
        if not self.bundle_dir.exists():
            raise FileNotFoundError(f"ClearVoice bundle not found: {self.bundle_dir}")
        self.src_dir = self.bundle_dir / "src"
        if not (self.src_dir / "speechthing" / "cli.py").exists():
            raise FileNotFoundError(f"speechthing runtime source missing under: {self.src_dir}")
        self.python_executable = python_executable or resolve_bundle_python(self.bundle_dir)
        self.device = device
        self.allow_download = bool(allow_download)
        self.timeout_seconds = float(timeout_seconds or 0.0)

    def extract(self, mixture_path: Path, reference_path: Path, out_dir: Path) -> dict[str, Any]:
        out_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["PYTHONPATH"] = prepend_env_path(env.get("PYTHONPATH"), self.src_dir)
        hf_home = self.bundle_dir / "models" / "huggingface"
        env["HF_HOME"] = str(hf_home)
        env["HF_HUB_CACHE"] = str(hf_home / "hub")
        env["HF_XET_CACHE"] = str(hf_home / "xet")
        env["HF_HUB_DISABLE_XET"] = "1"
        if not self.allow_download:
            env["HF_HUB_OFFLINE"] = "1"
            env["TRANSFORMERS_OFFLINE"] = "1"

        command = [
            str(self.python_executable),
            "-m",
            "speechthing.cli",
            "--debug",
            "extract",
            "--mixture",
            str(Path(mixture_path).resolve()),
            "--reference",
            str(Path(reference_path).resolve()),
            "--out",
            str(out_dir.resolve()),
            "--device",
            self.device,
        ]

        started = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=str(self.bundle_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds if self.timeout_seconds > 0 else None,
            check=False,
        )
        runtime_seconds = time.perf_counter() - started

        target_path = out_dir / "target.wav"
        report_path = out_dir / "report.json"
        payload: dict[str, Any] = {
            "engine": "clearvoice_native",
            "bundle": str(self.bundle_dir),
            "python": str(self.python_executable),
            "command": command,
            "returncode": int(completed.returncode),
            "runtime_seconds": runtime_seconds,
            "target_path": str(target_path),
            "report_path": str(report_path) if report_path.exists() else None,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

        if completed.returncode != 0:
            payload["target"] = None
            return payload
        if not target_path.exists():
            payload["returncode"] = 2
            payload["stderr"] = payload["stderr"] + "\nClearVoice target.wav was not created."
            payload["target"] = None
            return payload

        target, sample_rate = load_audio(target_path, target_sample_rate=None)
        payload["target"] = target
        payload["sample_rate"] = int(sample_rate)
        return payload


def test_tsextract_onnx(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    runner = ExportedTSExtractOnnx(
        args.onnx,
        manifest_path=args.manifest,
        device=args.device,
    )
    result = runner.extract(args.mixture, args.reference)
    target = result.pop("target")
    output_path = out_dir / "tsextract_onnx_target_8k.wav"
    write_audio(output_path, target, int(result["sample_rate"]))
    result["output_path"] = str(output_path)
    result["audio_stats"] = audio_stats(target, int(result["sample_rate"]))
    result["passed"] = bool(audio_passes(result["audio_stats"], args.min_rms))
    report_path = out_dir / "tsextract_onnx_report.json"
    write_json(report_path, result)
    result["report_path"] = str(report_path)
    return result


def test_clearvoice_bundle(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = args.out / "clearvoice_native"
    runner = ClearVoiceNativeBundle(
        args.bundle,
        python_executable=args.python,
        device=args.device,
        allow_download=args.allow_download,
        timeout_seconds=args.timeout_seconds,
    )
    result = runner.extract(args.mixture, args.reference, out_dir)
    target = result.pop("target", None)
    if target is None:
        result["audio_stats"] = None
        result["passed"] = False
    else:
        result["audio_stats"] = audio_stats(target, int(result["sample_rate"]))
        result["passed"] = bool(audio_passes(result["audio_stats"], args.min_rms))
    report_path = args.out / "clearvoice_native_report.json"
    write_json(report_path, result)
    result["report_path"] = str(report_path)
    return result


def test_bundle(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {
        "artifact": "target_speaker_export_bundle_test",
        "bundle": str(args.bundle),
        "mixture": str(args.mixture),
        "reference": str(args.reference),
        "device": args.device,
        "results": {},
    }

    if not args.skip_tsextract:
        onnx_path = args.tsextract_onnx or args.bundle / "tsextract_onnx" / "tsextract_fp32.onnx"
        tse_args = argparse.Namespace(
            onnx=onnx_path,
            manifest=args.tsextract_manifest,
            mixture=args.mixture,
            reference=args.reference,
            out=out_dir / "tsextract_onnx",
            device=args.device,
            min_rms=args.min_rms,
        )
        results["results"]["tsextract_onnx"] = test_tsextract_onnx(tse_args)

    if not args.skip_clearvoice:
        clearvoice_bundle = args.clearvoice_bundle or args.bundle / "clearvoice_native"
        cv_args = argparse.Namespace(
            bundle=clearvoice_bundle,
            python=args.clearvoice_python,
            mixture=args.mixture,
            reference=args.reference,
            out=out_dir,
            device=args.device,
            allow_download=args.allow_download,
            timeout_seconds=args.timeout_seconds,
            min_rms=args.min_rms,
        )
        results["results"]["clearvoice_native"] = test_clearvoice_bundle(cv_args)

    results["comparison"] = compare_available_outputs(results["results"])
    results["passed"] = all(
        bool(item.get("passed"))
        for item in results["results"].values()
        if isinstance(item, dict)
    )
    report_path = out_dir / "target_speaker_export_bundle_report.json"
    write_json(report_path, results)
    results["report_path"] = str(report_path)
    return results


def compare_available_outputs(results: dict[str, Any]) -> dict[str, Any] | None:
    left = results.get("tsextract_onnx")
    right = results.get("clearvoice_native")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    left_path = Path(str(left.get("output_path", "")))
    right_path = Path(str(right.get("target_path", "")))
    if not left_path.exists() or not right_path.exists():
        return None

    left_audio, left_sr = load_audio(left_path, target_sample_rate=8000)
    right_audio, right_sr = load_audio(right_path, target_sample_rate=8000)
    samples = min(left_audio.size, right_audio.size)
    if samples <= 0:
        return None
    left_audio = left_audio[:samples]
    right_audio = right_audio[:samples]
    diff = left_audio - right_audio
    left_std = float(np.std(left_audio))
    right_std = float(np.std(right_audio))
    correlation = (
        float(np.corrcoef(left_audio, right_audio)[0, 1])
        if left_std > 0.0 and right_std > 0.0
        else 0.0
    )
    return {
        "note": "Informational only. These are different models, so this is not a pass/fail metric.",
        "sample_rate_hz": int(left_sr or right_sr),
        "samples_compared": int(samples),
        "correlation": correlation,
        "rmse": float(np.sqrt(np.mean(diff**2))),
        "mean_abs_diff": float(np.mean(np.abs(diff))),
    }


def resolve_onnx_providers(ort: Any, device: str) -> list[str]:
    requested = str(device or "cpu").strip().casefold()
    available = set(ort.get_available_providers())
    providers: list[str] = []
    if requested.startswith("cuda") and "CUDAExecutionProvider" in available:
        providers.append("CUDAExecutionProvider")
    providers.append("CPUExecutionProvider")
    return [provider for provider in providers if provider in available]


def resolve_bundle_python(bundle_dir: Path) -> Path:
    venv_python = bundle_dir / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable)


def prepend_env_path(existing: Optional[str], path: Path) -> str:
    text = str(path)
    return text if not existing else text + os.pathsep + existing


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_audio(path: Path, target_sample_rate: Optional[int]) -> tuple[np.ndarray, int]:
    import soundfile as sf
    from scipy.signal import resample_poly

    audio, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
    array = np.asarray(audio, dtype=np.float32)
    if array.ndim == 2:
        array = array.mean(axis=1, dtype=np.float32)
    array = np.nan_to_num(array.reshape(-1), nan=0.0, posinf=0.0, neginf=0.0)

    if target_sample_rate is not None and int(sample_rate) != int(target_sample_rate):
        ratio = Fraction(int(target_sample_rate), int(sample_rate)).limit_denominator()
        array = resample_poly(array, ratio.numerator, ratio.denominator).astype(np.float32)
        sample_rate = int(target_sample_rate)

    return array.astype(np.float32, copy=False), int(sample_rate)


def write_audio(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(
        str(path),
        np.asarray(audio, dtype=np.float32).reshape(-1),
        int(sample_rate),
        subtype="FLOAT",
    )


def pad_or_trim_audio(audio: np.ndarray, target_samples: int) -> tuple[np.ndarray, int]:
    array = np.asarray(audio, dtype=np.float32).reshape(-1)
    original_samples = int(array.size)
    target_samples = int(target_samples)
    if array.size >= target_samples:
        return array[:target_samples].astype(np.float32, copy=False), original_samples
    padded = np.zeros(target_samples, dtype=np.float32)
    padded[: array.size] = array
    return padded, original_samples


def audio_stats(audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
    array = np.asarray(audio, dtype=np.float32).reshape(-1)
    finite = bool(np.all(np.isfinite(array)))
    if array.size == 0:
        return {
            "samples": 0,
            "sample_rate_hz": int(sample_rate),
            "seconds": 0.0,
            "finite": finite,
            "peak_abs": 0.0,
            "rms": 0.0,
            "mean_abs": 0.0,
            "non_silent_fraction": 0.0,
        }
    abs_audio = np.abs(array)
    return {
        "samples": int(array.size),
        "sample_rate_hz": int(sample_rate),
        "seconds": float(array.size / float(sample_rate)),
        "finite": finite,
        "peak_abs": float(np.max(abs_audio)),
        "rms": float(np.sqrt(np.mean(array**2))),
        "mean_abs": float(np.mean(abs_audio)),
        "non_silent_fraction": float(np.mean(abs_audio > 1.0e-5)),
    }


def audio_passes(stats: dict[str, Any], min_rms: float) -> bool:
    return bool(
        stats.get("finite")
        and int(stats.get("samples", 0)) > 0
        and float(stats.get("rms", 0.0)) >= float(min_rms)
        and float(stats.get("peak_abs", 0.0)) > 0.0
    )


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test exported selected-speaker artifacts from ai_runtime.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    tse = subparsers.add_parser("test-tsextract-onnx", help="Run TSExtract ONNX and write a smoke-test report.")
    tse.add_argument("--onnx", type=Path, default=DEFAULT_TSEXTRACT_BUNDLE_ONNX if DEFAULT_TSEXTRACT_BUNDLE_ONNX.exists() else DEFAULT_TSEXTRACT_ONNX)
    tse.add_argument("--manifest", type=Path, default=None)
    add_common_audio_args(tse)
    tse.set_defaults(func=test_tsextract_onnx)

    clearvoice = subparsers.add_parser("test-clearvoice-bundle", help="Run a ClearVoice native bundle and write a smoke-test report.")
    clearvoice.add_argument("--bundle", type=Path, default=DEFAULT_CLEARVOICE_BUNDLE)
    clearvoice.add_argument("--python", type=Path, default=None, help="Python executable to use. Defaults to bundle .venv, then current Python.")
    clearvoice.add_argument("--allow-download", action="store_true", help="Allow HF downloads if bundle assets are missing. Default is offline.")
    clearvoice.add_argument("--timeout-seconds", type=float, default=0.0, help="Optional subprocess timeout. 0 means no timeout.")
    add_common_audio_args(clearvoice)
    clearvoice.set_defaults(func=test_clearvoice_bundle)

    bundle = subparsers.add_parser("test-bundle", help="Run TSExtract ONNX and ClearVoice tests from one Windows bundle.")
    bundle.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    bundle.add_argument("--tsextract-onnx", type=Path, default=None)
    bundle.add_argument("--tsextract-manifest", type=Path, default=None)
    bundle.add_argument("--clearvoice-bundle", type=Path, default=None)
    bundle.add_argument("--clearvoice-python", type=Path, default=None)
    bundle.add_argument("--allow-download", action="store_true", help="Allow HF downloads for ClearVoice. Default is offline.")
    bundle.add_argument("--timeout-seconds", type=float, default=0.0, help="Optional ClearVoice subprocess timeout. 0 means no timeout.")
    bundle.add_argument("--skip-tsextract", action="store_true")
    bundle.add_argument("--skip-clearvoice", action="store_true")
    add_common_audio_args(bundle)
    bundle.set_defaults(func=test_bundle)
    return parser


def add_common_audio_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mixture", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_TEST_OUT)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--min-rms", type=float, default=1.0e-5)


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, indent=2))
    return 0 if bool(result.get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
