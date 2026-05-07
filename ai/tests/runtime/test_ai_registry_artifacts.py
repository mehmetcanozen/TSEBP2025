from __future__ import annotations

from ai.ai_runtime.artifacts import check_artifacts, missing_required_artifacts
from ai.ai_runtime.contracts import BackendId
from ai.ai_runtime.registry import get_backend, list_backends, list_model_packages


def test_backend_registry_is_deterministic():
    ids = [item.backend_id for item in list_backends()]

    assert ids == [
        BackendId.WAVEFORMER,
        BackendId.CODECSEP,
        BackendId.AUDIOSEP_HIVE15CAT,
        BackendId.CODECSEP_DNRV2_15CAT,
        BackendId.TARGET_SPEAKER,
    ]


def test_backend_registry_resolves_waveformer_categories():
    info = get_backend("waveformer")

    assert info.backend_id == BackendId.WAVEFORMER
    assert "dog" in info.categories
    assert info.artifact_paths


def test_model_package_registry_includes_research_checkpoints():
    packages = {item.model_id: item for item in list_model_packages()}

    assert "audiosep_open_vocab" in packages
    assert "audiosep_hive_raw" in packages
    assert "clapsep_research" in packages
    assert packages["audiosep_open_vocab"].runtime_status == "registered_research_runtime"
    assert packages["audiosep_hive_raw"].runtime_status == "registered_research_checkpoint"
    assert packages["clapsep_research"].artifact_paths


def test_model_package_registry_handles_missing_optional_manifest(monkeypatch, tmp_path):
    from ai.ai_runtime import registry

    monkeypatch.setattr(
        registry,
        "load_model_selection",
        lambda: {"models": {"optional_missing": "OptionalMissing/model_package.json"}},
    )
    monkeypatch.setattr(registry, "get_models_path", lambda: tmp_path)

    packages = registry.list_model_packages()

    assert len(packages) == 1
    assert packages[0].model_id == "optional_missing"
    assert packages[0].runtime_status == "missing_manifest"
    assert packages[0].package_path == (tmp_path / "OptionalMissing" / "model_package.json").resolve()


def test_artifact_checks_include_actionable_required_entries():
    statuses = check_artifacts(include_optional=False)
    keys = {status.key for status in statuses}

    assert "waveformer_desktop_onnx" in keys
    assert "target_speaker_tsextract_external_data" in keys
    assert all(status.notes for status in statuses)


def test_artifact_checks_include_research_checkpoint_entries():
    statuses = check_artifacts(include_optional=True)
    keys = {status.key for status in statuses}

    assert "audiosep_open_vocab_checkpoint" in keys
    assert "audiosep_hive_raw_checkpoint" in keys
    assert "clapsep_research_checkpoint" in keys


def test_missing_required_artifacts_are_structured():
    missing = missing_required_artifacts()

    assert all(not status.exists for status in missing)
    assert all(status.path.is_absolute() for status in missing)
