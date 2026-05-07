"""
CodecSep inference wrapper for the Semantic Noise Suppressor.

Provides the same lazy-loading, resample, and numpy-in / numpy-out contract as
the Waveformer and legacy-named AudioSep open-vocabulary separators.
"""

from __future__ import annotations

import inspect
import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

import numpy as np
import torch
import torch.nn.functional as F
import torchaudio
import yaml
from scipy import signal as scipy_signal

from ai.ai_runtime.separation.codecsep_query import (
    CodecSepCandidateScore,
    CodecSepQueryPlan,
    CodecSepQueryResult,
)
from ai.ai_runtime.utils.codecsep import (
    collapse_codecsep_prompt_value,
    flatten_codecsep_prompt_segments,
    normalize_codecsep_prompt_map,
    normalize_codecsep_prompt_value,
)
from ai.ai_runtime.utils.paths import (
    get_codecsep_clap_checkpoint_path,
    get_codecsep_default_run_dir,
    resolve_codecsep_checkpoint_path,
)

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000
STEMS: tuple[str, ...] = ("speech", "music", "sfx")
DEFAULT_CHECKPOINT_SOURCE = get_codecsep_default_run_dir()

DEFAULT_PROMPTS: Dict[str, list[str]] = {
    "speech": ["speech"],
    "music": ["music"],
    "sfx": ["sound effects, environmental sounds, noise"],
}

PROMPT_TEMPLATE_KEYWORDS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("dog", "bark", "barking", "canine"),
        (
            "a dog barking in the distance",
            "a dog barking loudly",
            "canine vocalization, an animal sound",
        ),
    ),
    (
        ("keyboard", "typing", "keystroke", "key click", "key clicks"),
        (
            "keyboard typing sounds, key clicks",
            "mechanical keyboard keystrokes",
            "fingers pressing keyboard keys rapidly",
        ),
    ),
    (
        ("phone", "telephone", "ring", "ringing", "notification"),
        (
            "a telephone ringing",
            "phone notification sounds",
            "an alert tone from a mobile phone",
        ),
    ),
    (
        ("siren", "ambulance", "emergency"),
        (
            "an ambulance siren in the distance",
            "a loud emergency vehicle siren",
            "wailing siren sounds",
        ),
    ),
    (
        ("alarm", "beep", "beeping"),
        (
            "a fire alarm beeping",
            "warning alarm sounds",
            "repeating alert beeps",
        ),
    ),
    (
        ("wind", "gust", "air"),
        (
            "gusting wind noise",
            "strong wind blowing outdoors",
            "air rushing in the background",
        ),
    ),
)


class _ClapSimilarityScorer:
    """Small CLAP wrapper used for reference-free query ranking."""

    def __init__(
        self,
        *,
        checkpoint_path: Path,
        amodel: str,
        tmodel: str,
        enable_fusion: bool,
        device: torch.device,
    ) -> None:
        self.device = device
        self.checkpoint_path = checkpoint_path
        self.enable_fusion = enable_fusion
        self._create_model, self._load_state_dict, self._get_audio_features = self._import_clap_helpers()
        from transformers import RobertaTokenizer

        self.model, self.model_cfg = self._create_model(
            amodel,
            tmodel,
            precision="fp32",
            device=device,
            enable_fusion=enable_fusion,
            fusion_type="aff_2d" if enable_fusion else "None",
        )
        state_dict = self._load_state_dict(str(checkpoint_path), skip_params=True)
        missing, unexpected = self.model.load_state_dict(state_dict, strict=False)
        if missing:
            logger.debug("CLAP scorer missing keys: %s", missing)
        if unexpected:
            logger.debug("CLAP scorer unexpected keys: %s", unexpected)
        self.model = self.model.to(device).eval()
        self._tokenizer = RobertaTokenizer.from_pretrained("roberta-base")
        self._audio_resampler: dict[int, torchaudio.transforms.Resample] = {}

    @staticmethod
    def _import_clap_helpers():
        spec = importlib.util.find_spec("laion_clap")
        if spec is None or not spec.submodule_search_locations:
            raise ImportError("laion_clap is required for CodecSep experimental-search scoring.")

        laion_clap_dir = Path(next(iter(spec.submodule_search_locations))).resolve()
        clap_module_root = str(laion_clap_dir)
        if clap_module_root not in sys.path:
            sys.path.insert(0, clap_module_root)

        factory_module = importlib.import_module("clap_module.factory")
        training_data_module = importlib.import_module("training.data")
        return (
            getattr(factory_module, "create_model"),
            getattr(factory_module, "load_state_dict"),
            getattr(training_data_module, "get_audio_features"),
        )

    def _tokenize(self, prompts: Sequence[str]) -> Mapping[str, torch.Tensor]:
        return self._tokenizer(
            list(prompts),
            padding="max_length",
            truncation=True,
            max_length=77,
            return_tensors="pt",
        )

    def encode_text(self, prompts: Sequence[str]) -> torch.Tensor:
        with torch.no_grad():
            tokens = self._tokenize(prompts)
            return self.model.get_text_embedding(tokens).detach()

    def encode_audio(self, audio: np.ndarray, sample_rate: int) -> torch.Tensor:
        waveform = np.asarray(audio, dtype=np.float32).squeeze()
        if waveform.ndim != 1:
            waveform = waveform.reshape(-1)
        tensor = torch.from_numpy(waveform).float()
        if sample_rate != 48000:
            if sample_rate not in self._audio_resampler:
                self._audio_resampler[sample_rate] = torchaudio.transforms.Resample(
                    orig_freq=sample_rate,
                    new_freq=48000,
                )
            tensor = self._audio_resampler[sample_rate](tensor.unsqueeze(0)).squeeze(0)

        # Match the official CLAP hook behavior.
        tensor = torch.clamp(tensor, -1.0, 1.0)
        tensor = torch.round(tensor * 32767.0) / 32767.0
        audio_input = [
            self._get_audio_features(
                {},
                tensor,
                480000,
                data_truncating="fusion" if self.enable_fusion else "rand_trunc",
                data_filling="repeatpad",
                audio_cfg=self.model_cfg["audio_cfg"],
                require_grad=False,
            )
        ]
        with torch.no_grad():
            return self.model.get_audio_embedding(audio_input).detach()

    def cosine_similarity(
        self,
        *,
        audio: np.ndarray,
        sample_rate: int,
        prompts: Sequence[str],
    ) -> float:
        if not prompts:
            return 0.0
        audio_embed = F.normalize(self.encode_audio(audio, sample_rate), dim=-1)
        text_embed = F.normalize(self.encode_text(prompts), dim=-1)
        return float((audio_embed @ text_embed.transpose(0, 1)).max().detach().cpu())


