"""Shared contracts for AI evaluation runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


CaseTier = Literal["reference", "coverage"]


@dataclass(frozen=True)
class EvalCase:
    """One audio input evaluated against all selected models."""

    case_id: str
    tier: CaseTier
    input_path: Path
    targets: dict[str, str]
    clean_reference_path: Path | None = None
    unwanted_reference_path: Path | None = None
    tags: tuple[str, ...] = ()
    notes: str = ""
    primary_ranking: bool = True
    speech_reference: bool = False

    def target_for_surface(self, surface: str) -> str:
        if surface in self.targets:
            return self.targets[surface]
        if "audiosep_prompt" in self.targets:
            return self.targets["audiosep_prompt"]
        if "exact15" in self.targets:
            return self.targets["exact15"]
        if "waveformer20" in self.targets:
            return self.targets["waveformer20"]
        if "legacy" in self.targets:
            return self.targets["legacy"]
        return "background noise"

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["input_path"] = str(self.input_path)
        row["clean_reference_path"] = (
            str(self.clean_reference_path) if self.clean_reference_path else ""
        )
        row["unwanted_reference_path"] = (
            str(self.unwanted_reference_path) if self.unwanted_reference_path else ""
        )
        row["targets"] = "; ".join(f"{key}={value}" for key, value in sorted(self.targets.items()))
        row["tags"] = ",".join(self.tags)
        return row

    def to_json_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["input_path"] = str(self.input_path)
        payload["clean_reference_path"] = (
            str(self.clean_reference_path) if self.clean_reference_path else None
        )
        payload["unwanted_reference_path"] = (
            str(self.unwanted_reference_path) if self.unwanted_reference_path else None
        )
        return payload

    @classmethod
    def from_json_dict(cls, payload: dict[str, Any]) -> "EvalCase":
        data = dict(payload)
        data["input_path"] = Path(data["input_path"])
        data["clean_reference_path"] = (
            Path(data["clean_reference_path"]) if data.get("clean_reference_path") else None
        )
        data["unwanted_reference_path"] = (
            Path(data["unwanted_reference_path"])
            if data.get("unwanted_reference_path")
            else None
        )
        data["tags"] = tuple(data.get("tags") or ())
        return cls(**data)


@dataclass(frozen=True)
class ModelEvalSpec:
    """Model adapter metadata used by the evaluator and workers."""

    model_id: str
    display_name: str
    adapter_kind: str
    target_surface: str
    runtime: str
    runnable: bool = True
    unsupported_reason: str = ""
    artifact_paths: tuple[Path, ...] = ()
    adapter_options: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["artifact_paths"] = [str(path) for path in self.artifact_paths]
        return payload

    @classmethod
    def from_json_dict(cls, payload: dict[str, Any]) -> "ModelEvalSpec":
        data = dict(payload)
        data["artifact_paths"] = tuple(Path(path) for path in data.get("artifact_paths", []))
        return cls(**data)


@dataclass(frozen=True)
class AdapterResult:
    """Result returned by one adapter for one case run."""

    clean_path: Path
    removed_path: Path
    sample_rate: int
    duration_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationSettings:
    """Serializable settings passed from the parent evaluator to workers."""

    repeats: int = 1
    warmup_runs: int = 1
    chunk_size_seconds: float = 10.0
    threshold: float = 0.5
    aggressiveness: float = 1.0
    save_audio: bool = True

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, payload: dict[str, Any]) -> "EvaluationSettings":
        return cls(**payload)
