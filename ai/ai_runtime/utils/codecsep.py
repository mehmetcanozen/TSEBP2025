"""Shared CodecSep runtime helpers."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


CODECSEP_STEMS: tuple[str, ...] = ("speech", "music", "sfx")


def _normalize_fixed_category_key(value: str | int | None) -> str:
    if value is None:
        return ""
    return str(value).strip().casefold()


@dataclass(frozen=True)
class FixedCategoryRuntimeEntry:
    class_id: int
    slug: str
    hive_label: str
    display_name: str
    product_category: str
    aliases: tuple[str, ...]


class FixedCategoryRuntimeCatalog:
    """Runtime view over fixed-category identity, mapping, and threshold artifacts."""

    def __init__(
        self,
        *,
        identity_payload: Mapping[str, Any] | None = None,
        mapping_payload: Mapping[str, Any] | None = None,
        threshold_payload: Mapping[str, Any] | None = None,
    ) -> None:
        self.identity_payload = dict(identity_payload or {})
        self.mapping_payload = dict(mapping_payload or {})
        self.threshold_payload = dict(threshold_payload or {})
        self.threshold_version = str(self.threshold_payload.get("version", ""))
        if self.threshold_payload and self.threshold_version.strip() != "gate_thresholds_v2":
            raise ValueError(
                "Fixed-category threshold artifact must declare version 'gate_thresholds_v2' "
                f"(got {self.threshold_version!r})."
            )

        self.version = str(self.identity_payload.get("version", ""))
        self.num_classes = int(self.identity_payload.get("num_classes", 0) or 0)
        self.null_id = int(self.identity_payload.get("null_id", self.num_classes))
        self.global_default_threshold = float(
            self.threshold_payload.get("global_default_threshold", 0.5),
        )
        self._thresholds_by_slug = {
            _normalize_fixed_category_key(key): float(value)
            for key, value in dict(self.threshold_payload.get("thresholds") or {}).items()
        }

        entries_by_id: dict[int, FixedCategoryRuntimeEntry] = {}
        entry_lookup: dict[str, int] = {}
        for raw_entry in list(self.identity_payload.get("entries") or []):
            entry = FixedCategoryRuntimeEntry(
                class_id=int(raw_entry["class_id"]),
                slug=str(raw_entry.get("slug", raw_entry.get("hive_label", ""))),
                hive_label=str(raw_entry.get("hive_label", raw_entry.get("display_name", ""))),
                display_name=str(raw_entry.get("display_name", raw_entry.get("hive_label", ""))),
                product_category=str(raw_entry.get("product_category", "other_unmapped")),
                aliases=tuple(str(item) for item in raw_entry.get("aliases", []) or []),
            )
            entries_by_id[entry.class_id] = entry
            for token in (entry.slug, entry.hive_label, entry.display_name, *entry.aliases):
                key = _normalize_fixed_category_key(token)
                if key and key not in entry_lookup:
                    entry_lookup[key] = entry.class_id
        self.entries_by_id = entries_by_id
        self.entry_lookup = entry_lookup

        products_by_name: dict[str, dict[str, Any]] = {}
        legacy_to_products: dict[str, list[str]] = {}
        for raw_product in list(self.mapping_payload.get("product_categories") or []):
            product_name = str(raw_product.get("product_category", "")).strip()
            if not product_name:
                continue
            normalized_name = _normalize_fixed_category_key(product_name)
            product_payload = {
                "product_category": product_name,
                "member_class_ids": [int(value) for value in raw_product.get("member_class_ids", []) or []],
                "member_slugs": [str(value) for value in raw_product.get("member_slugs", []) or []],
                "priority_class_ids": [int(value) for value in raw_product.get("priority_class_ids", []) or []],
                "legacy_runtime_categories": [
                    str(value) for value in raw_product.get("legacy_runtime_categories", []) or []
                ],
            }
            products_by_name[normalized_name] = product_payload
            for legacy_name in product_payload["legacy_runtime_categories"]:
                legacy_key = _normalize_fixed_category_key(legacy_name)
                if not legacy_key:
                    continue
                legacy_to_products.setdefault(legacy_key, [])
                if product_name not in legacy_to_products[legacy_key]:
                    legacy_to_products[legacy_key].append(product_name)
        for legacy_name, product_categories in dict(self.mapping_payload.get("legacy_category_aliases") or {}).items():
            legacy_key = _normalize_fixed_category_key(legacy_name)
            if not legacy_key:
                continue
            legacy_to_products.setdefault(legacy_key, [])
            for product_name in list(product_categories or []):
                normalized_product = _normalize_fixed_category_key(product_name)
                product_payload = products_by_name.get(normalized_product)
                if product_payload is None:
                    continue
                canonical_name = str(product_payload["product_category"])
                if canonical_name not in legacy_to_products[legacy_key]:
                    legacy_to_products[legacy_key].append(canonical_name)
        self.products_by_name = products_by_name
        self.legacy_to_products = legacy_to_products

    @classmethod
    def load(
        cls,
        *,
        identity_path: str | Path | None = None,
        mapping_path: str | Path | None = None,
        threshold_path: str | Path | None = None,
    ) -> "FixedCategoryRuntimeCatalog":
        return cls(
            identity_payload=_load_json_payload(identity_path),
            mapping_payload=_load_json_payload(mapping_path),
            threshold_payload=_load_json_payload(threshold_path),
        )

    @property
    def available(self) -> bool:
        return bool(self.entries_by_id or self.products_by_name)

    def describe_class_ids(self, class_ids: Sequence[int]) -> list[str]:
        labels: list[str] = []
        for class_id in class_ids:
            entry = self.entries_by_id.get(int(class_id))
            if entry is None:
                labels.append(str(class_id))
            else:
                labels.append(entry.slug or entry.hive_label or str(class_id))
        return labels

    def threshold_for_class_id(self, class_id: int) -> float:
        entry = self.entries_by_id.get(int(class_id))
        if entry is None:
            return self.global_default_threshold
        return float(
            self._thresholds_by_slug.get(
                _normalize_fixed_category_key(entry.slug),
                self.global_default_threshold,
            )
        )

    def resolve_targets(
        self,
        *,
        class_ids: Sequence[int | str] | None = None,
        product_categories: Sequence[str] | None = None,
        legacy_categories: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        resolved_class_ids: list[int] = []
        resolved_products: list[str] = []
        unresolved: list[str] = []
        seen_class_ids: set[int] = set()

        def add_class_id(class_id: int) -> None:
            normalized_id = int(class_id)
            if normalized_id in seen_class_ids:
                return
            seen_class_ids.add(normalized_id)
            resolved_class_ids.append(normalized_id)

        def add_product(product_name: str) -> bool:
            product_key = _normalize_fixed_category_key(product_name)
            product_payload = self.products_by_name.get(product_key)
            if product_payload is None:
                return False
            canonical_name = str(product_payload["product_category"])
            if canonical_name not in resolved_products:
                resolved_products.append(canonical_name)
            for class_id in product_payload["member_class_ids"]:
                add_class_id(class_id)
            return True

        for raw_value in list(class_ids or []):
            if raw_value is None:
                continue
            if isinstance(raw_value, int):
                add_class_id(raw_value)
                continue
            text_value = str(raw_value).strip()
            if not text_value:
                continue
            if text_value.isdigit():
                add_class_id(int(text_value))
                continue
            entry_match = self.entry_lookup.get(_normalize_fixed_category_key(text_value))
            if entry_match is not None:
                add_class_id(entry_match)
                continue
            if not add_product(text_value):
                unresolved.append(text_value)

        for product_name in list(product_categories or []):
            if product_name is None:
                continue
            text_value = str(product_name).strip()
            if not text_value:
                continue
            if not add_product(text_value):
                entry_match = self.entry_lookup.get(_normalize_fixed_category_key(text_value))
                if entry_match is not None:
                    add_class_id(entry_match)
                else:
                    unresolved.append(text_value)

        for legacy_name in list(legacy_categories or []):
            if legacy_name is None:
                continue
            text_value = str(legacy_name).strip()
            if not text_value:
                continue
            legacy_key = _normalize_fixed_category_key(text_value)
            matched_products = self.legacy_to_products.get(legacy_key, [])
            if matched_products:
                for product_name in matched_products:
                    add_product(product_name)
                continue
            if add_product(text_value):
                continue
            entry_match = self.entry_lookup.get(legacy_key)
            if entry_match is not None:
                add_class_id(entry_match)
            else:
                unresolved.append(text_value)

        return {
            "class_ids": resolved_class_ids,
            "product_categories": resolved_products,
            "labels": self.describe_class_ids(resolved_class_ids),
            "unresolved": unresolved,
        }


def _load_json_payload(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        return {}
    return dict(json.loads(candidate.read_text(encoding="utf-8")))


def normalize_codecsep_prompt_value(
    value: str | Sequence[str] | None,
) -> list[str]:
    """Normalize a single stem prompt value to a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    else:
        values = list(value)
    return [str(item).strip() for item in values if str(item).strip()]


