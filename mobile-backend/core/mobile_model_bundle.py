from __future__ import annotations

import hashlib
import json
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from database import models
from sqlalchemy.orm import Session

ACTIVE_MODEL_ENV = "TSEBP_ACTIVE_SUPPRESSION_MODEL"
REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_ROOT = REPO_ROOT / "ai" / "models"
MODEL_SELECTION_PATH = MODELS_ROOT / "model_selection.json"
DEFAULT_BUNDLE_KIND = "suppression_model_bundle"
DEFAULT_SAMPLE_RATE = 32_000
DEFAULT_SEGMENT_SECONDS = 5.0


@dataclass(frozen=True)
class PackagedModelPlatform:
    name: str
    runtime_kind: str
    artifact: str
    metadata_artifacts: tuple[str, ...]
    sample_rate: int
    segment_seconds: float | None = None
    overlap_seconds: float | None = None
    chunk_samples: int | None = None
    preferred_live_hop_ms: int | None = None
    mix_channels: int | None = None
    bundle_kind: str = DEFAULT_BUNDLE_KIND
    state_tensors: dict[str, list[int]] | None = None


@dataclass(frozen=True)
class PackagedModelSpec:
    package_path: Path
    root_dir: Path
    model_id: str
    package_version: str
    family: str
    display_name: str
    description: str
    suppression_strategy_kind: str
    categories: tuple[dict[str, Any], ...]
    presets: tuple[dict[str, Any], ...]
    platforms: dict[str, PackagedModelPlatform]

    def platform(self, name: str) -> PackagedModelPlatform:
        platform = self.platforms.get(name)
        if platform is None:
            raise KeyError(f"Model '{self.model_id}' does not define platform '{name}'")
        return platform

    def artifact_path(self, platform_name: str) -> Path:
        platform = self.platform(platform_name)
        return (self.root_dir / platform.artifact).resolve()

    def bundle_files(self, platform_name: str) -> list[Path]:
        platform = self.platform(platform_name)
        paths = [self.artifact_path(platform_name)]
        paths.extend((self.root_dir / relative).resolve() for relative in platform.metadata_artifacts)
        return paths


@dataclass
class PreparedDownloadArtifact:
    path: Path
    checksum: str
    file_size_mb: float
    filename: str
    media_type: str = "application/octet-stream"
    bundle_kind: str | None = None


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_model_selection() -> dict[str, Any]:
    if not MODEL_SELECTION_PATH.exists():
        raise FileNotFoundError(f"Shared model selection was not found: {MODEL_SELECTION_PATH}")
    return _read_json(MODEL_SELECTION_PATH)


def active_model_id() -> str:
    selection = _load_model_selection()
    override = os.getenv(ACTIVE_MODEL_ENV, "").strip()
    return override or str(selection["default_model_id"])


def iter_packaged_models() -> Iterable[PackagedModelSpec]:
    selection = _load_model_selection()
    for model_id in selection.get("models", {}):
        try:
            yield load_packaged_model(str(model_id))
        except FileNotFoundError:
            continue


def load_packaged_model(model_id: str | None = None) -> PackagedModelSpec:
    selection = _load_model_selection()
    resolved_model_id = model_id or active_model_id()
    models_map = selection.get("models", {})
    relative_package = models_map.get(resolved_model_id)
    if relative_package is None:
        raise KeyError(f"Unknown packaged model id '{resolved_model_id}'")

    package_path = (MODELS_ROOT / relative_package).resolve()
    payload = _read_json(package_path)
    platforms: dict[str, PackagedModelPlatform] = {}
    for platform_name, platform_payload in payload.get("platforms", {}).items():
        platforms[platform_name] = PackagedModelPlatform(
            name=platform_name,
            runtime_kind=str(platform_payload["runtime_kind"]),
            artifact=str(platform_payload["artifact"]),
            metadata_artifacts=tuple(platform_payload.get("metadata_artifacts", ())),
            sample_rate=int(platform_payload["sample_rate"]),
            segment_seconds=(
                float(platform_payload["segment_seconds"])
                if platform_payload.get("segment_seconds") is not None
                else None
            ),
            overlap_seconds=(
                float(platform_payload["overlap_seconds"])
                if platform_payload.get("overlap_seconds") is not None
                else None
            ),
            chunk_samples=(
                int(platform_payload["chunk_samples"])
                if platform_payload.get("chunk_samples") is not None
                else None
            ),
            preferred_live_hop_ms=(
                int(platform_payload["preferred_live_hop_ms"])
                if platform_payload.get("preferred_live_hop_ms") is not None
                else None
            ),
            mix_channels=(
                int(platform_payload["mix_channels"])
                if platform_payload.get("mix_channels") is not None
                else None
            ),
            bundle_kind=str(platform_payload.get("bundle_kind", DEFAULT_BUNDLE_KIND)),
            state_tensors=platform_payload.get("state_tensors"),
        )

    return PackagedModelSpec(
        package_path=package_path,
        root_dir=package_path.parent,
        model_id=str(payload["model_id"]),
        package_version=str(payload.get("package_version") or payload["model_id"]),
        family=str(payload["family"]),
        display_name=str(payload["display_name"]),
        description=str(payload.get("description", "")),
        suppression_strategy_kind=str(payload["suppression_strategy"]["kind"]),
        categories=tuple(dict(category) for category in payload.get("categories", ())),
        presets=tuple(dict(preset) for preset in payload.get("presets", ())),
        platforms=platforms,
    )