class CodecSepSeparator:
    """Wrapper around the vendored CodecSep model.

    Interface mirrors ``WaveformerSeparator`` where possible, but
    ``separate()`` accepts *stem names* (speech / music / sfx) rather
    than Waveformer-style target labels.
    """

    TARGET_SAMPLE_RATE = TARGET_SAMPLE_RATE
    STEMS = STEMS

    def __init__(
        self,
        checkpoint_path: Optional[Union[str, Path]] = None,
        device: Optional[Union[str, torch.device]] = None,
        prompts: Optional[Dict[str, list[str]]] = None,
    ) -> None:
        self.device = torch.device(device) if device else self._auto_device()
        self.checkpoint_path = Path(checkpoint_path) if checkpoint_path else self._default_checkpoint_path()
        self.resolved_checkpoint_path: Path | None = None
        self.prompts = normalize_codecsep_prompt_map(prompts or dict(DEFAULT_PROMPTS))
        self._model = None
        self._mag_normalizer = None
        self._resample_in: dict = {}
        self._resample_out: dict = {}
        self._clap_scorer: _ClapSimilarityScorer | None = None
        self._clap_scorer_cfg: dict[str, object] = {}
        self._clap_scorer_disabled = False
        self._clap_scorer_error: str | None = None
        self._input_volume_norm = None
        self._mix_lufs_target_db: float | None = None
        self._peak_norm_db: float | None = None
        self._peak_norm_gain: float | None = None
        self._logged_inference_norm_cfg = False
        self._conditioning_mode: str = "prompt"
        self._num_classes: int = 0

    @staticmethod
    def _auto_device() -> torch.device:
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")

    @staticmethod
    def _default_checkpoint_path() -> Path:
        return DEFAULT_CHECKPOINT_SOURCE

    @property
    def conditioning_mode(self) -> str:
        return self._conditioning_mode

    @property
    def num_classes(self) -> int:
        return self._num_classes

    def supports_fixed_category(self) -> bool:
        self._lazy_load_model()
        return self.conditioning_mode == "class_id"

    def _lazy_load_model(self) -> None:
        if self._model is not None:
            return

        resolved_checkpoint = resolve_codecsep_checkpoint_path(self.checkpoint_path)
        self.resolved_checkpoint_path = resolved_checkpoint

        if not resolved_checkpoint.exists():
            raise FileNotFoundError(
                f"CodecSep checkpoint not found for source {self.checkpoint_path}. "
                f"Resolved candidate path: {resolved_checkpoint}. "
                "Expected a cleaned CodecSep bundle under "
                "ai/models/CodecSep/Runs/CodecSep_DNR_USS_ModelBundle "
                "or a direct checkpoint family such as checkpoints/best_accelerate_resume_state "
                "or checkpoints/final_weights."
            )

        self._ensure_accelerate_logging_state()
        CodecSep = self._resolve_model_class()
        sample_rate, config_kwargs, inference_cfg = self._load_model_config(resolved_checkpoint)

        logger.info("Loading CodecSep model from %s to %s ...",
                     resolved_checkpoint, self.device)

        loaded = torch.load(
            resolved_checkpoint, map_location=self.device, weights_only=False,
        )

        if isinstance(loaded, dict) and "state_dict" in loaded:
            state_dict = loaded["state_dict"]
            metadata_kwargs = loaded.get("metadata", {}).get("kwargs", {})
        else:
            state_dict = loaded
            metadata_kwargs = {}

        model_kwargs = self._merge_model_kwargs(config_kwargs, metadata_kwargs)
        self._ensure_clap_config(model_kwargs, state_dict)
        self._clap_scorer_cfg = dict(model_kwargs.get("clap") or {})

        model = self._instantiate_model(
            CodecSep,
            sample_rate=sample_rate,
            model_kwargs=model_kwargs,
        )
        self._load_model_state_dict(model, state_dict)
        model = model.to(self.device).eval()

        if self.device.type == "cpu":
            try:
                model = torch.quantization.quantize_dynamic(
                    model, {torch.nn.Linear}, dtype=torch.qint8,
                )
                logger.info("Dynamic INT8 quantization applied to CodecSep")
            except Exception as exc:
                logger.warning("Quantization failed (non-critical): %s", exc)

        self._model = model
        self._conditioning_mode = str(getattr(model, "conditioning_mode", "prompt")).strip().lower() or "prompt"
        self._num_classes = int(getattr(model, "num_classes", 0) or 0)
        self._configure_inference_normalization(
            sample_rate=sample_rate,
            inference_cfg=inference_cfg,
        )
        logger.info("CodecSep model ready (device=%s)", self.device)

    @staticmethod
    def _ensure_accelerate_logging_state() -> None:
        """Initialize Accelerate state so vendored CodecSep logging stays usable."""
        try:
            from accelerate.state import PartialState
        except Exception:
            return
        try:
            PartialState()
        except Exception as exc:
            logger.debug("CodecSep accelerate PartialState init skipped: %s", exc)

    @staticmethod
    def _merge_model_kwargs(
        config_kwargs: Mapping[str, object],
        metadata_kwargs: Mapping[str, object],
    ) -> dict[str, object]:
        merged = dict(metadata_kwargs)
        merged.update({k: v for k, v in config_kwargs.items() if v is not None})
        return merged

    @staticmethod
    def _instantiate_model(
        model_class,
        *,
        sample_rate: int,
        model_kwargs: Mapping[str, object],
    ):
        candidate_kwargs = {
            "sample_rate": sample_rate,
            "latent_dim": model_kwargs.get("latent_dim"),
            "tracks": model_kwargs.get("tracks"),
            "mode": model_kwargs.get("mode"),
            "residual_mode": model_kwargs.get("residual_mode"),
            "enc_params": model_kwargs.get("enc_params"),
            "dec_params": model_kwargs.get("dec_params"),
            "transformer_params": model_kwargs.get("transformer_params"),
            "separator_params": model_kwargs.get("separator_params"),
            "film_clip": model_kwargs.get("film_clip"),
            "normalize_prompt_embeddings": model_kwargs.get("normalize_prompt_embeddings"),
            "prompt_embed_eps": model_kwargs.get("prompt_embed_eps"),
            "enable_semantic_finite_checks": model_kwargs.get("enable_semantic_finite_checks"),
            "conditioning": model_kwargs.get("conditioning"),
            "num_classes": model_kwargs.get("num_classes"),
            "clap": model_kwargs.get("clap"),
            "pretrain": model_kwargs.get("pretrain"),
        }

        signature = inspect.signature(model_class)
        supports_var_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        if supports_var_kwargs:
            filtered_kwargs = {
                key: value for key, value in candidate_kwargs.items() if value is not None
            }
        else:
            supported_names = set(signature.parameters.keys())
            filtered_kwargs = {
                key: value
                for key, value in candidate_kwargs.items()
                if key in supported_names and value is not None
            }
        return model_class(**filtered_kwargs)

    @staticmethod
    def _normalize_load_state_dict_result(result) -> tuple[list[str], list[str]]:
        if result is None:
            return [], []
        if hasattr(result, "missing_keys") and hasattr(result, "unexpected_keys"):
            return list(result.missing_keys), list(result.unexpected_keys)
        if isinstance(result, tuple) and len(result) == 2:
            return list(result[0]), list(result[1])
        return [], []

    @staticmethod
    def _is_legacy_additive_film_checkpoint(state_dict: Mapping[str, object]) -> bool:
        has_beta = False
        has_gamma = False
        for raw_key in state_dict.keys():
            key = str(raw_key).strip()
            if not key.startswith("film."):
                continue
            if "beta" in key:
                has_beta = True
            if "gamma" in key:
                has_gamma = True
            if has_beta and has_gamma:
                return False
        return has_beta and not has_gamma

    @staticmethod
    def _is_ignorable_state_dict_key(
        key: str,
        *,
        legacy_additive_film: bool = False,
    ) -> bool:
        normalized = str(key).strip()
        if normalized.endswith("position_ids") or normalized.endswith("token_type_ids"):
            return True
        if legacy_additive_film and normalized.startswith("film.") and "gamma" in normalized:
            return True
        return normalized in {
            "film.gate1.weight",
            "film.gate1.bias",
            "film.gate2.weight",
            "film.gate2.bias",
        }

    @classmethod
    def _load_model_state_dict(cls, model, state_dict: Mapping[str, object]) -> None:
        result = model.load_state_dict(state_dict, strict=False)
        missing_keys, unexpected_keys = cls._normalize_load_state_dict_result(result)
        legacy_additive_film = cls._is_legacy_additive_film_checkpoint(state_dict)
        ignored_missing = [
            key
            for key in missing_keys
            if cls._is_ignorable_state_dict_key(
                key,
                legacy_additive_film=legacy_additive_film,
            )
        ]
        ignored_unexpected = [
            key
            for key in unexpected_keys
            if cls._is_ignorable_state_dict_key(
                key,
                legacy_additive_film=legacy_additive_film,
            )
        ]
        blocking_missing = [key for key in missing_keys if key not in ignored_missing]
        blocking_unexpected = [key for key in unexpected_keys if key not in ignored_unexpected]

        if ignored_missing:
            logger.debug("Ignoring benign missing CodecSep checkpoint keys: %s", ignored_missing)
        if ignored_unexpected:
            logger.debug("Ignoring benign unexpected CodecSep checkpoint keys: %s", ignored_unexpected)
        if legacy_additive_film and ignored_missing:
            logger.info(
                "Detected legacy additive-FiLM CodecSep checkpoint; runtime gamma FiLM layers "
                "will stay at zero-init identity."
            )

        if not blocking_missing and not blocking_unexpected:
            return

        critical_tokens = (
            "film",
            "gate",
            "class_embedding",
            "separator",
            "transformer_encoder",
            "text_encoder",
        )
        critical_missing = [
            key for key in blocking_missing if any(token in key for token in critical_tokens)
        ]
        details: list[str] = []
        if critical_missing:
            details.append(
                "missing core conditioning/separator weights: "
                + ", ".join(critical_missing[:12])
            )
        elif blocking_missing:
            details.append("missing keys: " + ", ".join(blocking_missing[:12]))
        if blocking_unexpected:
            details.append("unexpected keys: " + ", ".join(blocking_unexpected[:12]))
        raise RuntimeError(
            "CodecSep checkpoint is not architecturally compatible with the authoritative runtime model; "
            + " | ".join(details)
        )

    @staticmethod
    def _detect_clap_amodel(state_dict: dict) -> str:
        """Infer CLAP audio model type from checkpoint weight shapes.

        HTSAT-tiny has embed_dim=96, HTSAT-base has embed_dim=128.
        """
        for key, tensor in state_dict.items():
            if "audio_branch" in key and "patch_embed.proj.weight" in key:
                if hasattr(tensor, "shape") and len(tensor.shape) >= 1:
                    embed_dim = tensor.shape[0]
                    if embed_dim >= 128:
                        return "HTSAT-base"
                    return "HTSAT-tiny"
        return "HTSAT-tiny"

    @staticmethod
    def _ensure_clap_config(
        model_kwargs: dict[str, object],
        state_dict: dict,
    ) -> None:
        """Ensure model_kwargs has a valid clap config matching the checkpoint.

        If the config is missing or has the wrong audio model architecture,
        detect the correct one from the state dict and inject it.
        """
        detected_amodel = CodecSepSeparator._detect_clap_amodel(state_dict)
        clap_cfg = dict(model_kwargs.get("clap") or {})

        needs_update = False
        if not clap_cfg:
            needs_update = True
        elif clap_cfg.get("amodel", "HTSAT-tiny") != detected_amodel:
            logger.info(
                "CLAP amodel mismatch: config says %s but checkpoint has %s",
                clap_cfg.get("amodel"), detected_amodel,
            )
            needs_update = True

        if needs_update:
            clap_cfg["amodel"] = detected_amodel
            if not clap_cfg.get("pretrained_ckpt_path"):
                default_clap_path = get_codecsep_clap_checkpoint_path()
                if default_clap_path.exists():
                    clap_cfg["pretrained_ckpt_path"] = str(default_clap_path)
                    logger.info(
                        "Using default CLAP checkpoint: %s (amodel=%s)",
                        default_clap_path, detected_amodel,
                    )
            model_kwargs["clap"] = clap_cfg

    @staticmethod
    def _infer_run_dir(checkpoint_source: Path, resolved_checkpoint: Path) -> Path | None:
        if checkpoint_source.exists() and checkpoint_source.is_dir():
            return checkpoint_source
        if resolved_checkpoint.parent.name in {"ckpt_best", "ckpt_final"}:
            return resolved_checkpoint.parents[1]
        if resolved_checkpoint.parent.name in {"best_accelerate_resume_state", "final_weights"}:
            if resolved_checkpoint.parent.parent.name == "checkpoints":
                return resolved_checkpoint.parents[2]
            return resolved_checkpoint.parent.parent
        return None

    def _load_model_config(self, resolved_checkpoint: Path) -> tuple[int, dict[str, object], dict[str, object]]:
        run_dir = self._infer_run_dir(self.checkpoint_path, resolved_checkpoint)
        if run_dir is None:
            return TARGET_SAMPLE_RATE, {}, {}

        config_candidates = (
            run_dir / ".hydra" / "config.yaml",
            run_dir / "config" / "hydra_snapshot" / "config.yaml",
            run_dir.parent / "config" / "hydra_snapshot" / "config.yaml",
        )
        config_path = next((candidate for candidate in config_candidates if candidate.exists()), None)
        if config_path is None:
            return TARGET_SAMPLE_RATE, {}, {}

        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        model_cfg = dict(((data.get("model") or {}).get("codecsep_params") or {}))
        model_cfg.pop("name", None)
        model_cfg = self._resolve_model_cfg_paths(
            model_cfg,
            run_dir=run_dir,
        )
        sample_rate = int(data.get("sampling_rate", TARGET_SAMPLE_RATE))
        transform_cfg = dict(((data.get("training") or {}).get("transform") or {}))
        inference_cfg = {
            "mix_lufs_db": ((transform_cfg.get("lufs_norm_db") or {}).get("mix")),
            "peak_norm_db": transform_cfg.get("peak_norm_db"),
        }
        return sample_rate, model_cfg, inference_cfg

    @staticmethod
    def _resolve_model_cfg_paths(
        model_cfg: dict[str, object],
        *,
        run_dir: Path,
    ) -> dict[str, object]:
        runtime_snapshot = run_dir / "runtime_snapshot.json"
        snapshot_data: dict[str, Any] = {}
        if runtime_snapshot.exists():
            with runtime_snapshot.open("r", encoding="utf-8") as f:
                snapshot_data = yaml.safe_load(f) or {}

        resolved_paths = dict(snapshot_data.get("resolved_paths") or {})
        project_root_value = snapshot_data.get("project_root")
        if project_root_value:
            project_root = Path(str(project_root_value))
        else:
            project_root = run_dir.parents[1]

        def resolve_value(value: Any, key: str | None = None) -> Any:
            if isinstance(value, dict):
                return {k: resolve_value(v, key=k) for k, v in value.items()}
            if isinstance(value, list):
                return [resolve_value(item) for item in value]
            if not isinstance(value, str):
                return value

            if value.startswith("${paths.") and value.endswith("}"):
                path_key = value[len("${paths."):-1]
                resolved = resolved_paths.get(path_key)
                if resolved:
                    return resolved

            if key and key.endswith("_path"):
                candidate = Path(value).expanduser()
                if not candidate.is_absolute():
                    candidate = (project_root / candidate).resolve()
                return str(candidate)

            return value

        return resolve_value(model_cfg)

    @staticmethod
    def _resolve_model_class():
        from ai.ai_runtime.separation.codecsep import CodecSep

        return CodecSep

    @staticmethod
    def _resolve_wavsep_mag_norm_class():
        class _FallbackWavSepMagNorm:
            """Minimal vendored-equivalent fallback used for the clean runtime bundle."""

            def __call__(self, mix: torch.Tensor, signal_sep: torch.Tensor) -> torch.Tensor:
                eps = 1e-8
                bs, num_stems, channels, _ = signal_sep.shape
                mix_flat = mix.reshape(bs * mix.shape[1] * channels, -1)
                sep_flat = signal_sep.reshape(bs * num_stems * channels, -1)
                window = torch.hann_window(1024, device=mix.device)

                mix_spec = torch.stft(
                    mix_flat,
                    n_fft=1024,
                    hop_length=256,
                    win_length=1024,
                    window=window,
                    pad_mode="reflect",
                    center=True,
                    onesided=True,
                    return_complex=True,
                )
                sep_spec = torch.stft(
                    sep_flat,
                    n_fft=1024,
                    hop_length=256,
                    win_length=1024,
                    window=window,
                    pad_mode="reflect",
                    center=True,
                    onesided=True,
                    return_complex=True,
                )
                mix_spec = mix_spec.reshape(bs, 1, channels, *mix_spec.shape[-2:])
                sep_spec = sep_spec.reshape(bs, num_stems, channels, *sep_spec.shape[-2:])

                sep_mag = sep_spec.abs()
                ratio = sep_mag / sep_mag.sum(dim=1, keepdim=True).clamp_min(eps)
                ret_spec = torch.polar(mix_spec.abs() * ratio, mix_spec.angle())
                ret_spec = ret_spec.reshape(bs * num_stems * channels, *ret_spec.shape[-2:])
                ret = torch.istft(
                    ret_spec,
                    n_fft=1024,
                    hop_length=256,
                    win_length=1024,
                    window=window,
                    center=True,
                )
                return ret.reshape(bs, num_stems, channels, -1)

        return _FallbackWavSepMagNorm

    @staticmethod
    def _resolve_volume_norm_helpers():
        class _FallbackVolumeNorm:
            def __init__(self, sample_rate: int = TARGET_SAMPLE_RATE):
                self.sample_rate = sample_rate
                self._meter = torchaudio.transforms.Loudness(sample_rate)

            def __call__(self, signal, target_loudness=-30, var=0, return_gain=False):
                if signal.ndim != 3:
                    raise ValueError("Expected [B, C, T] tensor for loudness normalization.")
                bs = signal.shape[0]
                lufs_ref = self._meter(signal)
                lufs_target = torch.full_like(lufs_ref, float(target_loudness))
                gain = torch.exp((lufs_target - lufs_ref) * np.log(10.0) / 20.0)
                gain[gain.isnan()] = 0.0
                signal = signal * gain[:, None, None]
                if return_gain:
                    return signal, gain
                return signal

        def _db_to_gain(db: float) -> float:
            return float(np.power(10.0, float(db) / 20.0))

        return _FallbackVolumeNorm, _db_to_gain

    def _get_mag_normalizer(self):
        if self._mag_normalizer is None:
            self._mag_normalizer = self._resolve_wavsep_mag_norm_class()()
        return self._mag_normalizer

    def _configure_inference_normalization(
        self,
        *,
        sample_rate: int,
        inference_cfg: Mapping[str, object],
    ) -> None:
        self._mix_lufs_target_db = None
        self._peak_norm_db = None
        self._peak_norm_gain = None
        self._input_volume_norm = None
        self._logged_inference_norm_cfg = False

        mix_lufs_value = inference_cfg.get("mix_lufs_db")
        peak_norm_value = inference_cfg.get("peak_norm_db")
        if mix_lufs_value is None and peak_norm_value is None:
            return

        volume_norm_class, db_to_gain = self._resolve_volume_norm_helpers()
        if mix_lufs_value is not None:
            self._mix_lufs_target_db = float(mix_lufs_value)
            self._input_volume_norm = volume_norm_class(sample_rate=sample_rate)
        if peak_norm_value is not None:
            self._peak_norm_db = float(peak_norm_value)
            self._peak_norm_gain = float(db_to_gain(float(peak_norm_value)))

    def _apply_inference_normalization(
        self,
        tensor: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        normalized = tensor.clone()
        total_gain = torch.ones(
            (normalized.shape[0], 1, 1),
            dtype=normalized.dtype,
            device=normalized.device,
        )

        if self._peak_norm_gain is not None:
            peak = normalized.abs().amax(dim=-1, keepdim=True)
            peak_limit = torch.full_like(peak, float(self._peak_norm_gain))
            peak_gain = torch.ones_like(peak)
            mask = peak > peak_limit
            peak_gain[mask] = peak_limit[mask] / peak[mask]
            normalized = normalized * peak_gain
            total_gain = total_gain * peak_gain

        if self._input_volume_norm is not None and self._mix_lufs_target_db is not None:
            normalized, mix_gain = self._input_volume_norm(
                signal=normalized,
                target_loudness=float(self._mix_lufs_target_db),
                var=0,
                return_gain=True,
            )
            total_gain = total_gain * mix_gain[:, None, None]

        if (
            not self._logged_inference_norm_cfg
            and (self._mix_lufs_target_db is not None or self._peak_norm_db is not None)
        ):
            logger.info(
                "CodecSep runtime applying AudioCaps-style input conditioning: mix_lufs=%.2f peak_norm_db=%s",
                float(self._mix_lufs_target_db or 0.0),
                "none" if self._peak_norm_db is None else f"{self._peak_norm_db:.2f}",
            )
            self._logged_inference_norm_cfg = True

        return normalized, total_gain

    def separate(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        stems: Sequence[str] = ("sfx",),
        prompt_overrides: Optional[Mapping[str, Union[str, Sequence[str]]]] = None,
    ) -> np.ndarray:
        """Separate requested normalized stems and return their sum."""
        stem_outputs = self.separate_stems(
            audio=audio,
            sample_rate=sample_rate,
            stems=stems,
            prompt_overrides=prompt_overrides,
        )
        selected = [stem_outputs[stem] for stem in stems if stem in stem_outputs]
        if not selected:
            if isinstance(audio, np.ndarray):
                return np.zeros_like(audio)
            return np.zeros_like(audio.detach().cpu().numpy())
        combined = np.array(selected[0], copy=True)
        for track in selected[1:]:
            min_samples = min(combined.shape[0], track.shape[0])
            combined[:min_samples] += track[:min_samples]
        return combined

    def separate_stems(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        stems: Sequence[str] | None = None,
        prompt_overrides: Optional[Mapping[str, Union[str, Sequence[str]]]] = None,
    ) -> Dict[str, np.ndarray]:
        """Return paper-faithful normalized stems as a name -> numpy dict."""
        return self.separate_stem_bundle(
            audio=audio,
            sample_rate=sample_rate,
            stems=stems,
            prompt_overrides=prompt_overrides,
        )["normalized"]

    def separate_stem_bundle(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        stems: Sequence[str] | None = None,
        prompt_overrides: Optional[Mapping[str, Union[str, Sequence[str]]]] = None,
    ) -> Dict[str, Dict[str, np.ndarray]]:
        """Return both raw decoded stems and WavSepMagNorm-normalized stems."""
        self._lazy_load_model()
        assert self._model is not None
        stems = stems or list(self.STEMS)

        tensor, restore_gain = self._prepare_input(audio, sample_rate)
        raw_output, normalized, track_order = self._run_normalized_model(
            tensor,
            prompt_overrides=prompt_overrides,
            restore_gain=restore_gain,
        )

        normalized_result: Dict[str, np.ndarray] = {}
        raw_result: Dict[str, np.ndarray] = {}
        for stem in stems:
            if stem not in track_order:
                logger.warning("Unknown CodecSep stem '%s', skipping", stem)
                continue
            idx = track_order.index(stem)
            raw_audio = self._resample_back(raw_output[:, idx + 1, :], sample_rate)
            stem_audio = self._resample_back(normalized[:, idx, :], sample_rate)
            raw_result[stem] = self._to_numpy(raw_audio, audio)
            normalized_result[stem] = self._to_numpy(stem_audio, audio)
        return {"raw": raw_result, "normalized": normalized_result}

    def separate_multi_query(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        stem_groups: Sequence[Sequence[str]],
        prompt_overrides: Optional[Mapping[str, Union[str, Sequence[str]]]] = None,
    ) -> list[np.ndarray]:
        """Analogue of WaveformerSeparator.separate_multi_query.

        CodecSep always produces all 3 stems in one pass, so multiple
        queries are answered from a single forward pass.
        """
        self._lazy_load_model()
        assert self._model is not None

        stem_outputs = self.separate_stems(
            audio=audio,
            sample_rate=sample_rate,
            stems=list(self.STEMS),
            prompt_overrides=prompt_overrides,
        )

        results: list[np.ndarray] = []
        for group in stem_groups:
            tracks = []
            for stem in group:
                if stem in stem_outputs:
                    tracks.append(stem_outputs[stem])
            if tracks:
                combined = np.array(tracks[0], copy=True)
                for track in tracks[1:]:
                    min_samples = min(combined.shape[0], track.shape[0])
                    combined[:min_samples] += track[:min_samples]
            else:
                if isinstance(audio, np.ndarray):
                    combined = np.zeros_like(audio)
                else:
                    combined = np.zeros_like(audio.detach().cpu().numpy())
            results.append(combined)
        return results

    def separate_class_ids(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        class_ids: Sequence[int | str],
        *,
        target_present: Sequence[bool] | torch.Tensor | None = None,
        query_mode: Sequence[str] | str | None = None,
    ) -> Dict[int, np.ndarray]:
        return self.separate_class_id_bundle(
            audio=audio,
            sample_rate=sample_rate,
            class_ids=class_ids,
            target_present=target_present,
            query_mode=query_mode,
        )["targets"]

    def separate_class_id_bundle(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        class_ids: Sequence[int | str],
        *,
        target_present: Sequence[bool] | torch.Tensor | None = None,
        query_mode: Sequence[str] | str | None = None,
        merge_policy: str = "wiener_mask",
        aggressiveness: float = 1.0,
    ) -> dict[str, object]:
        self._lazy_load_model()
        assert self._model is not None
        if self.conditioning_mode != "class_id":
            raise RuntimeError(
                "This CodecSep checkpoint is prompt-conditioned. "
                "Use separate_stems/query or load a fixed-category checkpoint for class-id inference.",
            )

        resolved_class_ids = self._coerce_class_id_sequence(class_ids)
        if not resolved_class_ids:
            raise ValueError("Expected at least one class id for fixed-category separation.")

        if target_present is None:
            target_present_tensor = torch.ones(len(resolved_class_ids), dtype=torch.bool, device=self.device)
        else:
            target_present_tensor = torch.as_tensor(target_present, dtype=torch.bool, device=self.device).reshape(-1)
        if int(target_present_tensor.numel()) != len(resolved_class_ids):
            raise ValueError("target_present length must match class_ids length.")

        if query_mode is None:
            query_modes = ["present"] * len(resolved_class_ids)
        elif isinstance(query_mode, str):
            query_modes = [str(query_mode)] * len(resolved_class_ids)
        else:
            query_modes = [str(item) for item in list(query_mode)]
        if len(query_modes) != len(resolved_class_ids):
            raise ValueError("query_mode length must match class_ids length.")

        tensor, restore_gain = self._prepare_input(audio, sample_rate)
        class_id_tensor = torch.as_tensor(resolved_class_ids, dtype=torch.long, device=self.device)
        target_audio = self._model.separate_class_ids(
            tensor,
            class_id_tensor,
            target_present=target_present_tensor,
            query_mode=query_modes,
            sample_rate=TARGET_SAMPLE_RATE,
        )
        target_audio = target_audio / restore_gain.to(target_audio.device).clamp_min(1e-8)

        target_outputs: Dict[int, np.ndarray] = {}
        for index, class_id in enumerate(resolved_class_ids):
            class_tensor = self._resample_back(target_audio[index], sample_rate)
            target_outputs[int(class_id)] = self._to_numpy(class_tensor, audio)

        merged_target, clean_audio, chosen_policy = self._merge_class_target_estimates(
            original_audio=np.asarray(audio, dtype=np.float32),
            target_outputs=target_outputs,
            aggressiveness=aggressiveness,
            policy=merge_policy,
        )
        return {
            "targets": target_outputs,
            "selected_class_ids": resolved_class_ids,
            "merged_target": merged_target,
            "clean_audio": clean_audio,
            "merge_policy": chosen_policy,
        }

    def query(
        self,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        plan: CodecSepQueryPlan,
        *,
        selected_slot_hint: str | None = None,
    ) -> CodecSepQueryResult:
        """Run a CodecSep query and return both target and clean audio."""
        self._lazy_load_model()
        assert self._model is not None

        normalized_plan = plan.normalized()
        resolved_mode = self._resolve_query_mode(normalized_plan.mode)
        if resolved_mode == "fixed_category":
            raise RuntimeError(
                "CodecSep query plans are prompt-based and cannot run in fixed_category mode. "
                "Use separate_class_ids with explicit Hive class ids instead.",
            )
        if resolved_mode == "audiocaps_native":
            return self._query_audiocaps_native(
                audio=audio,
                sample_rate=sample_rate,
                plan=normalized_plan,
            )
        return self._query_experimental_search(
            audio=audio,
            sample_rate=sample_rate,
            plan=normalized_plan,
            selected_slot_hint=selected_slot_hint,
        )

    @staticmethod
    def _resolve_query_mode(mode: str) -> str:
        if mode == "query_first":
            return "experimental_search"
        if mode in {"fixed_category", "audiocaps_native", "experimental_search", "compat"}:
            return mode
        return "fixed_category"

    def _query_audiocaps_native(
        self,
        *,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        plan: CodecSepQueryPlan,
    ) -> CodecSepQueryResult:
        base_audio = np.asarray(audio, dtype=np.float32).copy()
        target_slot = str(plan.preferred_slot)
        tensor, restore_gain = self._prepare_input(base_audio, sample_rate)
        prompt_overrides = self._build_query_prompt_overrides(plan, target_slot=target_slot)
        embedding_overrides = {
            target_slot: self._build_native_target_embedding(plan),
        }
        raw_output, normalized, track_order = self._run_normalized_model(
            tensor,
            prompt_overrides=prompt_overrides,
            embedding_overrides=embedding_overrides,
            restore_gain=restore_gain,
        )

        raw_outputs: dict[str, np.ndarray] = {}
        normalized_outputs: dict[str, np.ndarray] = {}
        for slot in track_order:
            idx = track_order.index(slot)
            raw_audio = self._resample_back(raw_output[:, idx + 1, :], sample_rate)
            normalized_audio = self._resample_back(normalized[:, idx, :], sample_rate)
            raw_outputs[slot] = self._to_numpy(raw_audio, base_audio)
            normalized_outputs[slot] = self._to_numpy(normalized_audio, base_audio)

        clean_audio, chosen_policy = self._build_clean_audio(
            original_audio=base_audio,
            normalized_outputs=normalized_outputs,
            target_slot=target_slot,
            aggressiveness=plan.aggressiveness,
            policy=plan.reconstruction_policy,
        )
        mixture_score = self._mixture_consistency_score(
            normalized_outputs=normalized_outputs,
            reference_audio=base_audio,
        )
        score = CodecSepCandidateScore(
            slot=target_slot,  # type: ignore[arg-type]
            target_score=0.0,
            preserve_score=0.0,
            mixture_score=mixture_score,
            total_score=mixture_score,
            strategy="audiocaps_native",
        )
        logger.info(
            "CodecSep AudioCaps-native selection: label=%s slot=%s policy=%s aggressiveness=%.2f anchors=%s",
            plan.target_label or plan.target_prompts,
            target_slot,
            chosen_policy,
            float(plan.aggressiveness),
            {
                slot: prompts
                for slot, prompts in prompt_overrides.items()
                if slot != target_slot
            },
        )
        return CodecSepQueryResult(
            plan=plan,
            selected_slot=target_slot,  # type: ignore[arg-type]
            target_audio=np.asarray(normalized_outputs[target_slot], dtype=np.float32),
            clean_audio=np.asarray(clean_audio, dtype=base_audio.dtype),
            raw_outputs=raw_outputs,
            normalized_outputs=normalized_outputs,
            score=score,
            candidate_scores={target_slot: score},
            chosen_policy=chosen_policy,
            used_multistep=False,
        )

    def _query_experimental_search(
        self,
        *,
        audio: Union[np.ndarray, torch.Tensor],
        sample_rate: int,
        plan: CodecSepQueryPlan,
        selected_slot_hint: str | None = None,
    ) -> CodecSepQueryResult:
        candidate_slots = [selected_slot_hint] if selected_slot_hint else plan.candidate_slots()
        base_audio = np.asarray(audio, dtype=np.float32).copy()
        best_candidate: dict[str, object] | None = None
        candidate_scores: dict[str, CodecSepCandidateScore] = {}

        for slot in candidate_slots:
            candidate = self._run_query_candidate(
                query_audio=base_audio,
                reference_audio=base_audio,
                sample_rate=sample_rate,
                plan=plan,
                target_slot=str(slot),
                strategy_tag="slot_search" if len(candidate_slots) > 1 else "single_pass",
            )
            candidate_scores[str(slot)] = candidate["score"]
            if best_candidate is None or candidate["score"].total_score > best_candidate["score"].total_score:
                best_candidate = candidate

        assert best_candidate is not None
        used_multistep = False
        if plan.use_multistep and plan.multistep_steps > 1:
            refined = self._refine_query_candidate(
                audio=base_audio,
                sample_rate=sample_rate,
                plan=plan,
                candidate=best_candidate,
            )
            if refined["score"].total_score >= best_candidate["score"].total_score:
                best_candidate = refined
                candidate_scores[best_candidate["score"].slot] = best_candidate["score"]
                used_multistep = True

        clean_audio, chosen_policy = self._build_clean_audio(
            original_audio=base_audio,
            normalized_outputs=best_candidate["normalized_outputs"],
            target_slot=str(best_candidate["score"].slot),
            aggressiveness=plan.aggressiveness,
            policy=plan.reconstruction_policy,
        )
        logger.info(
            "CodecSep experimental-search selection: label=%s slot=%s strategy=%s target_score=%.4f preserve_score=%.4f mixture_score=%.4f total_score=%.4f policy=%s multistep=%s",
            plan.target_label or plan.target_prompts,
            best_candidate["score"].slot,
            best_candidate["score"].strategy,
            best_candidate["score"].target_score,
            best_candidate["score"].preserve_score,
            best_candidate["score"].mixture_score,
            best_candidate["score"].total_score,
            chosen_policy,
            used_multistep,
        )
        return CodecSepQueryResult(
            plan=plan,
            selected_slot=best_candidate["score"].slot,
            target_audio=best_candidate["target_audio"],
            clean_audio=clean_audio.astype(base_audio.dtype, copy=False),
            raw_outputs=best_candidate["raw_outputs"],
            normalized_outputs=best_candidate["normalized_outputs"],
            score=best_candidate["score"],
            candidate_scores=candidate_scores,
            chosen_policy=chosen_policy,
            used_multistep=used_multistep,
        )

    def _mixture_consistency_score(
        self,
        *,
        normalized_outputs: Mapping[str, np.ndarray],
        reference_audio: np.ndarray,
    ) -> float:
        recon = self._sum_tracks(list(normalized_outputs.values()), reference_audio)
        recon = recon[: len(reference_audio)]
        ref = reference_audio[: len(recon)]
        mixture_error = float(np.linalg.norm(recon - ref) / (np.linalg.norm(ref) + 1e-8))
        return max(0.0, 1.0 - mixture_error)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prepare_input(self, audio: Union[np.ndarray, torch.Tensor],
                       sample_rate: int) -> tuple[torch.Tensor, torch.Tensor]:
        tensor = torch.as_tensor(audio, dtype=torch.float32)
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
        elif tensor.ndim == 2 and tensor.shape[0] > tensor.shape[1]:
            tensor = tensor.transpose(0, 1)

        if tensor.shape[0] > 1:
            tensor = tensor.mean(dim=0, keepdim=True)

        if sample_rate != TARGET_SAMPLE_RATE:
            if sample_rate not in self._resample_in:
                self._resample_in[sample_rate] = torchaudio.transforms.Resample(
                    orig_freq=sample_rate, new_freq=TARGET_SAMPLE_RATE,
                )
            tensor = self._resample_in[sample_rate](tensor)

        tensor = tensor.unsqueeze(0)
        restore_gain = torch.ones((tensor.shape[0], 1, 1), dtype=tensor.dtype)
        if self._input_volume_norm is not None or self._peak_norm_gain is not None:
            tensor, applied_gain = self._apply_inference_normalization(tensor)
            restore_gain = applied_gain.clamp_min(1e-8)

        return tensor.to(self.device), restore_gain.to(self.device)

    @staticmethod
    def _normalize_prompt_value(
        value: Union[str, Sequence[str], None],
    ) -> list[str]:
        return normalize_codecsep_prompt_value(value)

    @classmethod
    def _normalize_prompt_map(
        cls,
        prompts: Mapping[str, Union[str, Sequence[str]]],
    ) -> Dict[str, list[str]]:
        return normalize_codecsep_prompt_map(prompts)

    def _build_prompt_list(
        self,
        prompt_overrides: Optional[Mapping[str, Union[str, Sequence[str]]]] = None,
    ) -> list[list[str]]:
        if self.conditioning_mode == "class_id":
            raise RuntimeError(
                "Prompt-based track prompts are unavailable for fixed-category checkpoints. "
                "Use separate_class_ids instead.",
            )
        merged = dict(self.prompts)
        if prompt_overrides:
            merged.update(self._normalize_prompt_map(prompt_overrides))
        prompts_list: list[list[str]] = []
        for track in self._model.tracks:
            prompt_list = merged.get(track) or DEFAULT_PROMPTS.get(track, [track])
            runtime_prompt = collapse_codecsep_prompt_value(prompt_list)
            prompts_list.append(runtime_prompt or [track])
        return prompts_list

    def _get_clap_scorer(self) -> _ClapSimilarityScorer:
        if self._clap_scorer is not None:
            return self._clap_scorer
        if self._clap_scorer_disabled:
            raise RuntimeError(self._clap_scorer_error or "CodecSep CLAP scorer disabled.")
        clap_cfg = dict(self._clap_scorer_cfg or {})
        ckpt_value = clap_cfg.get("pretrained_ckpt_path")
        if not ckpt_value:
            raise RuntimeError("CodecSep CLAP scorer requires clap.pretrained_ckpt_path in the run config.")
        scorer_device = self.device
        try:
            self._clap_scorer = _ClapSimilarityScorer(
                checkpoint_path=Path(str(ckpt_value)).expanduser().resolve(),
                amodel=str(clap_cfg.get("amodel", "HTSAT-tiny")),
                tmodel=str(clap_cfg.get("tmodel", "roberta")),
                enable_fusion=bool(clap_cfg.get("enable_fusion", False)),
                device=scorer_device,
            )
        except Exception as exc:
            self._clap_scorer_disabled = True
            self._clap_scorer_error = f"CodecSep CLAP scorer disabled after initialization failure: {exc}"
            raise RuntimeError(self._clap_scorer_error) from exc
        return self._clap_scorer

    def _build_target_embedding(self, plan: CodecSepQueryPlan) -> torch.Tensor:
        assert self._model is not None
        positive_embed = self._model.text_encoder.get_text_embedding(
            plan.target_prompts,
            use_tensor=True,
        ).detach()
        target_embed = positive_embed.mean(dim=0, keepdim=True)
        if plan.negative_prompts:
            negative_embed = self._model.text_encoder.get_text_embedding(
                plan.negative_prompts,
                use_tensor=True,
            ).detach().mean(dim=0, keepdim=True)
            alpha = min(0.65, max(0.25, 0.30 + 0.20 * max(0.0, plan.aggressiveness - 1.0)))
            target_embed = (1.0 + alpha) * target_embed - alpha * negative_embed
        return F.normalize(target_embed.float(), dim=-1)

    def _build_query_prompt_overrides(
        self,
        plan: CodecSepQueryPlan,
        *,
        target_slot: str,
    ) -> dict[str, list[str]]:
        prompt_overrides = {
            slot: list(prompt_values)
            for slot, prompt_values in dict(plan.slot_prompt_overrides).items()
            if prompt_values
        }
        prompt_overrides[target_slot] = list(plan.target_prompts)
        for slot in self.STEMS:
            if slot not in prompt_overrides:
                prompt_overrides[slot] = list(self.prompts.get(slot) or DEFAULT_PROMPTS.get(slot, [slot]))
        return prompt_overrides

    def _expand_target_prompt_variants(
        self,
        prompt_values: Sequence[str],
    ) -> list[str]:
        variants = normalize_codecsep_prompt_value(prompt_values)
        if not variants:
            return []

        flattened = flatten_codecsep_prompt_segments(variants)
        collapsed = ", ".join(flattened[:6]) if flattened else variants[0]
        if collapsed and collapsed not in variants:
            variants.append(collapsed)
        if collapsed:
            variants.append(f"a recording of {collapsed}")

        lowered_segments = " ".join(segment.casefold() for segment in flattened)
        for keywords, templates in PROMPT_TEMPLATE_KEYWORDS:
            if any(keyword in lowered_segments for keyword in keywords):
                variants.extend(templates)

        deduped: list[str] = []
        seen: set[str] = set()
        for prompt in variants:
            cleaned = str(prompt).strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(cleaned)
            if len(deduped) >= 4:
                break
        return deduped

    def _build_native_target_embedding(
        self,
        plan: CodecSepQueryPlan,
    ) -> torch.Tensor:
        assert self._model is not None
        prompt_variants = self._expand_target_prompt_variants(plan.target_prompts)
        if not prompt_variants:
            prompt_variants = list(plan.target_prompts)
        embeddings = self._model.text_encoder.get_text_embedding(
            prompt_variants,
            use_tensor=True,
        ).detach()
        target_embed = embeddings.mean(dim=0, keepdim=True)
        if plan.negative_prompts:
            negative_embed = self._model.text_encoder.get_text_embedding(
                plan.negative_prompts,
                use_tensor=True,
            ).detach().mean(dim=0, keepdim=True)
            alpha = min(0.65, max(0.25, 0.30 + 0.20 * max(0.0, plan.aggressiveness - 1.0)))
            target_embed = (1.0 + alpha) * target_embed - alpha * negative_embed
        return F.normalize(target_embed.float(), dim=-1)

    @staticmethod
    def _rms(audio: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.square(np.asarray(audio, dtype=np.float32)))) + 1e-8)

    def _score_candidate(
        self,
        *,
        target_audio: np.ndarray,
        normalized_outputs: Mapping[str, np.ndarray],
        reference_audio: np.ndarray,
        sample_rate: int,
        plan: CodecSepQueryPlan,
        target_slot: str,
        strategy_tag: str,
    ) -> CodecSepCandidateScore:
        try:
            target_score = self._get_clap_scorer().cosine_similarity(
                audio=target_audio,
                sample_rate=sample_rate,
                prompts=plan.target_prompts,
            )
        except Exception as exc:
            logger.warning("CLAP candidate scoring unavailable; falling back to energy heuristic: %s", exc)
            target_score = min(1.0, self._rms(target_audio) / self._rms(reference_audio))

        preserve_score = 0.0
        if plan.preserve_prompts:
            complement = self._sum_tracks(
                [track for slot, track in normalized_outputs.items() if slot != target_slot],
                reference_audio,
            )
            try:
                preserve_score = self._get_clap_scorer().cosine_similarity(
                    audio=complement,
                    sample_rate=sample_rate,
                    prompts=plan.preserve_prompts,
                )
            except Exception as exc:
                logger.warning(
                    "CLAP preserve scoring unavailable; falling back to RMS heuristic: %s",
                    exc,
                )
                preserve_score = min(1.0, self._rms(complement) / self._rms(reference_audio))

        recon = self._sum_tracks(list(normalized_outputs.values()), reference_audio)
        recon = recon[: len(reference_audio)]
        ref = reference_audio[: len(recon)]
        mixture_error = float(np.linalg.norm(recon - ref) / (np.linalg.norm(ref) + 1e-8))
        mixture_score = max(0.0, 1.0 - mixture_error)

        total_score = float(target_score + 0.12 * preserve_score + 0.08 * mixture_score)
        return CodecSepCandidateScore(
            slot=target_slot,  # type: ignore[arg-type]
            target_score=float(target_score),
            preserve_score=float(preserve_score),
            mixture_score=float(mixture_score),
            total_score=total_score,
            strategy=strategy_tag,
        )

    @staticmethod
    def _sum_tracks(
        tracks: Sequence[np.ndarray],
        reference: np.ndarray,
    ) -> np.ndarray:
        if not tracks:
            return np.zeros_like(reference, dtype=np.float32)
        total = np.asarray(tracks[0], dtype=np.float32).copy()
        for track in tracks[1:]:
            total = total[: min(len(total), len(track))]
            total[: len(total)] += np.asarray(track[: len(total)], dtype=np.float32)
        if len(total) < len(reference):
            total = np.pad(total, (0, len(reference) - len(total)), mode="constant")
        return total[: len(reference)]

    def _run_query_candidate(
        self,
        *,
        query_audio: np.ndarray,
        reference_audio: np.ndarray,
        sample_rate: int,
        plan: CodecSepQueryPlan,
        target_slot: str,
        strategy_tag: str,
    ) -> dict[str, object]:
        self._lazy_load_model()
        assert self._model is not None
        tensor, restore_gain = self._prepare_input(query_audio, sample_rate)
        target_embedding = self._build_target_embedding(plan)
        prompt_overrides = self._build_query_prompt_overrides(plan, target_slot=target_slot)
        raw_output, normalized, track_order = self._run_normalized_model(
            tensor,
            prompt_overrides=prompt_overrides,
            embedding_overrides={target_slot: target_embedding},
            restore_gain=restore_gain,
        )

        raw_outputs: dict[str, np.ndarray] = {}
        normalized_outputs: dict[str, np.ndarray] = {}
        for slot in track_order:
            idx = track_order.index(slot)
            raw_audio = self._resample_back(raw_output[:, idx + 1, :], sample_rate)
            normalized_audio = self._resample_back(normalized[:, idx, :], sample_rate)
            raw_outputs[slot] = self._to_numpy(raw_audio, reference_audio)
            normalized_outputs[slot] = self._to_numpy(normalized_audio, reference_audio)

        target_audio = np.asarray(normalized_outputs[target_slot], dtype=np.float32)
        score = self._score_candidate(
            target_audio=target_audio,
            normalized_outputs=normalized_outputs,
            reference_audio=np.asarray(reference_audio, dtype=np.float32),
            sample_rate=sample_rate,
            plan=plan,
            target_slot=target_slot,
            strategy_tag=strategy_tag,
        )
        return {
            "target_audio": target_audio,
            "raw_outputs": raw_outputs,
            "normalized_outputs": normalized_outputs,
            "score": score,
        }

    def _refine_query_candidate(
        self,
        *,
        audio: np.ndarray,
        sample_rate: int,
        plan: CodecSepQueryPlan,
        candidate: dict[str, object],
    ) -> dict[str, object]:
        current = candidate
        original = np.asarray(audio, dtype=np.float32)
        ratios = (0.0, 0.25, 0.5)
        target_slot = str(current["score"].slot)
        for _ in range(max(0, plan.multistep_steps - 1)):
            best_candidate = current
            previous_target = np.asarray(current["target_audio"], dtype=np.float32)
            for ratio in ratios:
                blended = (ratio * original) + ((1.0 - ratio) * previous_target)
                blended_candidate = self._run_query_candidate(
                    query_audio=blended.astype(np.float32, copy=False),
                    reference_audio=original,
                    sample_rate=sample_rate,
                    plan=plan.force_slot(target_slot),
                    target_slot=target_slot,
                    strategy_tag=f"multistep@{ratio:.2f}",
                )
                if blended_candidate["score"].total_score > best_candidate["score"].total_score:
                    best_candidate = blended_candidate
            current = best_candidate
        return current

    def _build_clean_audio(
        self,
        *,
        original_audio: np.ndarray,
        normalized_outputs: Mapping[str, np.ndarray],
        target_slot: str,
        aggressiveness: float,
        policy: str,
    ) -> tuple[np.ndarray, str]:
        target_audio = np.asarray(normalized_outputs[target_slot], dtype=np.float32)
        other_tracks = [
            np.asarray(track, dtype=np.float32)
            for slot, track in normalized_outputs.items()
            if slot != target_slot
        ]
        complement_audio = self._sum_tracks(other_tracks, original_audio)
        subtract_audio = np.asarray(original_audio, dtype=np.float32) - max(1.0, float(aggressiveness)) * target_audio

        chosen_policy = str(policy)
        if policy == "wiener_mask":
            return self._build_clean_audio_wiener(
                original_audio=original_audio,
                normalized_outputs=normalized_outputs,
                target_slot=target_slot,
                aggressiveness=aggressiveness,
            )
        if policy == "keep_complement":
            clean = complement_audio
        elif policy == "score_select":
            mix_rms = self._rms(original_audio)
            subtract_penalty = abs(self._rms(subtract_audio) - mix_rms)
            complement_penalty = abs(self._rms(complement_audio) - mix_rms)
            if complement_penalty + 1e-4 < subtract_penalty:
                clean = complement_audio
                chosen_policy = "keep_complement"
            else:
                clean = subtract_audio
                chosen_policy = "subtract_target"
        else:
            clean = subtract_audio
            chosen_policy = "subtract_target"
        return clean, chosen_policy

    def _build_clean_audio_wiener(
        self,
        *,
        original_audio: np.ndarray,
        normalized_outputs: Mapping[str, np.ndarray],
        target_slot: str,
        aggressiveness: float,
        nperseg: int = 2048,
        perceptual_floor_min: float = 0.01,
        perceptual_floor_max: float = 0.05,
    ) -> tuple[np.ndarray, str]:
        """Build clean audio using Wiener soft masks from CodecSep stem power spectrograms.

        Instead of subtracting the target stem waveform (which amplifies errors),
        compute sum-to-one Wiener masks from all stems' power spectrograms and
        apply the keep-mask to the mixture STFT. This is bounded [0,1] by
        construction and preserves mixture phase.
        """
        orig = np.asarray(original_audio, dtype=np.float32)

        # Flatten to mono for masking -- CodecSep stems are always mono.
        # Soundfile returns (samples, channels), so handle both conventions.
        if orig.ndim == 2:
            mix = orig.mean(axis=-1) if orig.shape[-1] <= orig.shape[0] else orig.mean(axis=0)
        else:
            mix = orig.copy()
        mix = mix.astype(np.float32)

        # Flatten stems to 1-D
        def _flatten_stem(s: np.ndarray) -> np.ndarray:
            s = np.asarray(s, dtype=np.float32)
            if s.ndim == 2:
                return s.mean(axis=-1) if s.shape[-1] <= s.shape[0] else s.mean(axis=0)
            return s

        flat_outputs = {slot: _flatten_stem(s) for slot, s in normalized_outputs.items()}

        # Fallback: if stems have negligible energy, return original
        mix_rms = float(np.sqrt(np.mean(mix ** 2)) + 1e-10)
        stem_rms_total = sum(
            float(np.sqrt(np.mean(s ** 2))) for s in flat_outputs.values()
        )
        if stem_rms_total < 1e-6 * mix_rms:
            logger.warning("CodecSep Wiener mask: stems have near-zero energy, returning original audio.")
            return orig.copy(), "wiener_mask_passthrough"

        n_samples = len(mix)
        nperseg = min(nperseg, n_samples // 2) if n_samples >= 4 else n_samples
        noverlap = nperseg * 3 // 4
        beta = max(0.5, float(aggressiveness) / 2.0)

        # Build frequency-dependent perceptual floor
        n_freqs = nperseg // 2 + 1
        floor = self._build_wiener_perceptual_floor(
            n_freqs, perceptual_floor_min, perceptual_floor_max,
        )

        # STFT of the mono mix
        _, _, Z_mix = scipy_signal.stft(mix, nperseg=nperseg, noverlap=noverlap)

        # Compute power spectrograms for keep vs target stems
        keep_power = np.zeros_like(np.abs(Z_mix) ** 2)
        target_power = np.zeros_like(keep_power)

        for slot, stem_1d in flat_outputs.items():
            # Pad/truncate to match mix length
            if len(stem_1d) < n_samples:
                stem_1d = np.pad(stem_1d, (0, n_samples - len(stem_1d)))
            else:
                stem_1d = stem_1d[:n_samples]

            _, _, Z_stem = scipy_signal.stft(stem_1d, nperseg=nperseg, noverlap=noverlap)
            P_stem = np.abs(Z_stem) ** 2

            if slot == target_slot:
                target_power += P_stem
            else:
                keep_power += P_stem

        total_power = keep_power + target_power + 1e-10

        # Wiener mask: ratio of keep-power to total
        mask_keep = keep_power / total_power

        # Apply mask exponent for aggressiveness control
        if abs(beta - 1.0) > 1e-4:
            mask_keep = np.power(mask_keep, beta)

        # Apply perceptual floor (frequency-dependent)
        floor_2d = floor[:, np.newaxis]
        mask_keep = np.maximum(mask_keep, floor_2d)

        # Clamp to [0, 1]
        mask_keep = np.clip(mask_keep, 0.0, 1.0)

        # Apply to mixture STFT and reconstruct
        Z_clean = mask_keep * Z_mix
        _, clean_mono = scipy_signal.istft(Z_clean, nperseg=nperseg, noverlap=noverlap)
        clean_mono = clean_mono[:n_samples].astype(np.float32)

        # Restore original shape (broadcast mono mask to stereo if needed)
        if orig.ndim == 2:
            # Apply the same mono gain to each channel of the original
            # gain = clean_mono / (mix + eps) avoids phase issues
            gain = np.abs(clean_mono) / (np.abs(mix) + 1e-8)
            gain = np.clip(gain, 0.0, 1.0)
            clean = orig.copy()
            for c in range(orig.shape[-1] if orig.shape[-1] <= orig.shape[0] else orig.shape[0]):
                if orig.shape[-1] <= orig.shape[0]:
                    clean[:, c] = orig[:, c] * gain
                else:
                    clean[c, :] = orig[c, :] * gain
        else:
            clean = clean_mono

        return clean.astype(np.float32), "wiener_mask"

    @staticmethod
    def _build_wiener_perceptual_floor(
        n_freqs: int,
        floor_min: float = 0.01,
        floor_max: float = 0.05,
    ) -> np.ndarray:
        """Build a frequency-dependent floor: higher floor at low freqs, lower at high."""
        bin_idx = np.arange(n_freqs, dtype=np.float32)
        t = bin_idx / max(n_freqs - 1, 1)
        return floor_max - t * (floor_max - floor_min)

    def _run_normalized_model(
        self,
        tensor: torch.Tensor,
        prompt_overrides: Optional[Mapping[str, Union[str, Sequence[str]]]] = None,
        embedding_overrides: Optional[Mapping[str, torch.Tensor]] = None,
        restore_gain: Optional[torch.Tensor] = None,
    ) -> tuple[torch.Tensor, torch.Tensor, list[str]]:
        track_order = list(self.STEMS)
        raw_output = self._run_model(
            tensor,
            track_order,
            prompt_overrides=prompt_overrides,
            embedding_overrides=embedding_overrides,
        )
        mix_tensor = tensor.unsqueeze(2)
        separated = raw_output[:, 1:].unsqueeze(2)
        normalized = self._get_mag_normalizer()(mix_tensor, separated)
        if normalized.ndim == 4 and normalized.shape[2] == 1:
            normalized = normalized.squeeze(2)
        if restore_gain is not None:
            safe_gain = restore_gain.to(raw_output.device).clamp_min(1e-8)
            raw_output = raw_output / safe_gain
            normalized = normalized / safe_gain
        return raw_output, normalized, track_order

    def _run_model(
        self,
        tensor: torch.Tensor,
        output_tracks: list[str],
        prompt_overrides: Optional[Mapping[str, Union[str, Sequence[str]]]] = None,
        embedding_overrides: Optional[Mapping[str, torch.Tensor]] = None,
    ) -> torch.Tensor:
        assert self._model is not None
        prompts_list = self._build_prompt_list(prompt_overrides=prompt_overrides)
        return self._model.evaluate(
            (tensor, prompts_list),
            sample_rate=TARGET_SAMPLE_RATE,
            output_tracks=["mix"] + output_tracks,
            embedding_overrides=embedding_overrides,
        )

    @staticmethod
    def _coerce_class_id_sequence(class_ids: Sequence[int | str]) -> list[int]:
        output: list[int] = []
        seen: set[int] = set()
        for value in list(class_ids):
            if value is None:
                continue
            class_id = int(value)
            if class_id in seen:
                continue
            seen.add(class_id)
            output.append(class_id)
        return output

    def _merge_class_target_estimates(
        self,
        *,
        original_audio: np.ndarray,
        target_outputs: Mapping[int, np.ndarray],
        aggressiveness: float,
        policy: str,
        nperseg: int = 2048,
    ) -> tuple[np.ndarray, np.ndarray, str]:
        if not target_outputs:
            passthrough = np.asarray(original_audio, dtype=np.float32).copy()
            return np.zeros_like(passthrough), passthrough, "empty"

        if policy == "sum":
            merged_target = np.asarray(
                self._sum_tracks(list(target_outputs.values()), original_audio),
                dtype=np.float32,
            )
            scale = max(0.0, float(aggressiveness))
            merged_target = merged_target * scale
            clean_audio = np.asarray(original_audio, dtype=np.float32) - merged_target
            return merged_target, clean_audio.astype(np.float32), "sum"

        orig = np.asarray(original_audio, dtype=np.float32)
        if orig.ndim == 2:
            mix = orig.mean(axis=-1) if orig.shape[-1] <= orig.shape[0] else orig.mean(axis=0)
        else:
            mix = orig.copy()
        mix = mix.astype(np.float32)

        def _flatten(audio_value: np.ndarray) -> np.ndarray:
            arr = np.asarray(audio_value, dtype=np.float32)
            if arr.ndim == 2:
                return arr.mean(axis=-1) if arr.shape[-1] <= arr.shape[0] else arr.mean(axis=0)
            return arr

        n_samples = len(mix)
        if n_samples < 4:
            merged_target = np.asarray(
                self._sum_tracks(list(target_outputs.values()), original_audio),
                dtype=np.float32,
            )
            scale = max(0.0, float(aggressiveness))
            merged_target = merged_target * scale
            clean_audio = np.asarray(original_audio, dtype=np.float32) - merged_target
            return merged_target, clean_audio.astype(np.float32), "sum"

        nperseg = min(int(nperseg), max(4, n_samples // 2))
        noverlap = max(1, nperseg * 3 // 4)
        beta = max(0.5, float(aggressiveness) / 2.0)
        _, _, Z_mix = scipy_signal.stft(mix, nperseg=nperseg, noverlap=noverlap)
        mix_power = np.abs(Z_mix) ** 2
        target_power = np.zeros_like(mix_power)

        for target_audio in target_outputs.values():
            flattened = _flatten(target_audio)
            if len(flattened) < n_samples:
                flattened = np.pad(flattened, (0, n_samples - len(flattened)))
            else:
                flattened = flattened[:n_samples]
            _, _, Z_target = scipy_signal.stft(flattened, nperseg=nperseg, noverlap=noverlap)
            target_power += np.abs(Z_target) ** 2

        if float(target_power.sum()) <= 1e-10:
            passthrough = orig.copy()
            return np.zeros_like(passthrough), passthrough, "wiener_mask_passthrough"

        target_power = np.minimum(target_power, mix_power)
        keep_power = np.clip(mix_power - target_power, 0.0, None)
        mask_keep = keep_power / (keep_power + target_power + 1e-10)
        if abs(beta - 1.0) > 1e-4:
            mask_keep = np.power(mask_keep, beta)
        mask_keep = np.clip(mask_keep, 0.0, 1.0)
        clean_spec = mask_keep * Z_mix
        removed_spec = (1.0 - mask_keep) * Z_mix
        _, clean_mono = scipy_signal.istft(clean_spec, nperseg=nperseg, noverlap=noverlap)
        _, removed_mono = scipy_signal.istft(removed_spec, nperseg=nperseg, noverlap=noverlap)
        clean_mono = clean_mono[:n_samples].astype(np.float32)
        removed_mono = removed_mono[:n_samples].astype(np.float32)

        if orig.ndim == 2:
            gain = np.abs(clean_mono) / (np.abs(mix) + 1e-8)
            gain = np.clip(gain, 0.0, 1.0)
            clean = orig.copy()
            channel_count = orig.shape[-1] if orig.shape[-1] <= orig.shape[0] else orig.shape[0]
            for channel_index in range(channel_count):
                if orig.shape[-1] <= orig.shape[0]:
                    clean[:, channel_index] = orig[:, channel_index] * gain
                else:
                    clean[channel_index, :] = orig[channel_index, :] * gain
            removed = orig - clean
        else:
            clean = clean_mono
            removed = removed_mono
        return removed.astype(np.float32), clean.astype(np.float32), "wiener_mask"

    def _resample_back(self, tensor: torch.Tensor,
                       target_sr: int) -> torch.Tensor:
        if target_sr == TARGET_SAMPLE_RATE:
            return tensor
        if target_sr not in self._resample_out:
            self._resample_out[target_sr] = torchaudio.transforms.Resample(
                orig_freq=TARGET_SAMPLE_RATE, new_freq=target_sr,
            )
        return self._resample_out[target_sr](tensor.cpu())

    @staticmethod
    def _to_numpy(tensor: torch.Tensor,
                  original: Union[np.ndarray, torch.Tensor]) -> np.ndarray:
        out = tensor.squeeze(0).cpu().numpy()
        orig_len = (original.shape[0] if isinstance(original, np.ndarray)
                    and original.ndim == 1 else
                    original.shape[-1] if isinstance(original, torch.Tensor)
                    else original.shape[0])
        if out.ndim == 1:
            if out.shape[0] < orig_len:
                out = np.pad(out, (0, orig_len - out.shape[0]), mode="constant")
            else:
                out = out[:orig_len]
        else:
            if out.shape[-1] < orig_len:
                out = np.pad(out, ((0, 0), (0, orig_len - out.shape[-1])), mode="constant")
            else:
                out = out[:, :orig_len]
        ndim = (original.ndim if isinstance(original, np.ndarray)
                else original.ndim)
        if ndim == 1 and out.ndim > 1:
            out = out.squeeze()
        elif ndim == 2 and out.ndim == 1:
            out = out.reshape(-1, 1)
        return out


__all__ = ["TARGET_SAMPLE_RATE", "STEMS", "CodecSepSeparator"]