def normalize_codecsep_prompt_map(
    prompts: Mapping[str, str | Sequence[str]] | None,
) -> dict[str, list[str]]:
    """Normalize a stem -> prompt mapping."""
    normalized: dict[str, list[str]] = {}
    if not prompts:
        return normalized
    for stem, value in prompts.items():
        prompt_list = normalize_codecsep_prompt_value(value)
        if prompt_list:
            normalized[stem] = prompt_list
    return normalized


def flatten_codecsep_prompt_segments(
    value: str | Sequence[str] | None,
) -> list[str]:
    """Split prompt text into deterministic comma-delimited segments."""
    segments: list[str] = []
    for prompt in normalize_codecsep_prompt_value(value):
        for segment in prompt.split(","):
            cleaned = segment.strip()
            if cleaned:
                segments.append(cleaned)
    return segments


def collapse_codecsep_prompt_value(
    value: str | Sequence[str] | None,
    *,
    max_segments: int = 6,
) -> list[str]:
    """Collapse one or many prompt strings into a single runtime prompt."""
    segments = flatten_codecsep_prompt_segments(value)
    if not segments:
        return []

    deduped: list[str] = []
    seen: set[str] = set()
    for segment in segments:
        key = segment.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(segment)
        if len(deduped) >= max_segments:
            break

    if not deduped:
        return []
    return [", ".join(deduped)]