def load_active_packaged_model(platform_name: str = "android") -> PackagedModelSpec:
    model = load_packaged_model()
    model.platform(platform_name)
    return model


def discover_audiosep15_model_path() -> Path | None:
    try:
        return load_packaged_model("audiosep_hive15cat").artifact_path("android")
    except (FileNotFoundError, KeyError):
        return None


def resolve_packaged_model_for_artifact(
    artifact_path: Path,
    platform_name: str,
) -> PackagedModelSpec | None:
    resolved_artifact = artifact_path.resolve()
    try:
        active_model = load_active_packaged_model(platform_name)
        if active_model.artifact_path(platform_name) == resolved_artifact:
            return active_model
    except (FileNotFoundError, KeyError):
        pass

    for model in iter_packaged_models():
        try:
            candidate = model.artifact_path(platform_name)
        except KeyError:
            continue
        if candidate == resolved_artifact:
            return model

    artifact_name = resolved_artifact.name.lower()
    if artifact_name == "frozensep_hive_15cat.onnx":
        return load_packaged_model("audiosep_hive15cat")
    if artifact_name.endswith(".pte") or artifact_name.startswith("semantic_hearing_100ms_"):
        return load_packaged_model("waveformer_edge_100ms")
    return None


def compute_checksum(file_path: Path) -> str:
    sha = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def default_android_model_version_string(model: PackagedModelSpec) -> str:
    return model.package_version


def ensure_default_android_model_version(db: Session) -> models.ModelVersion | None:
    try:
        packaged_model = load_active_packaged_model("android")
    except (FileNotFoundError, KeyError):
        return None

    artifact_path = packaged_model.artifact_path("android")
    if not artifact_path.exists():
        return None

    version_string = default_android_model_version_string(packaged_model)
    existing = (
        db.query(models.ModelVersion)
        .filter(models.ModelVersion.version == version_string)
        .first()
    )
    if existing:
        file_size_mb = round(artifact_path.stat().st_size / (1024 * 1024), 2)
        checksum = compute_checksum(artifact_path)
        stored_path = Path(existing.file_path)
        needs_update = (
            existing.file_path != str(artifact_path)
            or not stored_path.exists()
            or existing.platform != "android"
            or existing.file_size_mb != file_size_mb
            or existing.checksum != checksum
            or not existing.is_active
        )
        if needs_update:
            existing.description = (
                f"Auto-registered packaged Android export for {packaged_model.display_name}."
            )
            existing.file_path = str(artifact_path)
            existing.file_size_mb = file_size_mb
            existing.checksum = checksum
            existing.platform = "android"
            existing.is_active = True
            db.commit()
            db.refresh(existing)
        return existing

    file_size_mb = round(artifact_path.stat().st_size / (1024 * 1024), 2)
    created = models.ModelVersion(
        version=version_string,
        description=f"Auto-registered packaged Android export for {packaged_model.display_name}.",
        file_path=str(artifact_path),
        file_size_mb=file_size_mb,
        checksum=compute_checksum(artifact_path),
        platform="android",
        is_active=True,
    )
    db.add(created)
    db.commit()
    db.refresh(created)
    return created


