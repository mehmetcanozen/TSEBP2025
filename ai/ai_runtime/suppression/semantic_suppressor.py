"""
Semantic Noise Suppressor - Core Intelligence.

Waveformer uses spectral masking (``wiener_dd`` or ``cirm``).
CodecSep defaults to V5 fixed-category class-id separation, with legacy prompt
paths kept only for compatibility.
"""

from __future__ import annotations

from dataclasses import replace
import logging
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional, Sequence, Union

import numpy as np
import yaml

from ai.ai_runtime.separation.codecsep_query import CodecSepQueryPlan
from ai.ai_runtime.separation.codecsep_separator import DEFAULT_PROMPTS as DEFAULT_CODECSEP_PROMPTS
from ai.ai_runtime.suppression.masking import CIRMMasking, MaskingStrategy, WienerDDMasking
from ai.ai_runtime.utils.codecsep import (
    FixedCategoryRuntimeCatalog,
    collapse_codecsep_prompt_value,
    normalize_codecsep_prompt_map,
    normalize_codecsep_prompt_value,
)
from ai.ai_runtime.utils.paths import (
    get_audiosep_hive15cat_onnx_path,
    get_codecsep_fixed_category_gate_thresholds_path,
    get_codecsep_fixed_category_identity_path,
    get_codecsep_runtime_fixed_category_mapping_path,
    get_config_path,
)

if TYPE_CHECKING:
    from ai.ai_runtime.detection import SemanticDetective
    from ai.ai_runtime.enhancement import SpeechEnhancer
    from ai.ai_runtime.separation import (
        AudioSepHive15CatSeparator,
        CodecSepSeparator,
        UniversalSeparator,
        WaveformerSeparator,
    )

logger = logging.getLogger(__name__)

try:
    from ai.ai_runtime.profiles.profiler import get_profiler

    profiler = get_profiler()
except ImportError:
    profiler = None
    logger.warning("Profiler not available, performance tracking disabled")

DEFAULT_MAPPING_PATH = get_config_path("yamnet_to_waveformer.yaml")
AUDIOSEP_HIVE15CAT_MAPPING_PATH = get_config_path("audiosep_hive15cat_categories.yaml")
CODECSEP_MAPPING_PATH = get_config_path("category_to_codecsep.yaml")
CODECSEP_FIXEDSET_MAPPING_PATH = get_codecsep_runtime_fixed_category_mapping_path()
CODECSEP_FIXEDSET_IDENTITY_PATH = get_codecsep_fixed_category_identity_path()
CODECSEP_FIXEDSET_THRESHOLDS_PATH = get_codecsep_fixed_category_gate_thresholds_path()

SEPARATOR_BACKENDS = ("waveformer", "codecsep", "audiosep_hive15cat")
MASKING_METHODS = ("wiener_dd", "cirm")


def _build_masking_strategy(
    method: str,
    nperseg: int = 2048,
    dd_alpha: float = 0.98,
    floor_min: float = 0.01,
    floor_max: float = 0.05,
) -> Union[WienerDDMasking, CIRMMasking]:
    if method == "wiener_dd":
        return WienerDDMasking(
            nperseg=nperseg, dd_alpha=dd_alpha,
            perceptual_floor_min=floor_min, perceptual_floor_max=floor_max,
        )
    if method == "cirm":
        return CIRMMasking(
            nperseg=nperseg,
            perceptual_floor_min=floor_min, perceptual_floor_max=floor_max,
        )
    raise ValueError(f"Unknown masking method '{method}'. Choose from {MASKING_METHODS}")