def build_codecsep_prompt_overrides(
    *,
    speech_prompts: str | Sequence[str] | None = None,
    music_prompts: str | Sequence[str] | None = None,
    sfx_prompts: str | Sequence[str] | None = None,
    existing: Mapping[str, str | Sequence[str]] | None = None,
) -> dict[str, list[str]]:
    """Build a normalized CodecSep prompt override map."""
    overrides = normalize_codecsep_prompt_map(existing)
    for stem, prompts in {
        "speech": speech_prompts,
        "music": music_prompts,
        "sfx": sfx_prompts,
    }.items():
        prompt_list = normalize_codecsep_prompt_value(prompts)
        if prompt_list:
            overrides[stem] = prompt_list
    return overrides


def add_codecsep_runtime_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_backend: bool = True,
    include_masking: bool = True,
    default_mode: str = "fixed_category",
    default_query_strategy: str = "single_pass",
    default_multistep_steps: int = 0,
) -> argparse.ArgumentParser:
    """Add common runtime separator arguments to a parser."""
    if include_backend:
        parser.add_argument(
            "--separator-backend",
            type=str,
            choices=["waveformer", "codecsep", "audiosep_hive15cat"],
            default="waveformer",
            help=(
                "Separation model: waveformer (default), codecsep, or audiosep_hive15cat. "
                "CodecSep defaults to the active AudioCaps run directory under ai/models/CodecSep/. "
                "AudioSepHive15Cat defaults to ai/models/AudioSepHive15Cat/frozensep_hive_15cat.onnx."
            ),
        )
    if include_masking:
        parser.add_argument(
            "--masking-method",
            type=str,
            choices=["wiener_dd", "cirm"],
            default="wiener_dd",
            help=(
                "Spectral masking for Waveformer and AudioSepHive15Cat: wiener_dd or cirm. "
                "Ignored by CodecSep."
            ),
        )
    parser.add_argument(
        "--audiosep15-model",
        type=str,
        default=None,
        help=(
            "AudioSepHive15Cat ONNX file or model directory override. "
            "Defaults to ai/models/AudioSepHive15Cat/frozensep_hive_15cat.onnx."
        ),
    )
    parser.add_argument(
        "--audiosep15-device",
        type=str,
        default=None,
        help="Optional AudioSepHive15Cat execution hint, e.g. cpu or cuda.",
    )
    parser.add_argument(
        "--audiosep15-realtime-hop",
        type=float,
        default=1.0,
        help="Buffered live inference hop in seconds for AudioSepHive15Cat realtime mode.",
    )
    parser.add_argument(
        "--codecsep-checkpoint",
        type=str,
        default=None,
        help=(
            "CodecSep run directory or checkpoint file override. "
            "Defaults to ai/models/CodecSep/.../CodecSep_Hive_V5_50K_Pilot_Run1. "
            "The runtime resolves V5 checkpoint families such as ckpt_gate_pass and ckpt_best_screen automatically."
        ),
    )
    parser.add_argument(
        "--codecsep-device",
        type=str,
        default=None,
        help="Optional CodecSep device override, e.g. cpu, cuda, or cuda:0.",
    )
    parser.add_argument(
        "--codecsep-speech-prompt",
        action="append",
        default=None,
        help="Repeatable explicit prompt override for CodecSep speech stem.",
    )
    parser.add_argument(
        "--codecsep-music-prompt",
        action="append",
        default=None,
        help="Repeatable explicit prompt override for CodecSep music stem.",
    )
    parser.add_argument(
        "--codecsep-sfx-prompt",
        action="append",
        default=None,
        help="Repeatable explicit prompt override for CodecSep sfx stem.",
    )
    parser.add_argument(
        "--codecsep-mode",
        type=str,
        choices=["fixed_category", "compat", "audiocaps_native", "experimental_search", "auto", "query_first"],
        default=default_mode,
        help=(
            "CodecSep runtime mode: fixed_category (default class-id path), "
            "compat (legacy stem routing), audiocaps_native (legacy fixed-slot prompt path), "
            "experimental_search (legacy slot-search path), or auto."
        ),
    )
    parser.add_argument(
        "--codecsep-product-category",
        action="append",
        default=None,
        help="Repeatable fixed-category product category override for CodecSep runtime.",
    )
    parser.add_argument(
        "--codecsep-hive-class-id",
        action="append",
        default=None,
        help="Repeatable fixed-category Hive class id override for CodecSep runtime.",
    )
    parser.add_argument(
        "--codecsep-query-strategy",
        type=str,
        choices=["single_pass", "slot_search"],
        default=default_query_strategy,
        help="Experimental-search strategy only. Ignored by fixed_category and audiocaps_native modes.",
    )
    parser.add_argument(
        "--codecsep-multistep-steps",
        type=int,
        default=default_multistep_steps,
        help="Experimental-search refinement iterations. Ignored by fixed_category and audiocaps_native modes.",
    )
    parser.add_argument(
        "--codecsep-stereo-mode",
        type=str,
        choices=["mono_shared", "per_channel"],
        default="mono_shared",
        help=(
            "Batch-only stereo handling for CodecSep: mono_shared (default, faster) or "
                "per_channel (slower, higher-cost debug path)."
        ),
    )
    parser.add_argument(
        "--codecsep-fixed-merge-policy",
        type=str,
        choices=["wiener_mask", "sum"],
        default="wiener_mask",
        help=(
            "Fixed-category clean-audio reconstruction policy: "
            "wiener_mask (safer, softer) or sum (louder direct subtraction)."
        ),
    )
    parser.add_argument(
        "--codecsep-negative-prompt",
        action="append",
        default=None,
        help="Experimental-search only. Ignored by fixed_category and audiocaps_native modes.",
    )
    parser.add_argument(
        "--codecsep-preserve-prompt",
        action="append",
        default=None,
        help="Experimental-search only. Ignored by fixed_category and audiocaps_native modes.",
    )
    return parser


