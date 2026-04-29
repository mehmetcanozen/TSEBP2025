"""Target-speaker extraction runtime adapter.

This wraps the SpeakerSeperator assets under ``ai/models`` with an in-memory
API so suppression code can use a reference speaker clip without shelling out
to the toy CLI. It can run either the native ClearVoice separate+match pipeline
or the faster TSExcalibur target extractor.
"""

from __future__ import annotations

import logging
import json
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
from scipy.signal import resample_poly

from ai.ai_runtime.utils import audio_utils
from ai.ai_runtime.utils.paths import get_speaker_separator_model_path
from ai.ai_runtime.utils.target_speaker import (
    DEFAULT_TARGET_SPEAKER_ENGINE,
    normalize_target_speaker_engine,
)

logger = logging.getLogger(__name__)

HF_REPO = "swc2/TSExcalibur"
SOURCE_REPO = "https://github.com/youzhenghai/TSExcalibur.git"
DEFAULT_CHECKPOINT = "DPRNN_TSE/LibriMix_Clean/Origin_mixing/best_model.pth"
DEFAULT_SAMPLE_RATE = 8_000
CLEARVOICE_SAMPLE_RATE = 16_000
AI_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = AI_ROOT.parent
DEFAULT_TARGET_SPEAKER_EXPORT_ROOT = AI_ROOT / "models" / "exports" / "target_speaker_windows"
DEFAULT_TSEXTRACT_ONNX = DEFAULT_TARGET_SPEAKER_EXPORT_ROOT / "tsextract" / "tsextract_fp32.onnx"
DEFAULT_TSEXTRACT_BUNDLE_ONNX = (
    DEFAULT_TARGET_SPEAKER_EXPORT_ROOT
    / "windows_bundle_slim"
    / "tsextract_onnx"
    / "tsextract_fp32.onnx"
)
DEFAULT_CLEARVOICE_BUNDLE = (
    DEFAULT_TARGET_SPEAKER_EXPORT_ROOT
    / "windows_bundle_slim"
    / "clearvoice_native"
)


@dataclass(frozen=True)
class TargetSpeakerExtractionResult:
    """Output bundle for target-speaker extraction."""

    audio: np.ndarray
    sample_rate: int
    model_sample_rate: int
    engine: str
    speaker_logits_shape: tuple[int, ...] | None = None