class SemanticSuppressor:
    """Intelligent noise suppressor using semantic understanding.

    Parameters
    ----------
    separator_backend:
        ``"waveformer"`` (default, 41-class target extractor) or
        ``"codecsep"`` (V5 fixed-category latent masker with legacy prompt compatibility) or
        ``"audiosep_hive15cat"`` (exact-15 ONNX separator routed through post-masking).
    masking_method:
        ``"wiener_dd"`` (Ephraim-Malah Decision-Directed Wiener, default)
        or ``"cirm"`` (bounded phase-aware ratio masking).
    """

    def __init__(
        self,
        mapping_path: Optional[Path] = None,
        detector: Optional[SemanticDetective] = None,
        separator: Optional[WaveformerSeparator] = None,
        enhancer: Optional[SpeechEnhancer] = None,
        universal: Optional[UniversalSeparator] = None,
        audiosep_hive15cat: Optional[AudioSepHive15CatSeparator] = None,
        *,
        separator_backend: str = "waveformer",
        masking_method: str = "wiener_dd",
        audiosep_hive15cat_model_path: Optional[Union[str, Path]] = None,
        audiosep_hive15cat_device: Optional[str] = None,
        codecsep_checkpoint_path: Optional[Union[str, Path]] = None,
        codecsep_device: Optional[str] = None,
        codecsep_prompts: Optional[Dict[str, Sequence[str]]] = None,
    ) -> None:
        if separator_backend not in SEPARATOR_BACKENDS:
            raise ValueError(
                f"Unknown separator_backend '{separator_backend}'. "
                f"Choose from {SEPARATOR_BACKENDS}"
            )
        if masking_method not in MASKING_METHODS:
            raise ValueError(
                f"Unknown masking_method '{masking_method}'. "
                f"Choose from {MASKING_METHODS}"
            )

        self.separator_backend = separator_backend
        self.masking_method = masking_method
        self.audiosep_hive15cat_model_path = (
            Path(audiosep_hive15cat_model_path)
            if audiosep_hive15cat_model_path
            else get_audiosep_hive15cat_onnx_path()
        )
        self.audiosep_hive15cat_device = audiosep_hive15cat_device
        self.codecsep_checkpoint_path = (
            Path(codecsep_checkpoint_path) if codecsep_checkpoint_path else None
        )
        self.codecsep_device = codecsep_device
        self.codecsep_prompts = normalize_codecsep_prompt_map(
            codecsep_prompts or dict(DEFAULT_CODECSEP_PROMPTS)
        )

        self.mapping_path = mapping_path or self._default_mapping_path(separator_backend)
        self.category_map = self._load_mapping(self.mapping_path)

        codecsep_mapping = self._load_codecsep_mapping()
        self._codecsep_stem_map = codecsep_mapping.get("stems", {})
        self._codecsep_prompt_map = codecsep_mapping.get("prompts", {})
        self._codecsep_query_map = codecsep_mapping.get("queries", {})
        self._codecsep_fixed_catalog = FixedCategoryRuntimeCatalog.load(
            identity_path=CODECSEP_FIXEDSET_IDENTITY_PATH,
            mapping_path=CODECSEP_FIXEDSET_MAPPING_PATH,
            threshold_path=CODECSEP_FIXEDSET_THRESHOLDS_PATH,
        )

        self._detector = detector
        self._separator = separator
        self._audiosep_hive15cat = audiosep_hive15cat
        self._audiosep_hive15cat_key: tuple[str | None, str | None] | None = (
            (str(self.audiosep_hive15cat_model_path), self.audiosep_hive15cat_device)
            if audiosep_hive15cat is not None
            else None
        )
        self._codecsep_separator: CodecSepSeparator | None = None
        self._codecsep_separator_key: tuple[str | None, str | None] | None = None
        self._enhancer = enhancer
        self._universal = universal
        self._overlap_save_tail = None
        self._codecsep_query_cache: dict[tuple, str] = {}
        self._last_codecsep_removed_audio: np.ndarray | None = None

        # Waveformer separation params
        self.weak_stem_boost_cap = 4.5
        self.under_extract_scale = 2.0

        # Masking params
        self.spectral_nperseg = 2048
        self.perceptual_floor_min = 0.01
        self.perceptual_floor_max = 0.05
        self.dd_alpha = 0.98

        self._masking_cache: dict[str, MaskingStrategy] = {}
        self._masking_cache[masking_method] = _build_masking_strategy(
            masking_method,
            nperseg=self.spectral_nperseg,
            dd_alpha=self.dd_alpha,
            floor_min=self.perceptual_floor_min,
            floor_max=self.perceptual_floor_max,
        )

    @staticmethod
    def _default_mapping_path(separator_backend: str) -> Path:
        if separator_backend == "audiosep_hive15cat":
            return AUDIOSEP_HIVE15CAT_MAPPING_PATH
        return DEFAULT_MAPPING_PATH

    # ------------------------------------------------------------------
    # Lazy-loading properties
    # ------------------------------------------------------------------

    @property
    def enhancer(self) -> SpeechEnhancer:
        if self._enhancer is None:
            from ai.ai_runtime.enhancement import SpeechEnhancer

            logger.info("Initializing SpeechEnhancer...")
            self._enhancer = SpeechEnhancer()
        return self._enhancer

    @property
    def detector(self) -> SemanticDetective:
        if self._detector is None:
            try:
                from ai.ai_runtime.detection.semantic_detective import SemanticDetective
            except ImportError as exc:
                raise ImportError(
                    "SemanticDetective dependencies could not be imported. "
                    "If you only need always-suppress categories such as typing or pets, "
                    "use those categories so detection can be bypassed. "
                    "Otherwise fix the TensorFlow/protobuf environment."
                ) from exc

            logger.info("Initializing SemanticDetective...")
            self._detector = SemanticDetective()
        return self._detector

    def _category_effective_threshold(
        self,
        category: str,
        detection_threshold: float,
    ) -> float:
        cat_config = self.category_map.get(category, {})
        if detection_threshold < 0:
            return detection_threshold
        return cat_config.get("detection_threshold", detection_threshold)

    def _requires_detection(
        self,
        suppress_categories: Sequence[str],
        universal_prompts: Sequence[str],
        detection_threshold: float,
    ) -> bool:
        if universal_prompts:
            return False
        if not suppress_categories:
            return False
        for category in suppress_categories:
            if category not in self.category_map:
                continue
            if self._category_effective_threshold(category, detection_threshold) >= 0:
                return True
        return False

    @property
    def separator(self) -> WaveformerSeparator:
        if self._separator is None:
            from ai.ai_runtime.separation import WaveformerSeparator

            logger.info("Initializing WaveformerSeparator...")
            self._separator = WaveformerSeparator()
        return self._separator

    @property
    def universal_separator(self) -> UniversalSeparator:
        if self._universal is None:
            from ai.ai_runtime.separation import UniversalSeparator

            logger.info("Initializing UniversalSeparator (AudioSep)...")
            self._universal = UniversalSeparator()
        return self._universal

    @property
    def audiosep_hive15cat_separator(self):
        """Lazy-load the exact-15 AudioSep ONNX separator."""
        return self._get_audiosep_hive15cat_separator()

    @property
    def codecsep_separator(self):
        """Lazy-load the CodecSep separator (only when backend == codecsep)."""
        return self._get_codecsep_separator()

    def _get_masking_strategy(self, method: str) -> MaskingStrategy:
        if method not in self._masking_cache:
            self._masking_cache[method] = _build_masking_strategy(
                method,
                nperseg=self.spectral_nperseg,
                dd_alpha=self.dd_alpha,
                floor_min=self.perceptual_floor_min,
                floor_max=self.perceptual_floor_max,
            )
        return self._masking_cache[method]

    def _get_codecsep_separator(
        self,
        checkpoint_path: Optional[Union[str, Path]] = None,
        device: Optional[str] = None,
    ):
        requested_path = (
            Path(checkpoint_path)
            if checkpoint_path is not None
            else self.codecsep_checkpoint_path
        )
        requested_device = device if device is not None else self.codecsep_device
        cache_key = (
            str(requested_path) if requested_path is not None else None,
            requested_device,
        )
        if (
            self._codecsep_separator is not None
            and (
                self._codecsep_separator_key == cache_key
                or (
                    self._codecsep_separator_key is None
                    and requested_path is None
                    and requested_device is None
                )
            )
        ):
            return self._codecsep_separator

        from ai.ai_runtime.separation.codecsep_separator import CodecSepSeparator

        logger.info("Initializing CodecSepSeparator...")
        self._codecsep_separator = CodecSepSeparator(
            checkpoint_path=requested_path,
            device=requested_device,
            prompts=self.codecsep_prompts,
        )
        self._codecsep_separator_key = cache_key
        return self._codecsep_separator

    def _get_audiosep_hive15cat_separator(
        self,
        model_path: Optional[Union[str, Path]] = None,
        device: Optional[str] = None,
    ):
        requested_path = (
            Path(model_path)
            if model_path is not None
            else self.audiosep_hive15cat_model_path
        )
        requested_device = device if device is not None else self.audiosep_hive15cat_device
        cache_key = (
            str(requested_path) if requested_path is not None else None,
            requested_device,
        )
        if (
            self._audiosep_hive15cat is not None
            and (
                self._audiosep_hive15cat_key == cache_key
                or (
                    self._audiosep_hive15cat_key is None
                    and requested_path is None
                    and requested_device is None
                )
            )
        ):
            return self._audiosep_hive15cat

        from ai.ai_runtime.separation import AudioSepHive15CatSeparator

        logger.info("Initializing AudioSepHive15CatSeparator...")
        self._audiosep_hive15cat = AudioSepHive15CatSeparator(
            model_path=requested_path,
            device=requested_device,
        )
        self._audiosep_hive15cat_key = cache_key
        return self._audiosep_hive15cat

    @staticmethod
    def _sum_audio_tracks(tracks: Sequence[np.ndarray], reference: np.ndarray) -> np.ndarray:
        if not tracks:
            return np.zeros_like(reference)

        total = np.array(tracks[0], copy=True)
        for track in tracks[1:]:
            min_samples = min(total.shape[0], track.shape[0])
            total[:min_samples] += track[:min_samples]
        return total

    def _boost_under_extracted_stem(
        self,
        stem: np.ndarray,
        mix_rms: float,
        max_detection_confidence: float,
    ) -> np.ndarray:
        if self.weak_stem_boost_cap <= 1.0 or max_detection_confidence < 0.2:
            return stem

        stem_rms = np.sqrt(np.mean(stem ** 2))
        relative_level = stem_rms / mix_rms
        if relative_level >= 0.3:
            return stem

        boost = min(0.3 / (relative_level + 1e-8), self.weak_stem_boost_cap)
        if boost <= 1.0:
            return stem
        return stem * boost

    def _effective_category_aggressiveness(
        self,
        per_category_targets: list[tuple[str, list]],
        base_aggressiveness: float,
    ) -> float:
        effective = base_aggressiveness
        for cat, _ in per_category_targets:
            override = self.category_map.get(cat, {}).get("aggressiveness_override", 0)
            effective = max(effective, float(override or 0.0))
        return effective

    def reset_runtime_state(self) -> None:
        """Clear chunk-to-chunk state used by offline processing."""
        self._overlap_save_tail = None
        self._codecsep_query_cache.clear()
        self._last_codecsep_removed_audio = None

    def get_last_codecsep_removed_audio(self) -> np.ndarray | None:
        """Return the last exact target audio produced by the CodecSep path."""
        if self._last_codecsep_removed_audio is None:
            return None
        return np.array(self._last_codecsep_removed_audio, copy=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def suppress(
        self,
        audio: np.ndarray,
        sample_rate: int,
        suppress_categories: Sequence[str] = (),
        detection_threshold: float = 0.5,
        aggressiveness: float = 1.0,
        suppress_all: bool = False,
        universal_prompts: Sequence[str] = (),
        separator_backend: Optional[str] = None,
        masking_method: Optional[str] = None,
        audiosep_hive15cat_model_path: Optional[Union[str, Path]] = None,
        audiosep_hive15cat_device: Optional[str] = None,
        audiosep_hive15cat_realtime_hop_seconds: Optional[float] = None,
        codecsep_checkpoint_path: Optional[Union[str, Path]] = None,
        codecsep_device: Optional[str] = None,
        codecsep_prompt_overrides: Optional[Dict[str, Sequence[str]]] = None,
        codecsep_negative_prompts: Optional[Sequence[str]] = None,
        codecsep_preserve_prompts: Optional[Sequence[str]] = None,
        codecsep_mode: str = "fixed_category",
        codecsep_query_strategy: str = "single_pass",
        codecsep_multistep_steps: int = 0,
        codecsep_stereo_mode: str = "mono_shared",
        codecsep_product_categories: Optional[Sequence[str]] = None,
        codecsep_hive_class_ids: Optional[Sequence[Union[int, str]]] = None,
        codecsep_fixed_merge_policy: str = "wiener_mask",
        mask_floor: Optional[float] = None,
        max_suppression_ratio: Optional[float] = None,
        speech_dominance_threshold: Optional[float] = None,
        return_details: bool = False,
    ) -> Union[np.ndarray, dict[str, object]]:
        del audiosep_hive15cat_realtime_hop_seconds
        effective_backend = separator_backend or self.separator_backend
        effective_masking_method = masking_method or self.masking_method
        resolved_codecsep_mode = self._resolve_codecsep_mode(codecsep_mode)
        self._last_codecsep_removed_audio = None
        if effective_backend not in SEPARATOR_BACKENDS:
            raise ValueError(
                f"Unknown separator_backend '{effective_backend}'. "
                f"Choose from {SEPARATOR_BACKENDS}"
            )
        if effective_masking_method not in MASKING_METHODS:
            raise ValueError(
                f"Unknown masking_method '{effective_masking_method}'. "
                f"Choose from {MASKING_METHODS}"
            )
        if resolved_codecsep_mode not in {"fixed_category", "compat", "audiocaps_native", "experimental_search"}:
            raise ValueError(
                "codecsep_mode must resolve to one of: fixed_category, compat, audiocaps_native, experimental_search"
            )
        if codecsep_query_strategy not in {"single_pass", "slot_search"}:
            raise ValueError("codecsep_query_strategy must be one of: single_pass, slot_search")
        if codecsep_stereo_mode not in {"mono_shared", "per_channel"}:
            raise ValueError("codecsep_stereo_mode must be one of: mono_shared, per_channel")
        if resolved_codecsep_mode == "fixed_category" and universal_prompts:
            raise ValueError(
                "universal_prompts are not supported in codecsep fixed_category mode. "
                "Use compat or experimental_search with a prompt-conditioned checkpoint instead."
            )

        if suppress_all:
            if profiler:
                profiler.start("speech_enhancement")
            clean_audio = self.enhancer.enhance(audio, sample_rate)
            if profiler:
                profiler.end("speech_enhancement")
            return self._finalize_suppress_output(
                original_audio=audio,
                clean_audio=clean_audio,
                effective_backend=effective_backend,
                resolved_codecsep_mode=resolved_codecsep_mode,
                return_details=return_details,
            )

        if (
            len(suppress_categories) == 0
            and not universal_prompts
            and not codecsep_product_categories
            and not codecsep_hive_class_ids
        ):
            self._overlap_save_tail = None
            return self._finalize_suppress_output(
                original_audio=audio,
                clean_audio=np.array(audio, copy=True),
                effective_backend=effective_backend,
                resolved_codecsep_mode=resolved_codecsep_mode,
                return_details=return_details,
            )

        # --- Detection ---
        if (
            effective_backend == "codecsep"
            and (suppress_categories or universal_prompts or codecsep_product_categories or codecsep_hive_class_ids)
        ):
            detections = None
            smoothed_scores: dict = {}
        elif universal_prompts or not self._requires_detection(
            suppress_categories=suppress_categories,
            universal_prompts=universal_prompts,
            detection_threshold=detection_threshold,
        ):
            detections = None
            smoothed_scores: dict = {}
        else:
            if profiler:
                profiler.start("yamnet_detection")
            detections = self.detector.classify(audio, sample_rate)
            smoothed_scores = detections["smoothed"]
            if profiler:
                profiler.end("yamnet_detection")

        states = detections.get("states", {}) if detections else {}
        per_category_targets: list[tuple[str, list]] = []
        targets_to_suppress: list = []
        max_detection_confidence = 0.0
        has_transient_category = False

        for category in suppress_categories:
            if category not in self.category_map:
                logger.warning("Unknown category '%s', skipping", category)
                continue

            cat_config = self.category_map[category]

            if effective_backend == "codecsep":
                if resolved_codecsep_mode == "fixed_category":
                    cat_targets = self._get_codecsep_fixed_targets(category)
                else:
                    cat_targets = self._get_codecsep_stems(category)
            elif effective_backend == "audiosep_hive15cat":
                cat_targets = cat_config.get("audiosep15_targets", [])
            else:
                cat_targets = cat_config.get("waveformer_targets", [])

            if not cat_targets:
                continue

            if effective_backend == "codecsep":
                per_category_targets.append((category, cat_targets))
                targets_to_suppress.extend(cat_targets)
                max_detection_confidence = max(max_detection_confidence, 0.9)
                if cat_config.get("transient", False):
                    has_transient_category = True
                continue

            if effective_backend == "audiosep_hive15cat":
                per_category_targets.append((category, cat_targets))
                targets_to_suppress.extend(cat_targets)
                max_detection_confidence = max(max_detection_confidence, 0.9)
                if cat_config.get("transient", False):
                    has_transient_category = True
                continue

            confidence = smoothed_scores.get(category, 0.0)
            effective_threshold = self._category_effective_threshold(
                category, detection_threshold,
            )

            use_stability_gate = effective_threshold >= 0.4
            meets_threshold = effective_threshold < 0 or confidence >= effective_threshold
            is_stable = states.get(category, False) if use_stability_gate else True

            if effective_threshold < 0 or (meets_threshold and is_stable):
                if effective_threshold < 0:
                    confidence = max(confidence, 0.9)
                per_category_targets.append((category, cat_targets))
                targets_to_suppress.extend(cat_targets)
                max_detection_confidence = max(max_detection_confidence, confidence)
                if cat_config.get("transient", False):
                    has_transient_category = True

        has_explicit_fixed_targets = bool(codecsep_product_categories or codecsep_hive_class_ids)
        if not targets_to_suppress and not universal_prompts and not has_explicit_fixed_targets:
            self._overlap_save_tail = None
            return self._finalize_suppress_output(
                original_audio=audio,
                clean_audio=np.array(audio, copy=True),
                effective_backend=effective_backend,
                resolved_codecsep_mode=resolved_codecsep_mode,
                return_details=return_details,
            )

        # --- Separation ---
        if effective_backend == "codecsep" and (
            universal_prompts or suppress_categories or codecsep_product_categories or codecsep_hive_class_ids
        ):
            logger.info(
                "CodecSep %s suppression active; masking_method='%s' is ignored because CodecSep performs semantic separation directly.",
                resolved_codecsep_mode,
                effective_masking_method,
            )
            if resolved_codecsep_mode == "fixed_category":
                clean_audio = self._suppress_codecsep_fixed_category(
                    audio,
                    sample_rate,
                    per_category_targets,
                    suppress_categories=suppress_categories,
                    codecsep_checkpoint_path=codecsep_checkpoint_path,
                    codecsep_device=codecsep_device,
                    codecsep_product_categories=codecsep_product_categories,
                    codecsep_hive_class_ids=codecsep_hive_class_ids,
                    codecsep_fixed_merge_policy=codecsep_fixed_merge_policy,
                    aggressiveness=aggressiveness,
                    explicit_prompt_overrides=codecsep_prompt_overrides,
                )
            else:
                clean_audio = self._suppress_codecsep_query_first(
                    audio,
                    sample_rate,
                    per_category_targets,
                    smoothed_scores,
                    suppress_categories=suppress_categories,
                    universal_prompts=universal_prompts,
                    aggressiveness=aggressiveness,
                    codecsep_checkpoint_path=codecsep_checkpoint_path,
                    codecsep_device=codecsep_device,
                    explicit_prompt_overrides=codecsep_prompt_overrides,
                    negative_prompts=codecsep_negative_prompts,
                    preserve_prompts=codecsep_preserve_prompts,
                    mode=resolved_codecsep_mode,
                    query_strategy=codecsep_query_strategy,
                    multistep_steps=codecsep_multistep_steps,
                )
            if audio.ndim == 1:
                clean_audio = clean_audio.flatten()
            return self._finalize_suppress_output(
                original_audio=audio,
                clean_audio=clean_audio,
                effective_backend=effective_backend,
                resolved_codecsep_mode=resolved_codecsep_mode,
                return_details=return_details,
            )
        elif universal_prompts:
            unwanted_audio, separation_ratio = self._separate_universal(
                audio, sample_rate, universal_prompts,
            )
            max_detection_confidence = 0.9
        elif effective_backend == "audiosep_hive15cat":
            unwanted_audio, separation_ratio = self._separate_audiosep_hive15cat(
                audio,
                sample_rate,
                per_category_targets,
                model_path=audiosep_hive15cat_model_path,
                device=audiosep_hive15cat_device,
            )
        else:
            unwanted_audio, separation_ratio = self._separate_waveformer(
                audio, sample_rate, per_category_targets, max_detection_confidence,
            )

        # --- Masking ---
        if profiler:
            profiler.start("spectral_masking")

        # Under-extraction compensation
        under_extract_threshold = 0.3
        under_extract_scale = self.under_extract_scale
        if effective_backend == "audiosep_hive15cat":
            # AudioSep15 estimates are already category-specific and can sound brittle
            # if we push the unwanted track too hard before masking.
            under_extract_threshold = 0.18
            under_extract_scale = min(self.under_extract_scale, 1.15)
        if (
            under_extract_scale > 1.0
            and 1e-6 < separation_ratio < under_extract_threshold
        ):
            scale = min(
                under_extract_scale,
                under_extract_threshold / separation_ratio,
            )
            unwanted_audio = unwanted_audio * scale

        effective_aggressiveness = self._effective_category_aggressiveness(
            per_category_targets,
            aggressiveness,
        )

        effective_mask_floor = mask_floor
        effective_max_suppression_ratio = max_suppression_ratio
        effective_speech_dominance_threshold = speech_dominance_threshold
        if effective_backend == "audiosep_hive15cat":
            if effective_mask_floor is None:
                effective_mask_floor = (
                    0.07 if effective_masking_method == "wiener_dd" else 0.05
                )
            if effective_max_suppression_ratio is None:
                effective_max_suppression_ratio = 0.82
            if effective_speech_dominance_threshold is None:
                effective_speech_dominance_threshold = 2.5

        # Transient categories: shorter STFT + faster alpha
        mask_nperseg = 1024 if has_transient_category else self.spectral_nperseg
        mask_dd_alpha = 0.92 if has_transient_category else self.dd_alpha

        masking = self._get_masking_strategy(effective_masking_method)
        clean_audio = masking.apply(
            mix=audio,
            unwanted=unwanted_audio,
            aggressiveness=effective_aggressiveness,
            sample_rate=sample_rate,
            nperseg=mask_nperseg,
            dd_alpha=mask_dd_alpha,
            mask_floor=effective_mask_floor,
            max_suppression_ratio=effective_max_suppression_ratio,
            speech_dominance_threshold=effective_speech_dominance_threshold,
        )

        if profiler:
            profiler.end("spectral_masking")

        if audio.ndim == 1:
            clean_audio = clean_audio.flatten()
        return self._finalize_suppress_output(
            original_audio=audio,
            clean_audio=clean_audio,
            effective_backend=effective_backend,
            resolved_codecsep_mode=resolved_codecsep_mode,
            return_details=return_details,
        )

    def detect_categories(
        self,
        audio: np.ndarray,
        sample_rate: int,
        threshold: float = 0.3,
    ) -> Dict[str, float]:
        detections = self.detector.classify(audio, sample_rate)
        smoothed = detections["smoothed"]
        return {cat: conf for cat, conf in smoothed.items() if conf >= threshold}

    # ------------------------------------------------------------------
    # Separation back-ends (private)
    # ------------------------------------------------------------------

    def _separate_waveformer(
        self,
        audio: np.ndarray,
        sample_rate: int,
        per_category_targets: list[tuple[str, list]],
        max_detection_confidence: float,
    ) -> tuple[np.ndarray, float]:
        if profiler:
            profiler.start("input_normalization")
        max_val = np.max(np.abs(audio))
        if max_val < 1e-8:
            if profiler:
                profiler.end("input_normalization")
            return np.zeros_like(audio), 0.0
        scale_factor = 1.0 / max_val
        audio_norm = audio * scale_factor
        if profiler:
            profiler.end("input_normalization")

        if profiler:
            profiler.start("waveformer_separation")
        target_groups = [list(set(ct)) for _, ct in per_category_targets]
        if hasattr(self.separator, "separate_multi_query"):
            stems = self.separator.separate_multi_query(
                audio=audio_norm, sample_rate=sample_rate,
                target_groups=target_groups,
            )
        else:
            stems = [
                self.separator.separate(
                    audio=audio_norm, sample_rate=sample_rate, targets=tg,
                )
                for tg in target_groups
            ]

        mix_rms = np.sqrt(np.mean(audio_norm ** 2)) + 1e-8
        for i, stem in enumerate(stems):
            stems[i] = self._boost_under_extracted_stem(
                stem,
                mix_rms,
                max_detection_confidence,
            )

        unwanted_norm = stems[0]
        for stem in stems[1:]:
            min_samples = min(unwanted_norm.shape[0], stem.shape[0])
            unwanted_norm[:min_samples] += stem[:min_samples]
        if profiler:
            profiler.end("waveformer_separation")

        unwanted_audio = unwanted_norm * (1.0 / scale_factor)

        mix_rms_post = np.sqrt(np.mean(audio[: unwanted_audio.shape[0]] ** 2)) + 1e-8
        unwanted_rms = np.sqrt(np.mean(unwanted_audio ** 2)) + 1e-8
        separation_ratio = unwanted_rms / mix_rms_post
        return unwanted_audio, separation_ratio

    def _separate_audiosep_hive15cat(
        self,
        audio: np.ndarray,
        sample_rate: int,
        per_category_targets: list[tuple[str, list]],
        *,
        model_path: Optional[Union[str, Path]] = None,
        device: Optional[str] = None,
    ) -> tuple[np.ndarray, float]:
        if profiler:
            profiler.start("audiosep_hive15cat_separation")

        labels: list[str] = []
        for _, targets in per_category_targets:
            for target in targets:
                if target not in labels:
                    labels.append(str(target))

        if not labels:
            if profiler:
                profiler.end("audiosep_hive15cat_separation")
            return np.zeros_like(audio), 0.0

        separator = self._get_audiosep_hive15cat_separator(
            model_path=model_path,
            device=device,
        )
        unwanted_audio = separator.separate(
            audio=audio,
            sample_rate=sample_rate,
            categories=labels,
        )
        if profiler:
            profiler.end("audiosep_hive15cat_separation")

        min_len = min(audio.shape[0], unwanted_audio.shape[0])
        mix_rms = np.sqrt(np.mean(audio[:min_len] ** 2)) + 1e-8
        unwanted_rms = np.sqrt(np.mean(unwanted_audio[:min_len] ** 2)) + 1e-8
        return unwanted_audio, unwanted_rms / mix_rms

    @staticmethod
    def _resolve_codecsep_mode(mode: str) -> str:
        if mode == "query_first":
            return "experimental_search"
        if mode == "auto":
            return "fixed_category"
        return mode

    def _finalize_suppress_output(
        self,
        *,
        original_audio: np.ndarray,
        clean_audio: np.ndarray,
        effective_backend: str,
        resolved_codecsep_mode: str,
        return_details: bool,
    ) -> Union[np.ndarray, dict[str, object]]:
        if not return_details:
            return clean_audio
        removed_audio = self.get_last_codecsep_removed_audio()
        if removed_audio is None:
            removed_audio = (
                np.asarray(original_audio, dtype=np.float32)
                - np.asarray(clean_audio, dtype=np.float32)
            )
        return {
            "clean_audio": clean_audio,
            "removed_audio": np.asarray(removed_audio, dtype=np.asarray(original_audio).dtype),
            "backend": effective_backend,
            "codecsep_mode": resolved_codecsep_mode,
        }

    def _codecsep_query_cfg(self, category: str) -> dict:
        cfg = dict(self._codecsep_query_map.get(category) or {})
        if cfg:
            return cfg

        stems = self._get_codecsep_stems(category)
        prompts = self._get_codecsep_prompt_values(category)
        if not stems:
            return {}
        preferred_slot = stems[0]
        return {
            "positive_prompts": prompts,
            "preferred_slot": preferred_slot,
            "alternate_slots": [slot for slot in stems[1:] if slot != preferred_slot],
            "reconstruction_policy": "keep_complement" if preferred_slot in {"speech", "music"} else "subtract_target",
            "default_aggressiveness": self.category_map.get(category, {}).get("aggressiveness_override", 0),
            "use_multistep": preferred_slot == "sfx",
        }

    def _compile_codecsep_native_plans(
        self,
        *,
        suppress_categories: Sequence[str],
        per_category_targets: list[tuple[str, list]],
        explicit_prompt_overrides: Optional[Dict[str, Sequence[str]]],
        universal_prompts: Sequence[str],
        aggressiveness: float,
        mode: str,
    ) -> list[CodecSepQueryPlan]:
        explicit_map = normalize_codecsep_prompt_map(explicit_prompt_overrides)
        if universal_prompts:
            target_prompts = normalize_codecsep_prompt_value(universal_prompts)
            if "sfx" in explicit_map:
                target_prompts = target_prompts + list(explicit_map["sfx"])
            return [
                CodecSepQueryPlan(
                    target_prompts=target_prompts,
                    preferred_slot="sfx",
                    slot_prompt_overrides={
                        slot: prompts for slot, prompts in explicit_map.items() if slot != "sfx"
                    },
                    reconstruction_policy="subtract_target",
                    query_strategy="single_pass",
                    multistep_steps=0,
                    aggressiveness=aggressiveness,
                    mode=mode,  # type: ignore[arg-type]
                    use_multistep=False,
                    target_label="universal",
                    debug_context={"categories": [], "universal": list(universal_prompts)},
                ).normalized()
            ]

        active_categories = {category for category, _ in per_category_targets}
        grouped: dict[tuple[str, str], dict[str, object]] = {}
        for category in suppress_categories:
            if category not in active_categories:
                continue
            cfg = self._codecsep_query_cfg(category)
            if not cfg:
                continue
            preferred_slot = str(cfg.get("preferred_slot", "sfx"))
            reconstruction_policy = str(
                cfg.get(
                    "reconstruction_policy",
                    "keep_complement" if preferred_slot in {"speech", "music"} else "subtract_target",
                )
            )
            group = grouped.setdefault(
                (preferred_slot, reconstruction_policy),
                {
                    "categories": [],
                    "positive_prompts": [],
                    "negative_prompts": [],
                    "default_aggressiveness": aggressiveness,
                },
            )
            group["categories"].append(category)
            group["positive_prompts"].extend(
                normalize_codecsep_prompt_value(
                    cfg.get("positive_prompts") or self._get_codecsep_prompt_values(category)
                )
            )
            group["negative_prompts"].extend(
                normalize_codecsep_prompt_value(cfg.get("negative_prompts"))
            )
            group["default_aggressiveness"] = max(
                float(group["default_aggressiveness"]),
                float(cfg.get("default_aggressiveness", 0) or 0.0),
            )

        plans: list[CodecSepQueryPlan] = []
        for (preferred_slot, reconstruction_policy), group in grouped.items():
            target_prompts = normalize_codecsep_prompt_value(group["positive_prompts"])
            if preferred_slot in explicit_map:
                target_prompts = target_prompts + list(explicit_map[preferred_slot])
            plans.append(
                CodecSepQueryPlan(
                    target_prompts=target_prompts,
                    negative_prompts=normalize_codecsep_prompt_value(group["negative_prompts"]),
                    preferred_slot=preferred_slot,  # type: ignore[arg-type]
                    slot_prompt_overrides={
                        slot: prompts
                        for slot, prompts in explicit_map.items()
                        if slot != preferred_slot
                    },
                    reconstruction_policy=reconstruction_policy,  # type: ignore[arg-type]
                    query_strategy="single_pass",
                    multistep_steps=0,
                    aggressiveness=float(group["default_aggressiveness"]),
                    mode=mode,  # type: ignore[arg-type]
                    use_multistep=False,
                    target_label=", ".join(group["categories"]),
                    debug_context={"categories": list(group["categories"])},
                ).normalized()
            )
        return plans

    def _compile_codecsep_experimental_plans(
        self,
        *,
        suppress_categories: Sequence[str],
        per_category_targets: list[tuple[str, list]],
        explicit_prompt_overrides: Optional[Dict[str, Sequence[str]]],
        universal_prompts: Sequence[str],
        negative_prompts: Optional[Sequence[str]],
        preserve_prompts: Optional[Sequence[str]],
        aggressiveness: float,
        mode: str,
        query_strategy: str,
        multistep_steps: int,
    ) -> list[CodecSepQueryPlan]:
        explicit_map = normalize_codecsep_prompt_map(explicit_prompt_overrides)
        if universal_prompts:
            target_prompts = normalize_codecsep_prompt_value(universal_prompts)
            if "sfx" in explicit_map:
                target_prompts = target_prompts + list(explicit_map["sfx"])
            plan = CodecSepQueryPlan(
                target_prompts=target_prompts,
                preferred_slot="sfx",
                alternate_slots=["speech", "music"],
                slot_prompt_overrides=explicit_map,
                negative_prompts=normalize_codecsep_prompt_value(negative_prompts),
                preserve_prompts=normalize_codecsep_prompt_value(preserve_prompts),
                reconstruction_policy="subtract_target",
                query_strategy=query_strategy,
                multistep_steps=multistep_steps,
                aggressiveness=aggressiveness,
                mode=mode,
                use_multistep=multistep_steps > 1,
                target_label="universal",
                debug_context={"categories": [], "universal": list(universal_prompts)},
            )
            return [plan.normalized()]

        active_categories = {category for category, _ in per_category_targets}
        grouped: dict[tuple[str, str], dict[str, object]] = {}
        for category in suppress_categories:
            if category not in active_categories:
                continue
            cfg = self._codecsep_query_cfg(category)
            if not cfg:
                continue
            preferred_slot = str(cfg.get("preferred_slot", "sfx"))
            reconstruction_policy = str(cfg.get("reconstruction_policy", "subtract_target"))
            key = (preferred_slot, reconstruction_policy)
            group = grouped.setdefault(
                key,
                {
                    "categories": [],
                    "positive_prompts": [],
                    "negative_prompts": [],
                    "preserve_prompts": [],
                    "alternate_slots": [],
                    "slot_prompt_overrides": {},
                    "default_aggressiveness": aggressiveness,
                    "use_multistep": False,
                },
            )
            group["categories"].append(category)
            group["positive_prompts"].extend(
                normalize_codecsep_prompt_value(cfg.get("positive_prompts") or self._get_codecsep_prompt_values(category))
            )
            group["negative_prompts"].extend(
                normalize_codecsep_prompt_value(cfg.get("negative_prompts"))
            )
            group["preserve_prompts"].extend(
                normalize_codecsep_prompt_value(cfg.get("preserve_prompts"))
            )
            group["alternate_slots"].extend(list(cfg.get("alternate_slots") or []))
            group["default_aggressiveness"] = max(
                float(group["default_aggressiveness"]),
                float(cfg.get("default_aggressiveness", 0) or 0.0),
            )
            group["use_multistep"] = bool(group["use_multistep"] or cfg.get("use_multistep", False))

        plans: list[CodecSepQueryPlan] = []
        for (preferred_slot, reconstruction_policy), group in grouped.items():
            target_prompts = normalize_codecsep_prompt_value(group["positive_prompts"])
            if preferred_slot in explicit_map:
                target_prompts = target_prompts + list(explicit_map[preferred_slot])
            slot_prompt_overrides = {
                slot: prompt_values
                for slot, prompt_values in explicit_map.items()
                if slot != preferred_slot
            }
            plan = CodecSepQueryPlan(
                target_prompts=target_prompts,
                preferred_slot=preferred_slot,  # type: ignore[arg-type]
                alternate_slots=[slot for slot in list(group["alternate_slots"]) if slot != preferred_slot],
                slot_prompt_overrides=slot_prompt_overrides,
                negative_prompts=normalize_codecsep_prompt_value(group["negative_prompts"]) + normalize_codecsep_prompt_value(negative_prompts),
                preserve_prompts=normalize_codecsep_prompt_value(group["preserve_prompts"]) + normalize_codecsep_prompt_value(preserve_prompts),
                reconstruction_policy=reconstruction_policy,  # type: ignore[arg-type]
                query_strategy=query_strategy,
                multistep_steps=multistep_steps,
                aggressiveness=max(float(group["default_aggressiveness"]), float(aggressiveness)),
                mode=mode,  # type: ignore[arg-type]
                use_multistep=bool(group["use_multistep"]) and multistep_steps > 1,
                target_label=", ".join(group["categories"]),
                debug_context={"categories": list(group["categories"])},
            )
            plans.append(plan.normalized())
        return plans

    def _resolve_codecsep_fixed_request(
        self,
        *,
        suppress_categories: Sequence[str],
        codecsep_product_categories: Sequence[str] | None = None,
        codecsep_hive_class_ids: Sequence[Union[int, str]] | None = None,
    ) -> dict[str, Any]:
        if not self._codecsep_fixed_catalog.available:
            return {
                "class_ids": [],
                "product_categories": [],
                "labels": [],
                "unresolved": list(suppress_categories) + [str(item) for item in list(codecsep_product_categories or [])],
            }
        return self._codecsep_fixed_catalog.resolve_targets(
            class_ids=codecsep_hive_class_ids,
            product_categories=codecsep_product_categories,
            legacy_categories=suppress_categories,
        )

    def _suppress_codecsep_fixed_category(
        self,
        audio: np.ndarray,
        sample_rate: int,
        per_category_targets: list[tuple[str, list]],
        *,
        suppress_categories: Sequence[str],
        codecsep_checkpoint_path: Optional[Union[str, Path]] = None,
        codecsep_device: Optional[str] = None,
        codecsep_product_categories: Sequence[str] | None = None,
        codecsep_hive_class_ids: Sequence[Union[int, str]] | None = None,
        codecsep_fixed_merge_policy: str = "wiener_mask",
        aggressiveness: float,
        explicit_prompt_overrides: Optional[Dict[str, Sequence[str]]] = None,
    ) -> np.ndarray:
        if not self._codecsep_fixed_catalog.available:
            logger.warning(
                "Fixed-category runtime artifacts are missing; falling back to compat mode until product_to_hive_fixedset.json and the identity catalog are available."
            )
            compat_targets = [
                (category, self._get_codecsep_stems(category))
                for category in suppress_categories
                if self._get_codecsep_stems(category)
            ]
            if compat_targets:
                return self._suppress_codecsep_compat(
                    audio,
                    sample_rate,
                    compat_targets,
                    {},
                    aggressiveness=aggressiveness,
                    codecsep_checkpoint_path=codecsep_checkpoint_path,
                    codecsep_device=codecsep_device,
                    explicit_prompt_overrides=explicit_prompt_overrides,
                )
            if codecsep_hive_class_ids or codecsep_product_categories:
                raise FileNotFoundError(
                    "Fixed-category runtime artifacts are missing. "
                    "Build product_to_hive_fixedset.json and the identity catalog before using explicit fixed-category ids."
                )
            return np.array(audio, copy=True)

        if not suppress_categories and not codecsep_product_categories and not codecsep_hive_class_ids:
            return np.array(audio, copy=True)

        resolution = self._resolve_codecsep_fixed_request(
            suppress_categories=suppress_categories,
            codecsep_product_categories=codecsep_product_categories,
            codecsep_hive_class_ids=codecsep_hive_class_ids,
        )
        if resolution["unresolved"]:
            logger.warning(
                "CodecSep fixed-category runtime could not resolve categories=%s",
                resolution["unresolved"],
            )
        class_ids = [int(value) for value in resolution["class_ids"]]
        if not class_ids:
            logger.warning(
                "CodecSep fixed-category runtime found no class ids for suppress_categories=%s product_categories=%s explicit_ids=%s",
                list(suppress_categories),
                list(codecsep_product_categories or []),
                list(codecsep_hive_class_ids or []),
            )
            return np.array(audio, copy=True)

        separator = self._get_codecsep_separator(
            checkpoint_path=codecsep_checkpoint_path,
            device=codecsep_device,
        )
        if not getattr(separator, "supports_fixed_category", lambda: False)():
            logger.warning(
                "CodecSep fixed_category mode requested but the loaded checkpoint is prompt-conditioned; falling back to compat mode.",
            )
            compat_targets = [
                (category, self._get_codecsep_stems(category))
                for category in suppress_categories
                if self._get_codecsep_stems(category)
            ]
            if not compat_targets:
                logger.warning(
                    "CodecSep fixed_category fallback had no legacy compat mappings for suppress_categories=%s",
                    list(suppress_categories),
                )
                return np.array(audio, copy=True)
            return self._suppress_codecsep_compat(
                audio,
                sample_rate,
                compat_targets,
                {},
                aggressiveness=aggressiveness,
                codecsep_checkpoint_path=codecsep_checkpoint_path,
                codecsep_device=codecsep_device,
                explicit_prompt_overrides=explicit_prompt_overrides,
            )

        logger.info(
            "CodecSep fixed-category routing: categories=%s product_categories=%s class_ids=%s labels=%s",
            list(suppress_categories),
            resolution["product_categories"],
            class_ids,
            resolution["labels"],
        )
        bundle = separator.separate_class_id_bundle(
            audio=audio,
            sample_rate=sample_rate,
            class_ids=class_ids,
            merge_policy=str(codecsep_fixed_merge_policy or "wiener_mask"),
            aggressiveness=aggressiveness,
        )
        removed_audio = np.asarray(bundle["merged_target"], dtype=np.float32)
        clean_audio = np.asarray(bundle["clean_audio"], dtype=np.float32)
        self._last_codecsep_removed_audio = removed_audio.astype(np.asarray(audio).dtype, copy=False)
        return clean_audio.astype(np.asarray(audio).dtype, copy=False)

    def _suppress_codecsep_query_first(
        self,
        audio: np.ndarray,
        sample_rate: int,
        per_category_targets: list[tuple[str, list]],
        smoothed_scores: Dict[str, float],
        *,
        suppress_categories: Sequence[str],
        universal_prompts: Sequence[str],
        aggressiveness: float,
        codecsep_checkpoint_path: Optional[Union[str, Path]] = None,
        codecsep_device: Optional[str] = None,
        explicit_prompt_overrides: Optional[Dict[str, Sequence[str]]] = None,
        negative_prompts: Optional[Sequence[str]] = None,
        preserve_prompts: Optional[Sequence[str]] = None,
        mode: str = "auto",
        query_strategy: str = "single_pass",
        multistep_steps: int = 0,
    ) -> np.ndarray:
        if mode == "compat":
            return self._suppress_codecsep_compat(
                audio,
                sample_rate,
                per_category_targets,
                smoothed_scores,
                aggressiveness=aggressiveness,
                codecsep_checkpoint_path=codecsep_checkpoint_path,
                codecsep_device=codecsep_device,
                explicit_prompt_overrides=explicit_prompt_overrides,
            )

        if mode == "audiocaps_native":
            if preserve_prompts:
                logger.info(
                    "CodecSep AudioCaps-native mode ignores codecsep_preserve_prompts; clean audio is rebuilt from normalized complement stems."
                )
            if query_strategy != "single_pass":
                logger.info(
                    "CodecSep AudioCaps-native mode ignores codecsep_query_strategy=%s and uses fixed-slot single-pass inference.",
                    query_strategy,
                )
            if multistep_steps > 0:
                logger.info(
                    "CodecSep AudioCaps-native mode ignores codecsep_multistep_steps=%s.",
                    multistep_steps,
                )
            plans = self._compile_codecsep_native_plans(
                suppress_categories=suppress_categories,
                per_category_targets=per_category_targets,
                explicit_prompt_overrides=explicit_prompt_overrides,
                universal_prompts=universal_prompts,
                aggressiveness=aggressiveness,
                mode=mode,
            )
        else:
            logger.info(
                "CodecSep experimental-search mode enabled: slot search / CLAP rescoring / multistep refinement remain active."
            )
            plans = self._compile_codecsep_experimental_plans(
                suppress_categories=suppress_categories,
                per_category_targets=per_category_targets,
                explicit_prompt_overrides=explicit_prompt_overrides,
                universal_prompts=universal_prompts,
                negative_prompts=negative_prompts,
                preserve_prompts=preserve_prompts,
                aggressiveness=aggressiveness,
                mode=mode,
                query_strategy=query_strategy,
                multistep_steps=multistep_steps,
            )
        if not plans:
            return np.array(audio, copy=True)

        separator = self._get_codecsep_separator(
            checkpoint_path=codecsep_checkpoint_path,
            device=codecsep_device,
        )
        if not hasattr(separator, "query"):
            logger.warning("CodecSep separator does not support native/experimental query mode; falling back to compat mode.")
            return self._suppress_codecsep_compat(
                audio,
                sample_rate,
                per_category_targets,
                smoothed_scores,
                aggressiveness=aggressiveness,
                codecsep_checkpoint_path=codecsep_checkpoint_path,
                codecsep_device=codecsep_device,
                explicit_prompt_overrides=explicit_prompt_overrides,
            )

        clean_audio = np.asarray(audio, dtype=np.float32).copy()
        removed_audio = np.zeros_like(clean_audio, dtype=np.float32)
        for plan in plans:
            cached_slot = None
            effective_plan = plan
            if mode == "experimental_search":
                cached_slot = self._codecsep_query_cache.get(plan.cache_key())
                effective_plan = replace(plan, query_strategy="single_pass") if cached_slot else plan
            result = separator.query(
                clean_audio,
                sample_rate,
                effective_plan,
                selected_slot_hint=cached_slot,
            )
            if mode == "experimental_search":
                self._codecsep_query_cache[plan.cache_key()] = str(result.selected_slot)
            result_target = np.asarray(result.target_audio, dtype=np.float32)
            min_samples = min(len(removed_audio), len(result_target))
            removed_audio[:min_samples] += result_target[:min_samples]
            clean_audio = np.asarray(result.clean_audio, dtype=np.float32)
        self._last_codecsep_removed_audio = removed_audio.astype(np.asarray(audio).dtype, copy=False)
        return clean_audio.astype(np.asarray(audio).dtype, copy=False)

    def _suppress_codecsep_compat(
        self,
        audio: np.ndarray,
        sample_rate: int,
        per_category_targets: list[tuple[str, list]],
        smoothed_scores: Dict[str, float],
        *,
        aggressiveness: float,
        codecsep_checkpoint_path: Optional[Union[str, Path]] = None,
        codecsep_device: Optional[str] = None,
        explicit_prompt_overrides: Optional[Dict[str, Sequence[str]]] = None,
    ) -> np.ndarray:
        if profiler:
            profiler.start("codecsep_separation")
        unique_stems: list[str] = []
        for _, targets in per_category_targets:
            for stem in targets:
                if stem not in unique_stems:
                    unique_stems.append(stem)

        if not unique_stems:
            return np.array(audio, copy=True)

        effective_aggressiveness = self._effective_category_aggressiveness(
            per_category_targets,
            aggressiveness,
        )
        prompt_overrides = self._build_codecsep_prompt_overrides(
            per_category_targets=per_category_targets,
            smoothed_scores=smoothed_scores,
            explicit_prompt_overrides=explicit_prompt_overrides,
        )
        category_names = [category for category, _ in per_category_targets]
        logger.info(
            "CodecSep semantic routing: categories=%s -> stems=%s prompts=%s effective_aggressiveness=%.2f",
            category_names,
            unique_stems,
            prompt_overrides,
            effective_aggressiveness,
        )
        separator = self._get_codecsep_separator(
            checkpoint_path=codecsep_checkpoint_path,
            device=codecsep_device,
        )
        all_stems = list(getattr(separator, "STEMS", ("speech", "music", "sfx")))
        if hasattr(separator, "separate_stem_bundle"):
            stem_bundle = separator.separate_stem_bundle(
                audio=audio,
                sample_rate=sample_rate,
                stems=all_stems,
                prompt_overrides=prompt_overrides,
            )
            raw_outputs = stem_bundle.get("raw", {})
            normalized_outputs = stem_bundle.get("normalized", {})
        else:
            normalized_outputs = separator.separate_stems(
                audio=audio,
                sample_rate=sample_rate,
                stems=all_stems,
                prompt_overrides=prompt_overrides,
            )
            raw_outputs = normalized_outputs

        if "sfx" in unique_stems:
            norm_unwanted_tracks = [
                np.asarray(normalized_outputs[stem], dtype=np.float32)
                for stem in unique_stems
                if stem in normalized_outputs
            ]
            normalized_unwanted = np.asarray(
                self._sum_audio_tracks(norm_unwanted_tracks, audio),
                dtype=np.float32,
            )
            self._last_codecsep_removed_audio = normalized_unwanted.astype(
                np.asarray(audio).dtype,
                copy=False,
            )
            effective_aggressiveness = max(1.0, effective_aggressiveness)
            clean_audio = (
                np.asarray(audio, dtype=np.float32)
                - effective_aggressiveness * normalized_unwanted
            )
            logger.info(
                "CodecSep semantic suppression keeps speech/music and removes routed unwanted content via normalized residual reconstruction: suppressing_stems=%s aggressiveness=%.2f",
                unique_stems,
                effective_aggressiveness,
            )
            if profiler:
                profiler.end("codecsep_separation")
            return clean_audio.astype(np.asarray(audio).dtype, copy=False)

        wanted_stems = [stem for stem in all_stems if stem not in unique_stems]
        wanted_tracks = [
            normalized_outputs[stem] for stem in wanted_stems if stem in normalized_outputs
        ]
        removed_tracks = [
            np.asarray(normalized_outputs[stem], dtype=np.float32)
            for stem in unique_stems
            if stem in normalized_outputs
        ]
        self._last_codecsep_removed_audio = self._sum_audio_tracks(
            removed_tracks,
            audio,
        ).astype(np.asarray(audio).dtype, copy=False)
        clean_audio = self._sum_audio_tracks(wanted_tracks, audio)
        logger.info(
            "CodecSep using paper-faithful normalized stem reconstruction: keeping=%s suppressing=%s",
            wanted_stems,
            unique_stems,
        )

        if profiler:
            profiler.end("codecsep_separation")
        return clean_audio

    def _separate_universal(
        self,
        audio: np.ndarray,
        sample_rate: int,
        universal_prompts: Sequence[str],
    ) -> tuple[np.ndarray, float]:
        if profiler:
            profiler.start("universal_separation")
        unwanted_audio = self.universal_separator.separate(
            audio=audio, sample_rate=sample_rate,
            prompts=list(universal_prompts),
        )
        if profiler:
            profiler.end("universal_separation")
        min_len = min(audio.shape[0], unwanted_audio.shape[0])
        mix_rms = np.sqrt(np.mean(audio[:min_len] ** 2)) + 1e-8
        unwanted_rms = np.sqrt(np.mean(unwanted_audio[:min_len] ** 2)) + 1e-8
        return unwanted_audio, unwanted_rms / mix_rms

    # ------------------------------------------------------------------
    # Config loaders
    # ------------------------------------------------------------------

    def _get_codecsep_stems(self, category: str) -> list[str]:
        if self._codecsep_stem_map and category in self._codecsep_stem_map:
            return self._codecsep_stem_map[category]
        return []

    def _get_codecsep_fixed_targets(self, category: str) -> list[int]:
        if not self._codecsep_fixed_catalog.available:
            return []
        resolution = self._codecsep_fixed_catalog.resolve_targets(
            legacy_categories=[category],
        )
        return [int(value) for value in resolution["class_ids"]]

    def _get_codecsep_prompt_values(self, category: str) -> list[str]:
        if self._codecsep_prompt_map and category in self._codecsep_prompt_map:
            return normalize_codecsep_prompt_value(self._codecsep_prompt_map[category])
        return []

    def _build_codecsep_prompt_overrides(
        self,
        per_category_targets: list[tuple[str, list]],
        smoothed_scores: Dict[str, float],
        explicit_prompt_overrides: Optional[Dict[str, Sequence[str]]] = None,
    ) -> Dict[str, list[str]]:
        prompt_groups: dict[str, list[tuple[float, list[str]]]] = defaultdict(list)
        for category, targets in per_category_targets:
            prompt_values = self._get_codecsep_prompt_values(category)
            if not prompt_values:
                continue
            confidence = smoothed_scores.get(category, 0.9)
            for stem in targets:
                prompt_groups[stem].append((confidence, prompt_values))

        prompt_overrides: Dict[str, list[str]] = {}
        for stem, entries in prompt_groups.items():
            ordered_values: list[str] = []
            for _, prompt_values in sorted(entries, key=lambda item: item[0], reverse=True):
                ordered_values.extend(prompt_values)
            runtime_prompt = collapse_codecsep_prompt_value(ordered_values)
            if runtime_prompt:
                prompt_overrides[stem] = runtime_prompt
        for stem, prompt_values in normalize_codecsep_prompt_map(explicit_prompt_overrides).items():
            runtime_prompt = collapse_codecsep_prompt_value(prompt_values)
            if runtime_prompt:
                prompt_overrides[stem] = runtime_prompt
        return prompt_overrides

    @staticmethod
    def _load_codecsep_mapping() -> Dict[str, dict]:
        path = CODECSEP_MAPPING_PATH
        if not path.exists():
            logger.warning("CodecSep mapping not found at %s", path)
            return {"stems": {}, "prompts": {}, "queries": {}}
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        stems = data.get("stems", {})
        prompts = data.get("prompts", {})
        queries = data.get("queries", {})
        logger.info(
            "Loaded %d CodecSep stem mappings, %d prompt mappings, and %d query profiles from %s",
            len(stems),
            len(prompts),
            len(queries),
            path,
        )
        return {"stems": stems, "prompts": prompts, "queries": queries}

    @staticmethod
    def _load_mapping(path: Path) -> Dict[str, dict]:
        if not path.exists():
            raise FileNotFoundError(f"Mapping file not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        categories = data.get("categories", {})
        logger.info("Loaded %d category mappings from %s", len(categories), path)
        return categories


__all__ = ["SemanticSuppressor"]