def build_suppressor_kwargs_from_args(args: Any) -> dict[str, Any]:
    """Extract SemanticSuppressor construction kwargs from parsed CLI args."""
    return {
        "separator_backend": getattr(args, "separator_backend", "waveformer"),
        "masking_method": getattr(args, "masking_method", "wiener_dd"),
        "audiosep_hive15cat_model_path": getattr(args, "audiosep15_model", None),
        "audiosep_hive15cat_device": getattr(args, "audiosep15_device", None),
        "codecsep_checkpoint_path": getattr(args, "codecsep_checkpoint", None),
        "codecsep_device": getattr(args, "codecsep_device", None),
    }


def build_codecsep_prompt_overrides_from_args(args: Any) -> dict[str, list[str]]:
    """Extract explicit per-call CodecSep prompt overrides from parsed CLI args."""
    return build_codecsep_prompt_overrides(
        speech_prompts=getattr(args, "codecsep_speech_prompt", None),
        music_prompts=getattr(args, "codecsep_music_prompt", None),
        sfx_prompts=getattr(args, "codecsep_sfx_prompt", None),
    )


def build_codecsep_call_kwargs_from_args(args: Any) -> dict[str, Any]:
    """Extract per-call separator controls from parsed CLI args."""
    return {
        "audiosep_hive15cat_model_path": getattr(args, "audiosep15_model", None),
        "audiosep_hive15cat_device": getattr(args, "audiosep15_device", None),
        "audiosep_hive15cat_realtime_hop_seconds": float(
            getattr(args, "audiosep15_realtime_hop", 1.0) or 1.0
        ),
        "codecsep_prompt_overrides": build_codecsep_prompt_overrides_from_args(args),
        "codecsep_negative_prompts": normalize_codecsep_prompt_value(
            getattr(args, "codecsep_negative_prompt", None),
        ),
        "codecsep_preserve_prompts": normalize_codecsep_prompt_value(
            getattr(args, "codecsep_preserve_prompt", None),
        ),
        "codecsep_mode": getattr(args, "codecsep_mode", "fixed_category"),
        "codecsep_query_strategy": getattr(args, "codecsep_query_strategy", "single_pass"),
        "codecsep_multistep_steps": int(getattr(args, "codecsep_multistep_steps", 0) or 0),
        "codecsep_stereo_mode": getattr(args, "codecsep_stereo_mode", "mono_shared"),
        "codecsep_fixed_merge_policy": getattr(args, "codecsep_fixed_merge_policy", "wiener_mask"),
        "codecsep_product_categories": [
            str(value) for value in list(getattr(args, "codecsep_product_category", None) or []) if str(value).strip()
        ],
        "codecsep_hive_class_ids": [
            str(value) for value in list(getattr(args, "codecsep_hive_class_id", None) or []) if str(value).strip()
        ],
    }