def prepare_download_artifact(
    version: models.ModelVersion,
    bundle_cache_dir: Path,
    requested_platform: str | None = None,
) -> PreparedDownloadArtifact:
    source_path = Path(version.file_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Model artifact does not exist: {source_path}")

    if source_path.suffix.lower() == ".zip":
        checksum = compute_checksum(source_path)
        return PreparedDownloadArtifact(
            path=source_path,
            checksum=checksum,
            file_size_mb=round(source_path.stat().st_size / (1024 * 1024), 2),
            filename=source_path.name,
            media_type="application/zip",
            bundle_kind=None,
        )

    resolved_platform = (requested_platform or version.platform or "all").strip().lower()
    if resolved_platform != "android":
        checksum = compute_checksum(source_path)
        return PreparedDownloadArtifact(
            path=source_path,
            checksum=checksum,
            file_size_mb=round(source_path.stat().st_size / (1024 * 1024), 2),
            filename=source_path.name,
            bundle_kind="raw_model",
        )

    packaged_model = resolve_packaged_model_for_artifact(source_path, "android")
    if packaged_model is None:
        raise FileNotFoundError(
            f"No packaged Android model definition was found for artifact: {source_path}"
        )

    bundle_path = build_android_bundle(version, packaged_model, bundle_cache_dir)
    checksum = compute_checksum(bundle_path)
    filename = f"{packaged_model.model_id}_android_v{version.version}.zip"
    return PreparedDownloadArtifact(
        path=bundle_path,
        checksum=checksum,
        file_size_mb=round(bundle_path.stat().st_size / (1024 * 1024), 2),
        filename=filename,
        media_type="application/zip",
        bundle_kind=packaged_model.platform("android").bundle_kind,
    )


def _cached_manifest_fingerprint(bundle_path: Path) -> str | None:
    if not bundle_path.exists():
        return None

    try:
        with zipfile.ZipFile(bundle_path, "r") as archive:
            with archive.open("manifest.sha256", "r") as handle:
                return handle.read().decode("utf-8").strip()
    except (KeyError, OSError, ValueError, zipfile.BadZipFile):
        return None


def build_android_bundle(
    version: models.ModelVersion,
    packaged_model: PackagedModelSpec,
    bundle_cache_dir: Path,
) -> Path:
    platform = packaged_model.platform("android")
    bundle_cache_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = bundle_cache_dir / f"{packaged_model.model_id}_android_v{version.version}.zip"

    included_files = collect_bundle_files(packaged_model, "android")
    manifest = build_manifest(version, packaged_model, platform, included_files)

    manifest_payload = json.dumps(manifest, indent=2, ensure_ascii=True)
    manifest_fingerprint = hashlib.sha256(manifest_payload.encode("utf-8")).hexdigest()

    source_mtime = max(path.stat().st_mtime for path in included_files.values())
    cached_fingerprint = _cached_manifest_fingerprint(bundle_path)
    if (
        bundle_path.exists()
        and bundle_path.stat().st_mtime >= source_mtime
        and cached_fingerprint == manifest_fingerprint
    ):
        return bundle_path

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest_payload)
        for relative_name, file_path in included_files.items():
            archive.write(file_path, arcname=relative_name)
        archive.writestr("manifest.sha256", manifest_fingerprint)

    return bundle_path


def collect_bundle_files(
    packaged_model: PackagedModelSpec,
    platform_name: str,
) -> dict[str, Path]:
    bundle_files: dict[str, Path] = {}
    for file_path in packaged_model.bundle_files(platform_name):
        if not file_path.exists():
            raise FileNotFoundError(f"Bundle file does not exist: {file_path}")
        bundle_files[file_path.name] = file_path
    return bundle_files


def build_manifest(
    version: models.ModelVersion,
    packaged_model: PackagedModelSpec,
    platform: PackagedModelPlatform,
    included_files: dict[str, Path],
) -> dict[str, Any]:
    primary_artifact_name = Path(platform.artifact).name
    artifacts = []
    for filename, file_path in included_files.items():
        lower = filename.lower()
        if lower.endswith(".onnx"):
            format_name = "onnx"
        elif lower.endswith(".ort"):
            format_name = "ort"
        elif lower.endswith(".pte"):
            format_name = "executorch"
        elif lower.endswith(".json"):
            format_name = "json"
        elif lower.endswith(".txt"):
            format_name = "text"
        elif lower.endswith(".yaml"):
            format_name = "yaml"
        else:
            format_name = "binary"

        if filename == primary_artifact_name:
            role = "model"
        else:
            role = "metadata"

        if format_name == "executorch":
            provider = "executorch"
        elif format_name in {"onnx", "ort"}:
            provider = "cpu"
        else:
            provider = "metadata"

        artifacts.append(
            {
                "filename": filename,
                "format": format_name,
                "provider": provider,
                "role": role,
                "sha256": compute_checksum(file_path),
                "bytes": file_path.stat().st_size,
            }
        )

    created_at = version.created_at.isoformat() if isinstance(version.created_at, datetime) else None
    manifest: dict[str, Any] = {
        "schema_version": 2,
        "bundle_kind": platform.bundle_kind,
        "model_id": packaged_model.model_id,
        "package_version": packaged_model.package_version,
        "model_family": packaged_model.family,
        "display_name": packaged_model.display_name,
        "suppression_strategy": packaged_model.suppression_strategy_kind,
        "runtime_kind": platform.runtime_kind,
        "version": version.version,
        "platform": version.platform,
        "created_at": created_at,
        "sample_rate": platform.sample_rate,
        "preferred_live_hop_ms": platform.preferred_live_hop_ms,
        "mix_channels": platform.mix_channels,
        "categories": list(packaged_model.categories),
        "artifacts": artifacts,
    }

    if platform.segment_seconds is not None:
        manifest["segment_seconds"] = platform.segment_seconds
    if platform.overlap_seconds is not None:
        manifest["overlap_seconds"] = platform.overlap_seconds
    if platform.chunk_samples is not None:
        manifest["chunk_samples"] = platform.chunk_samples
    if platform.state_tensors:
        manifest["state_tensors"] = platform.state_tensors

    return manifest