class TargetSpeakerSeparator:
    """Extract the speaker matching a short reference clip from a mixture.

    Four engines are supported:
    ``clearvoice`` runs the native slower/high-quality separation plus speaker
    matching pipeline. ``clearvoice_bundle`` runs the packaged native bundle.
    ``tsextract`` runs the faster 8 kHz TSExcalibur model. ``tsextract_onnx``
    runs the exported fixed-window ONNX artifact.
    The public API accepts and returns the runtime sample rate used by the rest
    of ``ai_runtime``.
    """

    def __init__(
        self,
        model_dir: Optional[Union[str, Path]] = None,
        checkpoint_path: Optional[Union[str, Path]] = None,
        checkpoint_name: str = DEFAULT_CHECKPOINT,
        device: Optional[str] = None,
        engine: str = DEFAULT_TARGET_SPEAKER_ENGINE,
    ) -> None:
        self.engine = normalize_target_speaker_engine(engine)
        if self.engine == "clearvoice_bundle":
            self.model_dir = (
                Path(model_dir).resolve()
                if model_dir
                else DEFAULT_CLEARVOICE_BUNDLE.resolve()
            )
        else:
            self.model_dir = (
                Path(model_dir).resolve()
                if model_dir
                else get_speaker_separator_model_path().resolve()
            )
        self.checkpoint_path = Path(checkpoint_path) if checkpoint_path else None
        self.checkpoint_name = checkpoint_name
        self.device = device
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self._model: Any | None = None
        self._model_args: dict[str, Any] = {}
        self._onnx_session: Any | None = None
        self._onnx_metadata: dict[str, Any] = {}

    @property
    def cache_root(self) -> Path:
        return self.model_dir / "models" / "huggingface"

    @property
    def source_dir(self) -> Path:
        return self.model_dir / "models" / "sources" / "TSExcalibur"

    def extract(
        self,
        audio: np.ndarray,
        sample_rate: int,
        reference_audio: Optional[np.ndarray] = None,
        reference_sample_rate: Optional[int] = None,
        *,
        reference_path: Optional[Union[str, Path]] = None,
    ) -> np.ndarray:
        """Return only the extracted target speaker audio."""
        return self.extract_with_details(
            audio=audio,
            sample_rate=sample_rate,
            reference_audio=reference_audio,
            reference_sample_rate=reference_sample_rate,
            reference_path=reference_path,
        ).audio

    def extract_with_details(
        self,
        audio: np.ndarray,
        sample_rate: int,
        reference_audio: Optional[np.ndarray] = None,
        reference_sample_rate: Optional[int] = None,
        *,
        reference_path: Optional[Union[str, Path]] = None,
    ) -> TargetSpeakerExtractionResult:
        """Extract target speaker audio and preserve the input layout."""
        if self.engine in {"clearvoice", "clearvoice_bundle"}:
            return self._extract_clearvoice_with_details(
                audio=audio,
                sample_rate=sample_rate,
                reference_audio=reference_audio,
                reference_sample_rate=reference_sample_rate,
                reference_path=reference_path,
            )
        if self.engine == "tsextract_onnx":
            return self._extract_tsextract_onnx_with_details(
                audio=audio,
                sample_rate=sample_rate,
                reference_audio=reference_audio,
                reference_sample_rate=reference_sample_rate,
                reference_path=reference_path,
            )
        return self._extract_tsextract_with_details(
            audio=audio,
            sample_rate=sample_rate,
            reference_audio=reference_audio,
            reference_sample_rate=reference_sample_rate,
            reference_path=reference_path,
        )

    def _extract_tsextract_with_details(
        self,
        audio: np.ndarray,
        sample_rate: int,
        reference_audio: Optional[np.ndarray] = None,
        reference_sample_rate: Optional[int] = None,
        *,
        reference_path: Optional[Union[str, Path]] = None,
    ) -> TargetSpeakerExtractionResult:
        """Extract target speaker with the fast TSExcalibur path."""
        original = np.asarray(audio, dtype=np.float32)
        if reference_audio is None:
            if reference_path is None:
                raise ValueError("tsextract target-speaker engine needs a reference audio/path.")
            reference_audio, reference_sample_rate = self.load_reference_file(reference_path)
        elif reference_sample_rate is None:
            reference_sample_rate = sample_rate
        reference = np.asarray(reference_audio, dtype=np.float32)
        target_len = audio_utils.get_target_length(original)

        mixture_mono = self._to_mono(original)
        reference_mono = self._to_mono(reference)

        mixture_model_sr = self._resample(mixture_mono, sample_rate, self.sample_rate)
        reference_model_sr = self._resample(
            reference_mono,
            reference_sample_rate,
            self.sample_rate,
        )

        estimated_model_sr, speaker_logits_shape = self._run_model(
            mixture_model_sr,
            reference_model_sr,
        )
        estimated = self._resample(estimated_model_sr, self.sample_rate, sample_rate)
        estimated = audio_utils.enforce_length(
            np.asarray(estimated, dtype=np.float32).reshape(-1),
            target_len,
        )
        return TargetSpeakerExtractionResult(
            audio=self._match_input_layout(estimated, original),
            sample_rate=sample_rate,
            model_sample_rate=self.sample_rate,
            engine=self.engine,
            speaker_logits_shape=speaker_logits_shape,
        )

    def _extract_tsextract_onnx_with_details(
        self,
        audio: np.ndarray,
        sample_rate: int,
        reference_audio: Optional[np.ndarray] = None,
        reference_sample_rate: Optional[int] = None,
        *,
        reference_path: Optional[Union[str, Path]] = None,
    ) -> TargetSpeakerExtractionResult:
        """Extract target speaker with the exported fixed-window TSExtract ONNX."""
        original = np.asarray(audio, dtype=np.float32)
        if reference_audio is None:
            if reference_path is None:
                raise ValueError("tsextract_onnx target-speaker engine needs a reference audio/path.")
            reference_audio, reference_sample_rate = self.load_reference_file(reference_path)
        elif reference_sample_rate is None:
            reference_sample_rate = sample_rate

        self._lazy_load_onnx()
        reference = np.asarray(reference_audio, dtype=np.float32)
        target_len = audio_utils.get_target_length(original)
        mixture_model_sr = self._resample(self._to_mono(original), sample_rate, self.sample_rate)
        reference_model_sr = self._resample(
            self._to_mono(reference),
            int(reference_sample_rate),
            self.sample_rate,
        )

        estimated_model_sr = self._run_onnx_model(mixture_model_sr, reference_model_sr)
        estimated = self._resample(estimated_model_sr, self.sample_rate, sample_rate)
        estimated = audio_utils.enforce_length(
            np.asarray(estimated, dtype=np.float32).reshape(-1),
            target_len,
        )
        return TargetSpeakerExtractionResult(
            audio=self._match_input_layout(estimated, original),
            sample_rate=sample_rate,
            model_sample_rate=self.sample_rate,
            engine=self.engine,
            speaker_logits_shape=None,
        )

    def _extract_clearvoice_with_details(
        self,
        audio: np.ndarray,
        sample_rate: int,
        reference_audio: Optional[np.ndarray] = None,
        reference_sample_rate: Optional[int] = None,
        *,
        reference_path: Optional[Union[str, Path]] = None,
    ) -> TargetSpeakerExtractionResult:
        """Extract target speaker with the native ClearVoice separate+match path."""
        original = np.asarray(audio, dtype=np.float32)
        if reference_audio is None and reference_path is None:
            raise ValueError("clearvoice target-speaker engine needs a reference audio/path.")
        if reference_audio is not None and reference_sample_rate is None:
            reference_sample_rate = sample_rate

        target_len = audio_utils.get_target_length(original)
        estimated, model_sample_rate = self._run_clearvoice(
            audio=original,
            sample_rate=sample_rate,
            reference_audio=reference_audio,
            reference_sample_rate=reference_sample_rate,
            reference_path=reference_path,
        )
        estimated = self._resample(estimated, model_sample_rate, sample_rate)
        estimated = audio_utils.enforce_length(
            np.asarray(estimated, dtype=np.float32).reshape(-1),
            target_len,
        )
        return TargetSpeakerExtractionResult(
            audio=self._match_input_layout(estimated, original),
            sample_rate=sample_rate,
            model_sample_rate=model_sample_rate,
            engine=self.engine,
            speaker_logits_shape=None,
        )

    @staticmethod
    def load_reference_file(path: Union[str, Path]) -> tuple[np.ndarray, int]:
        """Load a mono/stereo reference file for target-speaker extraction."""
        try:
            import soundfile as sf
        except ImportError as exc:  # pragma: no cover - dependency issue
            raise ImportError(
                "soundfile is required to load a target speaker reference path."
            ) from exc

        audio, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
        return np.asarray(audio, dtype=np.float32), int(sample_rate)

    def _run_model(
        self,
        mixture_model_sr: np.ndarray,
        reference_model_sr: np.ndarray,
    ) -> tuple[np.ndarray, tuple[int, ...] | None]:
        self._lazy_load_model()

        import torch

        device = self._resolve_device(torch)
        mix_tensor = torch.as_tensor(
            mixture_model_sr,
            dtype=torch.float32,
            device=device,
        ).unsqueeze(0)
        ref_tensor = torch.as_tensor(
            reference_model_sr,
            dtype=torch.float32,
            device=device,
        ).unsqueeze(0)
        ref_len = torch.tensor([ref_tensor.shape[-1]], dtype=torch.long, device=device)

        with torch.no_grad():
            estimated, speaker_logits = self._model(mix_tensor, ref_tensor, ref_len)
        estimated_np = estimated.squeeze().detach().cpu().numpy().astype(np.float32)
        logits_shape = tuple(int(dim) for dim in speaker_logits.shape)
        return estimated_np, logits_shape

    def _run_onnx_model(
        self,
        mixture_model_sr: np.ndarray,
        reference_model_sr: np.ndarray,
    ) -> np.ndarray:
        self._lazy_load_onnx()
        session = self._onnx_session
        if session is None:  # pragma: no cover - guarded by _lazy_load_onnx
            raise RuntimeError("TSExtract ONNX session was not initialized.")

        mixture_samples = int(self._onnx_metadata.get("mixture_samples", 80000) or 80000)
        reference_samples = int(self._onnx_metadata.get("reference_samples", 24000) or 24000)
        reference_fixed, reference_original_samples = self._pad_or_trim_model_audio(
            reference_model_sr,
            reference_samples,
        )
        reference_length = np.asarray(
            [min(reference_original_samples, reference_samples)],
            dtype=np.int64,
        )
        mixture = np.asarray(mixture_model_sr, dtype=np.float32).reshape(-1)
        if mixture.size == 0:
            return np.zeros(0, dtype=np.float32)

        chunks: list[np.ndarray] = []
        for start in range(0, mixture.size, mixture_samples):
            chunk = mixture[start : start + mixture_samples]
            valid_length = int(chunk.size)
            padded, _ = self._pad_or_trim_model_audio(chunk, mixture_samples)
            output = session.run(
                None,
                {
                    "mixture": padded.reshape(1, -1).astype(np.float32, copy=False),
                    "reference": reference_fixed.reshape(1, -1).astype(np.float32, copy=False),
                    "reference_length": reference_length,
                },
            )[0]
            chunks.append(np.asarray(output, dtype=np.float32).reshape(-1)[:valid_length])
        return np.concatenate(chunks).astype(np.float32, copy=False)

    def _run_clearvoice(
        self,
        *,
        audio: np.ndarray,
        sample_rate: int,
        reference_audio: Optional[np.ndarray],
        reference_sample_rate: Optional[int],
        reference_path: Optional[Union[str, Path]],
    ) -> tuple[np.ndarray, int]:
        """Run the SpeakerSeperator native extraction pipeline from temp WAVs."""
        if self.engine == "clearvoice_bundle":
            return self._run_clearvoice_bundle(
                audio=audio,
                sample_rate=sample_rate,
                reference_audio=reference_audio,
                reference_sample_rate=reference_sample_rate,
                reference_path=reference_path,
            )
        self._ensure_speechthing_on_path()

        resolved_reference_path: Path | None = None
        if reference_path is not None:
            candidate = Path(reference_path)
            resolved_reference_path = (
                candidate.resolve()
                if candidate.is_absolute()
                else (Path.cwd() / candidate).resolve()
            )

        from speechthing.pipeline import extract_target

        temp_root = self.model_dir / "outputs" / "_ai_runtime_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="clearvoice_",
            dir=str(temp_root),
            ignore_cleanup_errors=True,
        ) as tmp:
            tmp_dir = Path(tmp)
            mixture_path = tmp_dir / "mixture.wav"
            self._write_temp_wav(mixture_path, self._to_mono(audio), sample_rate)

            if resolved_reference_path is None:
                if reference_audio is None or reference_sample_rate is None:
                    raise ValueError(
                        "clearvoice target-speaker engine needs reference_audio "
                        "with reference_sample_rate when no reference_path is provided."
                    )
                resolved_reference_path = tmp_dir / "reference.wav"
                self._write_temp_wav(
                    resolved_reference_path,
                    self._to_mono(np.asarray(reference_audio, dtype=np.float32)),
                    int(reference_sample_rate),
                )

            out_dir = tmp_dir / "clearvoice"
            previous_cwd = Path.cwd()
            os.chdir(self.model_dir)
            try:
                report = extract_target(
                    mixture=mixture_path,
                    reference=resolved_reference_path,
                    out_dir=out_dir,
                    device=self._resolve_clearvoice_device(),
                    enhance=False,
                )
            finally:
                os.chdir(previous_cwd)

            target_path = Path(report.get("target_path", out_dir / "target.wav"))
            target_audio, target_sample_rate = self.load_reference_file(target_path)
            return self._to_mono(target_audio), int(target_sample_rate)

    def _run_clearvoice_bundle(
        self,
        *,
        audio: np.ndarray,
        sample_rate: int,
        reference_audio: Optional[np.ndarray],
        reference_sample_rate: Optional[int],
        reference_path: Optional[Union[str, Path]],
    ) -> tuple[np.ndarray, int]:
        """Run a packaged ClearVoice bundle through its own Python runtime."""
        self._ensure_speechthing_on_path()
        python_exe = self._resolve_clearvoice_bundle_python()
        env = self._clearvoice_bundle_env()

        resolved_reference_path: Path | None = None
        if reference_path is not None:
            candidate = Path(reference_path)
            resolved_reference_path = (
                candidate.resolve()
                if candidate.is_absolute()
                else (Path.cwd() / candidate).resolve()
            )

        temp_root = self.model_dir / "outputs" / "_ai_runtime_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="clearvoice_bundle_",
            dir=str(temp_root),
            ignore_cleanup_errors=True,
        ) as tmp:
            tmp_dir = Path(tmp)
            mixture_path = tmp_dir / "mixture.wav"
            self._write_temp_wav(mixture_path, self._to_mono(audio), sample_rate)

            if resolved_reference_path is None:
                if reference_audio is None or reference_sample_rate is None:
                    raise ValueError(
                        "clearvoice_bundle target-speaker engine needs reference_audio "
                        "with reference_sample_rate when no reference_path is provided."
                    )
                resolved_reference_path = tmp_dir / "reference.wav"
                self._write_temp_wav(
                    resolved_reference_path,
                    self._to_mono(np.asarray(reference_audio, dtype=np.float32)),
                    int(reference_sample_rate),
                )

            out_dir = tmp_dir / "clearvoice"
            command = [
                str(python_exe),
                "-m",
                "speechthing.cli",
                "--debug",
                "extract",
                "--mixture",
                str(mixture_path.resolve()),
                "--reference",
                str(resolved_reference_path.resolve()),
                "--out",
                str(out_dir.resolve()),
                "--device",
                self._resolve_clearvoice_device(),
            ]
            completed = subprocess.run(
                command,
                cwd=str(self.model_dir),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    "ClearVoice bundle extraction failed.\n"
                    f"command: {' '.join(command)}\n"
                    f"stdout:\n{completed.stdout}\n"
                    f"stderr:\n{completed.stderr}"
                )

            target_path = out_dir / "target.wav"
            if not target_path.exists():
                raise RuntimeError(
                    f"ClearVoice bundle finished but did not write target.wav at {target_path}"
                )
            target_audio, target_sample_rate = self.load_reference_file(target_path)
            return self._to_mono(target_audio), int(target_sample_rate)

    def _lazy_load_model(self) -> None:
        if self._model is not None:
            return

        import torch

        checkpoint_path = self._resolve_checkpoint_path()
        self._ensure_source_on_path()
        from calibur.model.dprnn_spe import DPRNNSpeTasNet

        device = self._resolve_device(torch)
        logger.info("Loading target-speaker separator from %s on %s", checkpoint_path, device)
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
        model_args = dict(checkpoint["model_args"])
        model_args.pop("n_src", None)
        model = DPRNNSpeTasNet(**model_args)
        model.load_state_dict(checkpoint["state_dict"])
        model.to(device)
        model.eval()

        self._model = model
        self._model_args = model_args
        self.sample_rate = int(model_args.get("sample_rate", DEFAULT_SAMPLE_RATE))

    def _lazy_load_onnx(self) -> None:
        if self._onnx_session is not None:
            return
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - dependency issue
            raise ImportError(
                "onnxruntime is required for target_speaker_engine=tsextract_onnx."
            ) from exc

        onnx_path = self._resolve_onnx_path()
        self._check_onnx_sidecars(onnx_path)
        manifest_path = onnx_path.with_suffix(".manifest.json")
        metadata: dict[str, Any] = {}
        if manifest_path.exists():
            metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.sample_rate = int(metadata.get("sample_rate_hz", DEFAULT_SAMPLE_RATE) or DEFAULT_SAMPLE_RATE)
        self._onnx_metadata = metadata

        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        providers = self._resolve_onnx_providers(ort)
        self._onnx_session = ort.InferenceSession(
            str(onnx_path),
            sess_options=options,
            providers=providers,
        )
        logger.info(
            "Loaded target-speaker TSExtract ONNX from %s with providers: %s",
            onnx_path,
            self._onnx_session.get_providers(),
        )

    def _resolve_checkpoint_path(self) -> Path:
        if self.checkpoint_path is not None:
            return self.checkpoint_path

        self._configure_runtime_cache()
        local = self._find_local_checkpoint()
        if local is not None:
            return local

        try:
            from huggingface_hub import hf_hub_download
        except ImportError as exc:  # pragma: no cover - dependency issue
            raise ImportError(
                "huggingface_hub is required to download the TSExcalibur checkpoint."
            ) from exc

        logger.info("Downloading target-speaker checkpoint %s from %s", self.checkpoint_name, HF_REPO)
        return Path(
            hf_hub_download(
                HF_REPO,
                self.checkpoint_name,
                cache_dir=str(self.cache_root / "hub"),
            ),
        )

    def _find_local_checkpoint(self) -> Path | None:
        snapshots_dir = self.cache_root / "hub" / "models--swc2--TSExcalibur" / "snapshots"
        if not snapshots_dir.exists():
            return None
        candidates = [
            path
            for path in snapshots_dir.glob(f"*/{self.checkpoint_name}")
            if path.exists()
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda path: path.stat().st_mtime)

    def _resolve_onnx_path(self) -> Path:
        if self.checkpoint_path is not None:
            requested = Path(self.checkpoint_path)
            if not requested.exists():
                raise FileNotFoundError(f"TSExtract ONNX was not found: {requested}")
            return requested.resolve()
        for candidate in (DEFAULT_TSEXTRACT_BUNDLE_ONNX, DEFAULT_TSEXTRACT_ONNX):
            if candidate.exists():
                return candidate.resolve()
        raise FileNotFoundError(
            "TSExtract ONNX was not found. Pass it via --target-speaker-checkpoint "
            f"or place it at {DEFAULT_TSEXTRACT_BUNDLE_ONNX}."
        )

    def _check_onnx_sidecars(self, onnx_path: Path) -> None:
        expected = onnx_path.with_name(onnx_path.name + ".data")
        if expected.exists():
            return
        try:
            payload = onnx_path.read_bytes()
        except OSError:
            return
        marker = (onnx_path.name + ".data").encode("utf-8")
        if marker in payload:
            raise FileNotFoundError(
                "TSExtract ONNX external data file is missing: "
                f"{expected}. Repackage the Windows bundle or copy this sidecar next "
                "to the .onnx file."
            )

    def _resolve_onnx_providers(self, ort_module: Any) -> list[str]:
        requested = str(self.device or "cpu").strip().casefold()
        available = set(ort_module.get_available_providers())
        providers: list[str] = []
        if requested.startswith("cuda") and "CUDAExecutionProvider" in available:
            providers.append("CUDAExecutionProvider")
        providers.append("CPUExecutionProvider")
        return [provider for provider in providers if provider in available]

    def _configure_runtime_cache(self) -> None:
        cache_root = self.cache_root.resolve()
        hub_cache = cache_root / "hub"
        xet_cache = cache_root / "xet"
        hub_cache.mkdir(parents=True, exist_ok=True)
        xet_cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(cache_root))
        os.environ.setdefault("HF_HUB_CACHE", str(hub_cache))
        os.environ.setdefault("HF_XET_CACHE", str(xet_cache))
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    def _configure_clearvoice_bundle_env(self) -> None:
        cache_root = self.cache_root.resolve()
        hub_cache = cache_root / "hub"
        xet_cache = cache_root / "xet"
        hub_cache.mkdir(parents=True, exist_ok=True)
        xet_cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(cache_root))
        os.environ.setdefault("HF_HUB_CACHE", str(hub_cache))
        os.environ.setdefault("HF_XET_CACHE", str(xet_cache))
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    def _clearvoice_bundle_env(self) -> dict[str, str]:
        self._configure_clearvoice_bundle_env()
        env = os.environ.copy()
        source = str((self.model_dir / "src").resolve())
        env["PYTHONPATH"] = (
            source
            if not env.get("PYTHONPATH")
            else source + os.pathsep + str(env["PYTHONPATH"])
        )
        cache_root = (self.model_dir / "models" / "huggingface").resolve()
        env["HF_HOME"] = str(cache_root)
        env["HF_HUB_CACHE"] = str(cache_root / "hub")
        env["HF_XET_CACHE"] = str(cache_root / "xet")
        env["HF_HUB_DISABLE_XET"] = "1"
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        return env

    def _resolve_clearvoice_bundle_python(self) -> Path:
        bundle_python = self.model_dir / ".venv" / "Scripts" / "python.exe"
        if bundle_python.exists():
            return bundle_python.resolve()
        if module_available("clearvoice") and module_available("speechbrain"):
            return Path(sys.executable)

        installer = self.model_dir / "install_clearvoice_runtime.ps1"
        install_hint = (
            f"cd {self.model_dir}\n"
            ".\\install_clearvoice_runtime.ps1 -CpuTorch\n"
            f"cd {PROJECT_ROOT}"
        )
        if not installer.exists():
            install_hint = (
                "The bundle installer is missing. Repackage the ClearVoice bundle, "
                "or install clearvoice and speechbrain in the current Python env."
            )
        raise RuntimeError(
            "ClearVoice bundle runtime is not installed. The suppression pipeline "
            "uses the bundle's own .venv for end-user testing, and this folder does "
            f"not contain {bundle_python}.\nRun this one-time setup yourself:\n{install_hint}"
        )

    def _ensure_source_on_path(self) -> None:
        source_file = self.source_dir / "calibur" / "model" / "dprnn_spe.py"
        if not source_file.exists():
            self._clone_source_repo()

        source = str(self.source_dir.resolve())
        if source not in sys.path:
            sys.path.insert(0, source)

    def _ensure_speechthing_on_path(self) -> None:
        source = self.model_dir / "src"
        package = source / "speechthing" / "pipeline.py"
        if not package.exists():
            raise FileNotFoundError(
                "SpeakerSeperator speechthing package was not found at "
                f"{package}. Use --target-speaker-model-dir to point at the project."
            )
        source_text = str(source.resolve())
        if source_text not in sys.path:
            sys.path.insert(0, source_text)

    def _clone_source_repo(self) -> None:
        git = shutil.which("git")
        if git is None:
            raise RuntimeError(
                "Git is required to fetch TSExcalibur source code. Clone "
                f"{SOURCE_REPO} into {self.source_dir}."
            )

        self.source_dir.parent.mkdir(parents=True, exist_ok=True)
        command = [
            git,
            "-c",
            "http.sslBackend=openssl",
            "clone",
            SOURCE_REPO,
            str(self.source_dir),
        ]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            raise RuntimeError(
                "Failed to clone TSExcalibur source code.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )

    def _resolve_device(self, torch_module: Any) -> str:
        if self.device:
            return str(self.device)
        if torch_module.cuda.is_available():
            self.device = "cuda"
        else:
            self.device = "cpu"
        return self.device

    def _resolve_clearvoice_device(self) -> str:
        if self.device:
            requested = str(self.device).strip().casefold()
            return "cuda" if requested.startswith("cuda") else "cpu"
        try:
            import torch

            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            self.device = "cpu"
        return self.device

    @staticmethod
    def _write_temp_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
        try:
            import soundfile as sf
        except ImportError as exc:  # pragma: no cover - dependency issue
            raise ImportError("soundfile is required for ClearVoice target extraction.") from exc

        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(
            str(path),
            np.clip(np.asarray(audio, dtype=np.float32).reshape(-1), -1.0, 1.0),
            int(sample_rate),
            subtype="PCM_16",
        )

    @staticmethod
    def _to_mono(audio: np.ndarray) -> np.ndarray:
        audio = np.nan_to_num(
            np.asarray(audio, dtype=np.float32),
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )
        if audio.ndim == 1:
            return audio.reshape(-1)
        if audio.ndim != 2:
            raise ValueError("audio must be a 1D mono array or a 2D stereo/channel array")
        if audio.shape[0] <= 8 and audio.shape[1] > audio.shape[0]:
            return audio.mean(axis=0).reshape(-1)
        return audio.mean(axis=1).reshape(-1)

    @staticmethod
    def _match_input_layout(mono_audio: np.ndarray, reference_layout: np.ndarray) -> np.ndarray:
        mono_audio = np.asarray(mono_audio, dtype=np.float32).reshape(-1)
        if reference_layout.ndim == 1:
            return mono_audio.astype(reference_layout.dtype, copy=False)
        if reference_layout.shape[0] <= 8 and reference_layout.shape[1] > reference_layout.shape[0]:
            channels = reference_layout.shape[0]
            return np.tile(mono_audio.reshape(1, -1), (channels, 1)).astype(
                reference_layout.dtype,
                copy=False,
            )
        channels = reference_layout.shape[1]
        return np.tile(mono_audio.reshape(-1, 1), (1, channels)).astype(
            reference_layout.dtype,
            copy=False,
        )

    @staticmethod
    def _resample(audio: np.ndarray, old_sr: int, new_sr: int) -> np.ndarray:
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if int(old_sr) == int(new_sr):
            return audio
        ratio = Fraction(int(new_sr), int(old_sr)).limit_denominator()
        return resample_poly(audio, ratio.numerator, ratio.denominator).astype(np.float32)

    @staticmethod
    def _pad_or_trim_model_audio(audio: np.ndarray, target_samples: int) -> tuple[np.ndarray, int]:
        array = np.asarray(audio, dtype=np.float32).reshape(-1)
        original_samples = int(array.size)
        target_samples = int(target_samples)
        if array.size >= target_samples:
            return array[:target_samples].astype(np.float32, copy=False), original_samples
        padded = np.zeros(target_samples, dtype=np.float32)
        padded[: array.size] = array
        return padded, original_samples


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


__all__ = [
    "CLEARVOICE_SAMPLE_RATE",
    "DEFAULT_CHECKPOINT",
    "DEFAULT_SAMPLE_RATE",
    "TargetSpeakerExtractionResult",
    "TargetSpeakerSeparator",
]
