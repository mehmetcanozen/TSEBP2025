import io
import json
import zipfile
from pathlib import Path

from core import mobile_model_bundle
from database import models
from conftest import TestingSession


def _fake_packaged_model(
    tmp_path: Path,
    artifact_name: str = "frozensep_hive_15cat.onnx",
    *,
    runtime_kind: str = "onnx_category_separator",
):
    model_path = tmp_path / artifact_name
    model_path.write_bytes(b"dummy-model")
    metadata_path = tmp_path / "categories_15.txt"
    metadata_path.write_text("speech\nmusic\nalarm\n", encoding="utf-8")

    platform = mobile_model_bundle.PackagedModelPlatform(
        name="android",
        runtime_kind=runtime_kind,
        artifact=artifact_name,
        metadata_artifacts=("categories_15.txt",),
        sample_rate=32_000,
        segment_seconds=5.0,
        overlap_seconds=1.0,
        preferred_live_hop_ms=500,
    )
    return mobile_model_bundle.PackagedModelSpec(
        package_path=tmp_path / "model_package.json",
        root_dir=tmp_path,
        model_id="test_audiosep",
        package_version="test_audiosep_20260418",
        family="audiosep",
        display_name="Test AudioSep",
        description="test packaged model",
        suppression_strategy_kind="masked_unwanted_track",
        categories=(
            {
                "id": "speech",
                "label": "speech",
                "default_aggressiveness": 1.4,
                "transient": False,
            },
            {
                "id": "music",
                "label": "music",
                "default_aggressiveness": 1.5,
                "transient": False,
            },
            {
                "id": "alarm",
                "label": "alarm",
                "default_aggressiveness": 2.0,
                "transient": True,
            },
        ),
        presets=(),
        platforms={"android": platform},
    )


