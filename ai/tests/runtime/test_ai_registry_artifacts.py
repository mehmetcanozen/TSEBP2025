from __future__ import annotations

from ai.ai_runtime.artifacts import check_artifacts, missing_required_artifacts
from ai.ai_runtime.contracts import BackendId
from ai.ai_runtime.registry import get_backend, list_backends


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


def test_artifact_checks_include_actionable_required_entries():
    statuses = check_artifacts(include_optional=False)
    keys = {status.key for status in statuses}

    assert "waveformer_desktop_onnx" in keys
    assert "target_speaker_tsextract_external_data" in keys
    assert all(status.notes for status in statuses)


def test_missing_required_artifacts_are_structured():
    missing = missing_required_artifacts()

    assert all(not status.exists for status in missing)
    assert all(status.path.is_absolute() for status in missing)
