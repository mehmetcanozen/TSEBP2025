"""Windows export/package workflow for selected-speaker engines.

This deliberately keeps the quality-preserving ClearVoice path as a native
runtime bundle and exports only the fast TSExtract model to FP32 ONNX.
Generated model files and bundles live under ai/models/exports, which is
ignored by git.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Iterable

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AI_ROOT = PROJECT_ROOT / "ai"
SPEAKER_SEPARATOR_DIR = AI_ROOT / "models" / "SpeakerSeperator"
DEFAULT_EXPORT_ROOT = AI_ROOT / "models" / "exports" / "target_speaker_windows"
DEFAULT_TSEXTRACT_ONNX = DEFAULT_EXPORT_ROOT / "tsextract" / "tsextract_fp32.onnx"
DEFAULT_CLEARVOICE_BUNDLE = DEFAULT_EXPORT_ROOT / "clearvoice_native"
DEFAULT_TSEXTRACT_ONNX_OPSET = 18

TSEXTRACT_EXPORT_DEPS = ("torch", "onnx", "onnxruntime", "asteroid", "scipy", "soundfile")
CLEARVOICE_RUNTIME_DEPS = ("torch", "torchaudio", "clearvoice", "speechbrain", "numpy", "scipy", "soundfile")
CLEARVOICE_PACKAGE_DEPS = ()
PACKAGE_IGNORE_DIRS = {".cache", ".git", ".pytest_cache", "__pycache__"}
PACKAGE_IGNORE_PATTERNS = ("*.pyc", "*.pyo")
CLEARVOICE_RUNTIME_REQUIREMENTS = (
    "numpy>=1.24,<3",
    "scipy>=1.11",
    "soundfile>=0.12.1",
    "torch>=2.2",
    "torchaudio>=2.2",
    "clearvoice>=0.1.2",
    "speechbrain>=1.0.0",
)
CLEARVOICE_CHECKPOINT_FILES = ("last_best_checkpoint", "last_best_checkpoint.pt")
CLEARVOICE_SPEAKER_FILES = (
    "hyperparams.yaml",
    "embedding_model.ckpt",
    "classifier.ckpt",
    "label_encoder.ckpt",
    "mean_var_norm_emb.ckpt",
)


class TSExtractONNXWrapper:
    """Lazily defined wrapper; torch is imported only by export/validation."""


def setup_repo_imports() -> None:
    for path in (PROJECT_ROOT, SPEAKER_SEPARATOR_DIR / "src"):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def check_env(args: argparse.Namespace) -> None:
    groups = {
        "tsextract-export": TSEXTRACT_EXPORT_DEPS,
        "clearvoice-package": CLEARVOICE_PACKAGE_DEPS,
        "clearvoice-runtime": CLEARVOICE_RUNTIME_DEPS,
    }
    selected = args.target
    if selected != "all":
        groups = {selected: groups[selected]}

    print(f"Python: {sys.executable}")
    for group, names in groups.items():
        missing = [name for name in names if not module_available(name)]
        status = "ok" if not missing else f"missing: {', '.join(missing)}"
        print(f"{group}: {status}")
        if group == "clearvoice-package":
            print("  note: package-clearvoice-runtime only copies native assets; it does not need ClearVoice imported.")
    if selected == "all":
        print("tip: use `check-env --target tsextract-export` for the ONNX export requirement only.")


def load_tsextract_separator(args: argparse.Namespace):
    setup_repo_imports()
    if not args.allow_download:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    from ai.ai_runtime.separation.target_speaker_separator import TargetSpeakerSeparator

    separator = TargetSpeakerSeparator(
        model_dir=args.model_dir,
        checkpoint_path=args.checkpoint,
        device=args.device,
        engine="tsextract",
    )
    patch_tsextract_norms_for_export(separator)
    separator._lazy_load_model()
    checkpoint_path = separator._resolve_checkpoint_path()
    return separator, checkpoint_path


def patch_tsextract_norms_for_export(separator) -> None:
    """Patch TSExcalibur's GlobLN helper only inside this export process.

    The native helper builds dims with torch.arange(...).tolist(), which works
    for inference but makes torch.export treat the reduction dims as
    data-dependent symbolic values. A static rank-based tuple is equivalent for
    this model and keeps the actual checkpoint weights untouched.
    """
    separator._ensure_source_on_path()

    import torch
    from calibur.model import norms as calibur_norms

    def export_z_norm(x, dims, eps: float = 1e-8):
        dims_tuple = tuple(int(dim) for dim in dims)
        mean = x.mean(dim=dims_tuple, keepdim=True)
        var = torch.var(x, dim=dims_tuple, keepdim=True, unbiased=False)
        return (x - mean) / torch.sqrt(var + eps)

    def export_glob_norm(x, eps: float = 1e-8):
        return export_z_norm(x, tuple(range(1, x.dim())), eps)

    calibur_norms.z_norm = export_z_norm
    calibur_norms._glob_norm = export_glob_norm


def make_tsextract_wrapper(model):
    import torch

    class _Wrapper(torch.nn.Module):
        def __init__(self, wrapped):
            super().__init__()
            self.wrapped = wrapped

        def forward(self, mixture, reference, reference_length):
            target, _speaker_logits = self.wrapped(mixture, reference, reference_length)
            if target.ndim == 1:
                target = target.unsqueeze(0)
            if target.ndim == 3 and target.shape[1] == 1:
                target = target.squeeze(1)
            return target

    return _Wrapper(model)


def export_tsextract_onnx(args: argparse.Namespace) -> None:
    require_modules(TSEXTRACT_EXPORT_DEPS)
    import onnx
    import torch

    separator, checkpoint_path = load_tsextract_separator(args)
    wrapper = make_tsextract_wrapper(separator._model).to(args.device).eval()
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)

    mixture = torch.zeros(1, args.mixture_samples, dtype=torch.float32, device=args.device)
    reference = torch.zeros(1, args.reference_samples, dtype=torch.float32, device=args.device)
    reference_length = torch.full(
        (1,),
        args.reference_samples,
        dtype=torch.long,
        device=args.device,
    )

    input_names = ["mixture", "reference", "reference_length"]
    output_names = ["target"]
    dynamic_axes = (
        {
            "mixture": {1: "mixture_samples"},
            "reference": {1: "reference_samples"},
            "reference_length": {0: "batch"},
            "target": {1: "mixture_samples"},
        }
        if args.dynamic_axes
        else None
    )

    started = time.perf_counter()
    with torch.no_grad():
        export_kwargs = {
            "opset_version": args.opset,
            "input_names": input_names,
            "output_names": output_names,
            "do_constant_folding": True,
        }
        if args.exporter == "dynamo":
            torch.onnx.export(
                wrapper,
                (mixture, reference, reference_length),
                str(output),
                dynamo=True,
                optimize=True,
                **export_kwargs,
            )
        else:
            if dynamic_axes is not None:
                export_kwargs["dynamic_axes"] = dynamic_axes
            torch.onnx.export(
                wrapper,
                (mixture, reference, reference_length),
                str(output),
                dynamo=False,
                **export_kwargs,
            )
    elapsed = time.perf_counter() - started

    model = onnx.load(str(output))
    onnx.checker.check_model(model)
    manifest = {
        "artifact": "tsextract_fp32_onnx",
        "engine": "tsextract",
        "quality_policy": "fp32_no_quantization",
        "sample_rate_hz": int(separator.sample_rate),
        "opset": int(args.opset),
        "opset_note": "TSExtract/Asteroid decoder uses col2im; PyTorch ONNX export needs opset >= 18.",
        "exporter": args.exporter,
        "shape_policy": "dynamic_axes" if dynamic_axes is not None else "fixed_shape",
        "mixture_samples": int(args.mixture_samples),
        "reference_samples": int(args.reference_samples),
        "input_names": input_names,
        "output_names": output_names,
        "dynamic_axes": dynamic_axes or {},
        "checkpoint": str(checkpoint_path),
        "output": str(output),
        "sha256": sha256_file(output),
        "bytes": output.stat().st_size,
        "external_data_files": [
            {
                "path": str(path),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in find_onnx_external_data_files(output)
        ],
        "runtime_seconds": elapsed,
    }
    write_json(output.with_suffix(".manifest.json"), manifest)
    print(json.dumps(manifest, indent=2))


def validate_tsextract_onnx(args: argparse.Namespace) -> None:
    require_modules(TSEXTRACT_EXPORT_DEPS)
    import onnxruntime as ort
    import torch

    separator, checkpoint_path = load_tsextract_separator(args)
    wrapper = make_tsextract_wrapper(separator._model).to(args.device).eval()

    mixture = load_audio(args.mixture, separator.sample_rate)
    reference = load_audio(args.reference, separator.sample_rate)
    mixture, mixture_original_samples = pad_or_trim_audio(mixture, args.mixture_samples)
    reference, reference_original_samples = pad_or_trim_audio(reference, args.reference_samples)
    mixture_t = torch.as_tensor(mixture, dtype=torch.float32, device=args.device).unsqueeze(0)
    reference_t = torch.as_tensor(reference, dtype=torch.float32, device=args.device).unsqueeze(0)
    reference_length_t = torch.tensor(
        [min(reference_original_samples, reference_t.shape[-1])],
        dtype=torch.long,
        device=args.device,
    )

    with torch.no_grad():
        pt_target = wrapper(mixture_t, reference_t, reference_length_t)
    pt_np = pt_target.squeeze(0).detach().cpu().numpy().astype(np.float32)

    session = ort.InferenceSession(str(args.onnx), providers=["CPUExecutionProvider"])
    onnx_np = session.run(
        None,
        {
            "mixture": mixture_t.detach().cpu().numpy(),
            "reference": reference_t.detach().cpu().numpy(),
            "reference_length": reference_length_t.detach().cpu().numpy(),
        },
    )[0].squeeze(0).astype(np.float32)

    metrics = compare_audio(pt_np, onnx_np)
    metrics.update(
        {
            "artifact": "tsextract_onnx_validation",
            "engine": "tsextract",
            "onnx": str(args.onnx),
            "checkpoint": str(checkpoint_path),
            "mixture": str(args.mixture),
            "reference": str(args.reference),
            "mixture_samples": int(args.mixture_samples),
            "mixture_original_samples": int(mixture_original_samples),
            "reference_samples": int(args.reference_samples),
            "reference_original_samples": int(reference_original_samples),
            "passed": bool(
                metrics["correlation"] >= args.min_correlation
                and metrics["rmse"] <= args.max_rmse
            ),
        },
    )
    write_json(args.report, metrics)
    print(json.dumps(metrics, indent=2))
    if not metrics["passed"]:
        raise SystemExit(
            "ONNX validation failed. Keep the PyTorch/native runtime until this passes."
        )


def package_clearvoice_runtime(args: argparse.Namespace) -> None:
    root = args.output
    model_dir = args.model_dir
    prepare_new_output_dir(root)

    write_clearvoice_runtime_requirements(root / "requirements.txt")
    if args.include_dev_docs:
        copy_file(model_dir / "pyproject.toml", root / "pyproject.toml")
        copy_file(model_dir / "requirements.txt", root / "requirements.original.txt")
        copy_file(model_dir / "README.md", root / "README.original.md")
        copy_file(model_dir / "PROJECT_EXPLANATION.md", root / "PROJECT_EXPLANATION.original.md")
    copy_tree(model_dir / "src", root / "src")
    copy_clearvoice_checkpoint_assets(model_dir, root)
    copy_clearvoice_speaker_assets(model_dir, root)
    (root / "outputs").mkdir(exist_ok=True)
    (root / "voice_profiles").mkdir(exist_ok=True)
    (root / "models" / "huggingface" / "hub").mkdir(parents=True, exist_ok=True)
    write_clearvoice_launcher(root / "run_clearvoice_extract.ps1")
    write_clearvoice_installer(root / "install_clearvoice_runtime.ps1")

    manifest = {
        "artifact": "clearvoice_native_windows_runtime",
        "engine": "clearvoice",
        "quality_policy": "native_fp32_pipeline_no_quantization_lossless_slim_package",
        "sample_rate_hz": 16000,
        "pipeline": [
            "ClearVoice MossFormer2_SS_16K speech separation",
            "SpeechBrain ECAPA speaker embedding",
            "cosine similarity stem selection",
        ],
        "entrypoint": "run_clearvoice_extract.ps1",
        "installer": "install_clearvoice_runtime.ps1",
        "model_dir": str(model_dir),
        "output": str(root),
        "required_python": ">=3.11,<3.12",
        "required_packages": list(CLEARVOICE_RUNTIME_REQUIREMENTS),
        "slim_policy": {
            "mode": "lossless_end_user",
            "kept": [
                "MossFormer2_SS_16K last_best_checkpoint.pt",
                "MossFormer2_SS_16K last_best_checkpoint pointer",
                "SpeechBrain ECAPA hparams/checkpoints",
                "speechthing runtime source",
            ],
            "excluded": [
                "Hugging Face download caches",
                "git metadata",
                "pytest caches",
                "Python bytecode caches",
                "developer docs unless --include-dev-docs is set",
            ],
        },
        "asset_sizes": summarize_assets(root),
    }
    if args.hash_assets:
        manifest["asset_hashes"] = {
            str(path.relative_to(root)): sha256_file(path)
            for path in iter_manifest_files(root)
        }
    write_json(root / "manifest.json", manifest)
    write_clearvoice_readme(root / "README.md", manifest)
    print(json.dumps(manifest, indent=2))


def package_windows(args: argparse.Namespace) -> None:
    root = args.output
    prepare_new_output_dir(root)
    clearvoice_args = argparse.Namespace(
        model_dir=args.model_dir,
        output=root / "clearvoice_native",
        hash_assets=args.hash_assets,
        include_dev_docs=args.include_dev_docs,
    )
    package_clearvoice_runtime(clearvoice_args)
    if args.tsextract_onnx:
        target_dir = root / "tsextract_onnx"
        target_dir.mkdir(parents=True, exist_ok=True)
        copy_file(args.tsextract_onnx, target_dir / args.tsextract_onnx.name)
        copy_onnx_external_data_files(args.tsextract_onnx, target_dir)
        manifest = args.tsextract_onnx.with_suffix(".manifest.json")
        if manifest.exists():
            copy_file(manifest, target_dir / manifest.name)
        write_tsextract_launcher(target_dir / "run_tsextract_onnx_python.ps1")

    write_json(
        root / "windows_bundle_manifest.json",
        {
            "artifact": "target_speaker_windows_bundle",
            "engines": ["clearvoice_native", "tsextract_onnx" if args.tsextract_onnx else "tsextract_onnx_missing"],
            "quality_policy": "clearvoice native FP32 lossless slim package; tsextract ONNX FP32",
            "output": str(root),
        },
    )


def require_modules(names: Iterable[str]) -> None:
    missing = [name for name in names if not module_available(name)]
    if missing:
        raise SystemExit(
            "Missing Python packages: "
            + ", ".join(missing)
            + ". Run check-env first, then install the missing packages in your chosen env."
        )


def load_audio(path: Path, sample_rate: int) -> np.ndarray:
    import soundfile as sf
    from scipy.signal import resample_poly

    audio, original_sr = sf.read(str(path), dtype="float32", always_2d=False)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if int(original_sr) != int(sample_rate):
        from fractions import Fraction

        ratio = Fraction(int(sample_rate), int(original_sr)).limit_denominator()
        audio = resample_poly(audio, ratio.numerator, ratio.denominator).astype(np.float32)
    return np.nan_to_num(audio.reshape(-1), nan=0.0, posinf=0.0, neginf=0.0)


def compare_audio(left: np.ndarray, right: np.ndarray) -> dict[str, float | int]:
    left = np.asarray(left, dtype=np.float32).reshape(-1)
    right = np.asarray(right, dtype=np.float32).reshape(-1)
    samples = min(left.size, right.size)
    left = left[:samples]
    right = right[:samples]
    diff = left - right
    left_std = float(np.std(left))
    right_std = float(np.std(right))
    correlation = (
        float(np.corrcoef(left, right)[0, 1])
        if samples and left_std > 0.0 and right_std > 0.0
        else 0.0
    )
    return {
        "samples": int(samples),
        "correlation": correlation,
        "rmse": float(np.sqrt(np.mean(diff**2))) if samples else 0.0,
        "max_abs_diff": float(np.max(np.abs(diff))) if samples else 0.0,
        "mean_abs_diff": float(np.mean(np.abs(diff))) if samples else 0.0,
    }


def pad_or_trim_audio(audio: np.ndarray, target_samples: int) -> tuple[np.ndarray, int]:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    original_samples = int(audio.size)
    target_samples = int(target_samples)
    if target_samples <= 0:
        return audio, original_samples
    if audio.size >= target_samples:
        return audio[:target_samples].astype(np.float32, copy=False), original_samples
    padded = np.zeros(target_samples, dtype=np.float32)
    padded[: audio.size] = audio
    return padded, original_samples


def prepare_new_output_dir(path: Path) -> None:
    if path.exists() and not path.is_dir():
        raise SystemExit(f"Output path exists but is not a directory: {path}")
    if path.exists() and any(path.iterdir()):
        raise SystemExit(
            f"Output folder is not empty: {path}\n"
            "Choose a fresh --output path for packaging. This avoids stale cache "
            "files from older bundles being mistaken for slim release contents."
        )
    path.mkdir(parents=True, exist_ok=True)


def copy_clearvoice_checkpoint_assets(model_dir: Path, root: Path) -> None:
    src_dir = model_dir / "checkpoints" / "MossFormer2_SS_16K"
    dst_dir = root / "checkpoints" / "MossFormer2_SS_16K"
    for name in CLEARVOICE_CHECKPOINT_FILES:
        copy_file(src_dir / name, dst_dir / name)


def copy_clearvoice_speaker_assets(model_dir: Path, root: Path) -> None:
    src_dir = model_dir / "pretrained_models" / "spkrec-ecapa-voxceleb"
    dst_dir = root / "pretrained_models" / "spkrec-ecapa-voxceleb"
    for name in CLEARVOICE_SPEAKER_FILES:
        copy_file(src_dir / name, dst_dir / name)


def find_onnx_external_data_files(onnx_path: Path) -> list[Path]:
    sidecars: list[Path] = []
    default_sidecar = onnx_path.with_name(onnx_path.name + ".data")
    if default_sidecar.exists():
        sidecars.append(default_sidecar)
    sidecars.extend(
        path
        for path in sorted(onnx_path.parent.glob(onnx_path.name + ".data.*"))
        if path.is_file() and path not in sidecars
    )
    return sidecars


def copy_onnx_external_data_files(onnx_path: Path, target_dir: Path) -> None:
    for sidecar in find_onnx_external_data_files(onnx_path):
        copy_file(sidecar, target_dir / sidecar.name)


def copy_file(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(src)
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore_package_cache_files)


def ignore_package_cache_files(_directory: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        if name in PACKAGE_IGNORE_DIRS:
            ignored.add(name)
            continue
        if any(fnmatch.fnmatch(name, pattern) for pattern in PACKAGE_IGNORE_PATTERNS):
            ignored.add(name)
    return ignored


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_manifest_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.name not in {"manifest.json", "README.md"}:
            yield path


def summarize_assets(root: Path) -> dict[str, int]:
    summary: dict[str, int] = {}
    for child in ("src", "checkpoints", "pretrained_models"):
        path = root / child
        summary[child] = sum(file.stat().st_size for file in path.rglob("*") if file.is_file())
    return summary


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_clearvoice_runtime_requirements(path: Path) -> None:
    path.write_text("\n".join(CLEARVOICE_RUNTIME_REQUIREMENTS) + "\n", encoding="utf-8")


def write_clearvoice_launcher(path: Path) -> None:
    path.write_text(
        """param(
  [Parameter(Mandatory=$true)] [string]$Mixture,
  [Parameter(Mandatory=$true)] [string]$Reference,
  [string]$Out = "outputs\\clearvoice_extract",
  [ValidateSet("cpu", "cuda")] [string]$Device = "cpu",
  [switch]$AllowDownload
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $Root "src"
$env:HF_HOME = Join-Path $Root "models\\huggingface"
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME "hub"
$env:HF_XET_CACHE = Join-Path $env:HF_HOME "xet"
$env:HF_HUB_DISABLE_XET = "1"
if (-not $AllowDownload) {
  $env:HF_HUB_OFFLINE = "1"
  $env:TRANSFORMERS_OFFLINE = "1"
}
$VenvPython = Join-Path $Root ".venv\\Scripts\\python.exe"
if (Test-Path -LiteralPath $VenvPython) {
  $Python = $VenvPython
} else {
  $Python = "python"
}
& $Python -m speechthing.cli --debug extract --mixture $Mixture --reference $Reference --out $Out --device $Device
""",
        encoding="utf-8",
    )


def write_clearvoice_installer(path: Path) -> None:
    path.write_text(
        """param(
  [string]$Python = "py",
  [switch]$CpuTorch
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Root ".venv"
if (-not (Test-Path -LiteralPath $Venv)) {
  if ($Python -eq "py") {
    & py -3.11 -m venv $Venv
  } else {
    & $Python -m venv $Venv
  }
}
$VenvPython = Join-Path $Venv "Scripts\\python.exe"
& $VenvPython -m pip install --upgrade pip
if ($CpuTorch) {
  & $VenvPython -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
}
& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")
""",
        encoding="utf-8",
    )


def write_tsextract_launcher(path: Path) -> None:
    path.write_text(
        """param(
  [Parameter(Mandatory=$true)] [string]$Mixture,
  [Parameter(Mandatory=$true)] [string]$Reference
)
Write-Host "Use your app/ONNX Runtime wrapper with tsextract_fp32.onnx."
Write-Host "Inputs are mono FP32 arrays at 8000 Hz: mixture, reference, reference_length."
""",
        encoding="utf-8",
    )


def write_clearvoice_readme(path: Path, manifest: dict[str, object]) -> None:
    path.write_text(
        f"""# ClearVoice Native Windows Runtime

This is the slim end-user ClearVoice bundle. It preserves the high-quality
selected-speaker path and does not quantize, prune, or convert the model
weights. It runs:

1. ClearVoice `MossFormer2_SS_16K` separation
2. SpeechBrain ECAPA speaker embedding
3. cosine-similarity stem selection

## Install Once

```powershell
.\\install_clearvoice_runtime.ps1 -CpuTorch
```

Omit `-CpuTorch` if you already want to manage your own CUDA-enabled Torch in
the bundle `.venv`.

## Run Offline

```powershell
.\\run_clearvoice_extract.ps1 -Mixture .\\test\\mix.wav -Reference .\\test\\speaker.wav -Out .\\outputs\\extract -Device cpu
```

The launcher uses `.venv\\Scripts\\python.exe` when it exists and defaults to
offline Hugging Face mode so an end user does not accidentally download a second
copy of the models. Add `-AllowDownload` only when intentionally repairing a
missing asset.

Python requirement: `{manifest["required_python"]}`

## Size Policy

This bundle keeps the real FP32 model assets and skips local caches, git
metadata, Python bytecode, and developer docs. That is why it is much smaller
than a raw project copy, while the actual model quality stays unchanged.
""",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export/package selected-speaker engines for Windows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check-env", help="Show missing dependencies without installing anything.")
    check.add_argument(
        "--target",
        choices=["all", "tsextract-export", "clearvoice-package", "clearvoice-runtime"],
        default="all",
        help="Limit the dependency check to one workflow.",
    )
    check.set_defaults(func=check_env)

    export = subparsers.add_parser("export-tsextract-onnx", help="Export TSExtract to FP32 ONNX.")
    add_common_model_args(export)
    export.add_argument("--output", type=Path, default=DEFAULT_TSEXTRACT_ONNX)
    export.add_argument("--opset", type=int, default=DEFAULT_TSEXTRACT_ONNX_OPSET)
    export.add_argument(
        "--exporter",
        choices=["dynamo", "legacy"],
        default="dynamo",
        help="PyTorch ONNX exporter path. dynamo is the default for this model.",
    )
    export.add_argument(
        "--dynamic-axes",
        action="store_true",
        help=(
            "Experimental legacy dynamic-axis export. The default fixed-shape export "
            "avoids the Asteroid col2im dynamic output-size failure."
        ),
    )
    export.add_argument("--mixture-samples", type=int, default=8000 * 10)
    export.add_argument("--reference-samples", type=int, default=8000 * 3)
    export.set_defaults(func=export_tsextract_onnx)

    validate = subparsers.add_parser("validate-tsextract-onnx", help="Compare ONNX output with PyTorch.")
    add_common_model_args(validate)
    validate.add_argument("--onnx", type=Path, default=DEFAULT_TSEXTRACT_ONNX)
    validate.add_argument("--mixture", type=Path, required=True)
    validate.add_argument("--reference", type=Path, required=True)
    validate.add_argument("--report", type=Path, default=DEFAULT_TSEXTRACT_ONNX.with_suffix(".validation.json"))
    validate.add_argument("--mixture-samples", type=int, default=8000 * 10)
    validate.add_argument("--reference-samples", type=int, default=8000 * 3)
    validate.add_argument("--min-correlation", type=float, default=0.999)
    validate.add_argument("--max-rmse", type=float, default=1.0e-4)
    validate.set_defaults(func=validate_tsextract_onnx)

    clearvoice = subparsers.add_parser(
        "package-clearvoice-runtime",
        help="Copy the native ClearVoice runtime assets into a Windows bundle.",
    )
    clearvoice.add_argument("--model-dir", type=Path, default=SPEAKER_SEPARATOR_DIR)
    clearvoice.add_argument("--output", type=Path, default=DEFAULT_CLEARVOICE_BUNDLE)
    clearvoice.add_argument("--hash-assets", action="store_true")
    clearvoice.add_argument(
        "--include-dev-docs",
        action="store_true",
        help="Also copy original project README/docs and source requirements into the bundle.",
    )
    clearvoice.set_defaults(func=package_clearvoice_runtime)

    package = subparsers.add_parser("package-windows", help="Assemble both engine artifacts into one folder.")
    package.add_argument("--model-dir", type=Path, default=SPEAKER_SEPARATOR_DIR)
    package.add_argument("--output", type=Path, default=DEFAULT_EXPORT_ROOT / "windows_bundle")
    package.add_argument("--tsextract-onnx", type=Path, default=None)
    package.add_argument("--hash-assets", action="store_true")
    package.add_argument(
        "--include-dev-docs",
        action="store_true",
        help="Also copy original project README/docs and source requirements into the ClearVoice bundle.",
    )
    package.set_defaults(func=package_windows)
    return parser


def add_common_model_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model-dir", type=Path, default=SPEAKER_SEPARATOR_DIR)
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="Allow Hugging Face downloads if the local checkpoint is missing. Default is offline-only.",
    )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