def _create_model_version(model_path: Path, platform: str = "android", version: str = "2.0.0") -> int:
    db = TestingSession()
    try:
        row = models.ModelVersion(
            version=version,
            description="android bundle test",
            file_path=str(model_path),
            file_size_mb=0.0,
            checksum="placeholder",
            platform=platform,
            is_active=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def test_latest_android_model_reports_bundle_metadata(client, auth_headers, tmp_path, monkeypatch):
    packaged_model = _fake_packaged_model(tmp_path)

    monkeypatch.setattr(
        mobile_model_bundle,
        "load_active_packaged_model",
        lambda platform_name="android": packaged_model,
    )
    monkeypatch.setattr(
        mobile_model_bundle,
        "resolve_packaged_model_for_artifact",
        lambda artifact_path, platform_name="android": packaged_model,
    )

    response = client.get("/model/latest?platform=android", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["has_update"] is True
    assert payload["bundle_kind"] == "suppression_model_bundle"
    assert payload["latest_version"] == packaged_model.package_version
    assert payload["filename"].endswith(".zip")
    assert payload["download_url"]


def test_android_model_download_returns_bundle_zip(client, auth_headers, tmp_path, monkeypatch):
    packaged_model = _fake_packaged_model(tmp_path)
    monkeypatch.setattr(
        mobile_model_bundle,
        "resolve_packaged_model_for_artifact",
        lambda artifact_path, platform_name="android": packaged_model
    )

    version_id = _create_model_version(packaged_model.artifact_path("android"), version="2.0.1")

    response = client.get(f"/model/download/{version_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")

    with zipfile.ZipFile(io.BytesIO(response.content), "r") as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "frozensep_hive_15cat.onnx" in names
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert manifest["bundle_kind"] == "suppression_model_bundle"
    assert manifest["model_id"] == packaged_model.model_id
    assert manifest["sample_rate"] == 32000
    assert manifest["segment_seconds"] == 5.0
    assert manifest["categories"][0]["id"] == "speech"


def test_android_bundle_marks_executorch_category_separator_artifact(client, auth_headers, tmp_path, monkeypatch):
    packaged_model = _fake_packaged_model(
        tmp_path,
        artifact_name="codecsep_dnrv2_15cat.pte",
        runtime_kind="executorch_category_separator",
    )
    monkeypatch.setattr(
        mobile_model_bundle,
        "resolve_packaged_model_for_artifact",
        lambda artifact_path, platform_name="android": packaged_model
    )

    version_id = _create_model_version(packaged_model.artifact_path("android"), version="2.0.3")

    response = client.get(f"/model/download/{version_id}", headers=auth_headers)
    assert response.status_code == 200

    with zipfile.ZipFile(io.BytesIO(response.content), "r") as archive:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert manifest["runtime_kind"] == "executorch_category_separator"
    model_artifact = next(item for item in manifest["artifacts"] if item["role"] == "model")
    assert model_artifact["filename"] == "codecsep_dnrv2_15cat.pte"
    assert model_artifact["format"] == "executorch"
    assert model_artifact["provider"] == "executorch"


def test_latest_android_model_auto_registers_repository_export(
    client,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    packaged_model = _fake_packaged_model(tmp_path)
    monkeypatch.setattr(
        mobile_model_bundle,
        "load_active_packaged_model",
        lambda platform_name="android": packaged_model,
    )

    response = client.get("/model/latest?platform=android", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["bundle_kind"] == "suppression_model_bundle"
    assert payload["latest_version"] == packaged_model.package_version
    assert payload["download_url"]

    db = TestingSession()
    try:
        created = db.query(models.ModelVersion).filter_by(version=payload["latest_version"]).one()
        assert created.file_path == str(packaged_model.artifact_path("android"))
        assert created.platform == "android"
        assert created.is_active is True
    finally:
        db.close()


def test_latest_android_model_prefers_active_db_version_over_packaged_default(
    client,
    auth_headers,
    tmp_path,
    monkeypatch,
):
    packaged_model = _fake_packaged_model(tmp_path)
    manual_version = "9.9.9-manual"
    _create_model_version(packaged_model.artifact_path("android"), version=manual_version)

    monkeypatch.setattr(
        mobile_model_bundle,
        "load_active_packaged_model",
        lambda platform_name="android": packaged_model,
    )
    monkeypatch.setattr(
        mobile_model_bundle,
        "resolve_packaged_model_for_artifact",
        lambda artifact_path, platform_name="android": packaged_model,
    )

    response = client.get("/model/latest?platform=android", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_version"] == manual_version

    db = TestingSession()
    try:
        versions = db.query(models.ModelVersion).order_by(models.ModelVersion.created_at.asc()).all()
        assert len(versions) == 1
        assert versions[0].version == manual_version
    finally:
        db.close()


def test_build_android_bundle_rebuilds_when_manifest_payload_changes(tmp_path):
    packaged_model = _fake_packaged_model(tmp_path)
    version_id = _create_model_version(packaged_model.artifact_path("android"), version="2.0.2")

    db = TestingSession()
    try:
        version = db.query(models.ModelVersion).filter_by(id=version_id).one()
        bundle_cache_dir = tmp_path / "bundle-cache"

        first_bundle = mobile_model_bundle.build_android_bundle(version, packaged_model, bundle_cache_dir)
        with zipfile.ZipFile(first_bundle, "r") as archive:
            first_manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert first_manifest["display_name"] == "Test AudioSep"

        updated_model = mobile_model_bundle.PackagedModelSpec(
            package_path=packaged_model.package_path,
            root_dir=packaged_model.root_dir,
            model_id=packaged_model.model_id,
            package_version=packaged_model.package_version,
            family=packaged_model.family,
            display_name="Updated Test AudioSep",
            description=packaged_model.description,
            suppression_strategy_kind=packaged_model.suppression_strategy_kind,
            categories=packaged_model.categories,
            presets=packaged_model.presets,
            platforms=packaged_model.platforms,
        )

        rebuilt_bundle = mobile_model_bundle.build_android_bundle(version, updated_model, bundle_cache_dir)
        with zipfile.ZipFile(rebuilt_bundle, "r") as archive:
            rebuilt_manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

        assert rebuilt_manifest["display_name"] == "Updated Test AudioSep"
    finally:
        db.close()


def test_latest_windows_model_reports_raw_artifact_metadata(client, auth_headers, tmp_path):
    model_path = tmp_path / "manual_windows.onnx"
    model_path.write_bytes(b"raw-windows-model")
    version_id = _create_model_version(model_path, platform="windows", version="3.0.0")

    response = client.get("/model/latest?platform=windows", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_version"] == "3.0.0"
    assert payload["bundle_kind"] == "raw_model"
    assert payload["filename"] == "manual_windows.onnx"
    assert payload["download_url"] == f"/model/download/{version_id}?platform=windows"


def test_windows_model_download_returns_raw_artifact(client, auth_headers, tmp_path):
    model_bytes = b"raw-windows-model"
    model_path = tmp_path / "manual_windows.onnx"
    model_path.write_bytes(model_bytes)
    version_id = _create_model_version(model_path, platform="windows", version="3.0.1")

    response = client.get(f"/model/download/{version_id}?platform=windows", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/octet-stream")
    assert response.content == model_bytes
