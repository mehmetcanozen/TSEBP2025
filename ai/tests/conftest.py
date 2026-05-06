"""Pytest controls for the AI workspace."""

from __future__ import annotations

from pathlib import Path

import pytest


LEGACY_ARTIFACT_TEST_FILES = {
    "test_waveformer_separator.py",
}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--run-manual", action="store_true", default=False, help="run manual tests")
    parser.addoption(
        "--run-audio-device",
        action="store_true",
        default=False,
        help="run tests that require a local audio device",
    )
    parser.addoption("--run-slow", action="store_true", default=False, help="run slow AI tests")
    parser.addoption(
        "--run-artifact-tests",
        action="store_true",
        default=False,
        help="run tests that require restored ai/models/Exports artifacts",
    )


def pytest_ignore_collect(collection_path, config: pytest.Config) -> bool:
    """Avoid importing legacy heavyweight model stacks during default fast runs."""

    path = Path(str(collection_path))
    if path.name in LEGACY_ARTIFACT_TEST_FILES and not config.getoption("--run-artifact-tests"):
        return True
    return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    gates = {
        "manual": (
            config.getoption("--run-manual"),
            pytest.mark.skip(reason="need --run-manual to run"),
        ),
        "requires_audio_device": (
            config.getoption("--run-audio-device"),
            pytest.mark.skip(reason="need --run-audio-device to run"),
        ),
        "slow": (
            config.getoption("--run-slow"),
            pytest.mark.skip(reason="need --run-slow to run"),
        ),
        "requires_artifacts": (
            config.getoption("--run-artifact-tests"),
            pytest.mark.skip(reason="need --run-artifact-tests to run"),
        ),
    }
    for item in items:
        for marker_name, (enabled, marker) in gates.items():
            if marker_name in item.keywords and not enabled:
                item.add_marker(marker)
