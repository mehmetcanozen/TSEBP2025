"""Shared runtime contracts for the Python AI workspace.

These small data classes keep CLI, diagnostics, and tests from depending on
implementation-specific parser objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class BackendId(StrEnum):
    """Known separator backends exposed by the Python AI runtime."""

    WAVEFORMER = "waveformer"
    CODECSEP = "codecsep"
    AUDIOSEP_HIVE15CAT = "audiosep_hive15cat"
    CODECSEP_DNRV2_15CAT = "codecsep_dnrv2_15cat"
    TARGET_SPEAKER = "target_speaker"


class ArtifactRole(StrEnum):
    """Why an artifact matters to the local developer workflow."""

    REQUIRED = "required"
    OPTIONAL = "optional"
    GENERATED = "generated"


@dataclass(frozen=True)
class BackendInfo:
    """Human-readable runtime backend metadata."""

    backend_id: BackendId
    display_name: str
    category_surface: str
    runtime_kind: str
    notes: str
    categories: tuple[str, ...] = ()
    artifact_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class ArtifactStatus:
    """File-level artifact diagnostic status."""

    key: str
    path: Path
    role: ArtifactRole
    exists: bool
    size_bytes: int | None = None
    notes: str = ""

    @classmethod
    def from_path(
        cls,
        *,
        key: str,
        path: Path,
        role: ArtifactRole,
        notes: str = "",
    ) -> "ArtifactStatus":
        return cls(
            key=key,
            path=path,
            role=role,
            exists=path.exists(),
            size_bytes=path.stat().st_size if path.is_file() else None,
            notes=notes,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "path": str(self.path),
            "role": self.role.value,
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class SuppressionFileRequest:
    """Canonical file-suppression request used by CLI tests and wrappers."""

    input_path: Path
    output_path: Path
    targets: tuple[str, ...]
    backend: BackendId = BackendId.WAVEFORMER
    aggressiveness: float = 1.5
    threshold: float = 0.5
    chunk_size_seconds: float = 10.0
    output_noise: bool = False
    extra_options: dict[str, Any] = field(default_factory=dict)
