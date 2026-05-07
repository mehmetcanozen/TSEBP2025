"""Evaluation case loading and target inference."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ai.ai_runtime.utils.paths import get_data_audio_path
from ai.evaluation.contracts import EvalCase


AUDIO_EXTENSIONS = {".wav", ".flac", ".ogg", ".aiff", ".aif"}
DEFAULT_CASES_PATH = Path(__file__).with_name("eval_cases.yaml")


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.strip().lower()).strip("_")


def _infer_targets(path: Path) -> dict[str, str]:
    name = path.stem.casefold()
    if "keyboard" in name or "typing" in name:
        return {
            "waveformer20": "computer_typing",
            "exact15": "keyboard typing",
            "legacy": "typing",
            "audiosep_prompt": "keyboard typing",
        }
    if "bark" in name or "dog" in name:
        return {
            "waveformer20": "dog",
            "exact15": "dog barking",
            "legacy": "pets",
            "audiosep_prompt": "dog barking",
        }
    if "siren" in name or "alarm" in name:
        return {
            "waveformer20": "siren",
            "exact15": "alarm",
            "legacy": "alarm",
            "audiosep_prompt": "siren alarm",
        }
    if "boat" in name or "engine" in name or "car" in name:
        return {
            "waveformer20": "car_horn",
            "exact15": "car engine",
            "legacy": "traffic",
            "audiosep_prompt": "boat engine, water noise",
        }
    if "music" in name:
        return {
            "waveformer20": "music",
            "exact15": "music",
            "legacy": "music",
            "audiosep_prompt": "music",
        }
    if "speech" in name:
        return {
            "waveformer20": "speech",
            "exact15": "speech",
            "legacy": "speech",
            "audiosep_prompt": "speech",
        }
    return {
        "waveformer20": "dog",
        "exact15": "background noise",
        "legacy": "misc",
        "audiosep_prompt": "background noise",
    }


def _resolve_audio_path(input_dir: Path, value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(value)
    return path if path.is_absolute() else input_dir / path


def _case_from_payload(input_dir: Path, payload: dict[str, Any]) -> EvalCase:
    input_path = _resolve_audio_path(input_dir, payload["input"])
    if input_path is None:
        raise ValueError(f"Evaluation case {payload.get('id', '<unknown>')} has no input")
    return EvalCase(
        case_id=str(payload.get("id") or _slug(input_path.stem)),
        tier="reference",
        input_path=input_path,
        clean_reference_path=_resolve_audio_path(input_dir, payload.get("clean_reference")),
        unwanted_reference_path=_resolve_audio_path(input_dir, payload.get("unwanted_reference")),
        targets={str(key): str(value) for key, value in (payload.get("targets") or {}).items()},
        tags=tuple(str(item) for item in payload.get("tags", [])),
        notes=str(payload.get("notes") or ""),
        primary_ranking=bool(payload.get("primary_ranking", True)),
        speech_reference=bool(payload.get("speech_reference", False)),
    )


def load_reference_cases(
    *,
    input_dir: Path | None = None,
    cases_path: Path | None = None,
) -> list[EvalCase]:
    """Load curated reference-backed cases."""

    resolved_input_dir = input_dir or get_data_audio_path("raw")
    resolved_cases_path = cases_path or DEFAULT_CASES_PATH
    payload = yaml.safe_load(resolved_cases_path.read_text(encoding="utf-8")) or {}
    return [
        _case_from_payload(resolved_input_dir, item)
        for item in payload.get("reference", [])
    ]


def build_coverage_cases(
    *,
    input_dir: Path | None = None,
) -> list[EvalCase]:
    """Generate coverage cases from every raw input audio file."""

    resolved_input_dir = input_dir or get_data_audio_path("raw")
    files = [
        path
        for path in sorted(resolved_input_dir.iterdir())
        if path.is_file() and path.suffix.casefold() in AUDIO_EXTENSIONS
    ]
    return [
        EvalCase(
            case_id=f"coverage_{_slug(path.stem)}",
            tier="coverage",
            input_path=path,
            targets=_infer_targets(path),
            tags=("coverage",),
            primary_ranking=False,
            speech_reference="speech" in path.stem.casefold(),
        )
        for path in files
    ]


def build_evaluation_cases(
    *,
    input_dir: Path | None = None,
    cases_path: Path | None = None,
    suite: str = "full",
    max_cases: int | None = None,
) -> list[EvalCase]:
    """Build the ordered case list for an evaluation suite."""

    suite_name = str(suite or "full").strip().casefold()
    cases: list[EvalCase] = []
    if suite_name in {"full", "reference"}:
        cases.extend(load_reference_cases(input_dir=input_dir, cases_path=cases_path))
    if suite_name in {"full", "coverage"}:
        cases.extend(build_coverage_cases(input_dir=input_dir))
    if suite_name not in {"full", "reference", "coverage"}:
        raise ValueError("suite must be one of: full, reference, coverage")
    if max_cases is not None:
        cases = cases[: max(0, int(max_cases))]
    return cases
