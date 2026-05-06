from __future__ import annotations

import subprocess
import sys

from typer.testing import CliRunner

from ai.cli.main import app


runner = CliRunner()


def test_python_module_help_runs():
    result = subprocess.run(
        [sys.executable, "-m", "ai", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "suppress" in result.stdout
    assert "artifacts" in result.stdout


def test_models_list_runs():
    result = runner.invoke(app, ["models", "list"])

    assert result.exit_code == 0, result.output
    assert "Default model:" in result.output
    assert "waveformer" in result.output


def test_artifacts_check_runs_without_strict_failure():
    result = runner.invoke(app, ["artifacts", "check", "--required-only"])

    assert result.exit_code == 0, result.output
    assert "waveformer" in result.output


def test_suppress_file_help_runs():
    result = runner.invoke(app, ["suppress", "file", "--help"])

    assert result.exit_code == 0, result.output
    assert "--input" in result.output
    assert "--target" in result.output
    assert "--backend" in result.output


def test_tsebp_ai_script_entry_declared():
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["scripts"]["tsebp-ai"] == "ai.cli.main:app"


def test_suppress_file_waveformer_uses_packaged_processor(monkeypatch, tmp_path):
    from ai.cli.commands import suppress as suppress_command

    calls = {}

    class FakeWaveformerProcessor:
        def process_file(self, **kwargs):
            calls.update(kwargs)
            return {
                "output_file": str(kwargs["output_path"]),
                "noise_audio": None,
                "sample_rate": 44100,
                "duration_seconds": 1.0,
                "rms_reduction_db": 0.5,
            }

    monkeypatch.setattr(suppress_command, "WaveformerOnnxBatchProcessor", FakeWaveformerProcessor)

    result = runner.invoke(
        app,
        [
            "suppress",
            "file",
            "--input",
            str(tmp_path / "input.wav"),
            "--output",
            str(tmp_path / "output.wav"),
            "--target",
            "dog",
            "--backend",
            "waveformer",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls["suppress_categories"] == ["dog"]
    assert calls["output_path"] == tmp_path / "output.wav"


def test_compare_run_repeated_model_options_are_forwarded_as_one_legacy_list(monkeypatch):
    from ai.cli.commands import compare as compare_command

    captured = {}

    def fake_main(argv):
        captured["argv"] = list(argv)
        return 0

    monkeypatch.setattr(compare_command.run_model_comparison, "main", fake_main)

    result = runner.invoke(
        app,
        [
            "compare",
            "run",
            "--model",
            "waveformer",
            "--model",
            "waveformer_onnx_export",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["argv"] == [
        "--models",
        "waveformer",
        "waveformer_onnx_export",
        "--dry-run",
    ]


def test_legacy_batch_processor_help_points_to_new_cli():
    result = subprocess.run(
        [sys.executable, "-m", "ai.ai_runtime.batch.batch_processor", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Legacy path notice" in result.stderr
    assert "--input" in result.stdout


def test_legacy_virtual_mic_help_points_to_new_cli():
    result = subprocess.run(
        [sys.executable, "-m", "ai.scripts.demos.virtual_mic_streamer", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Legacy path notice" in result.stderr
    assert "--list-devices" in result.stdout


def test_legacy_compare_help_points_to_new_cli():
    result = subprocess.run(
        [sys.executable, "-m", "ai.scripts.run_model_comparison", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Legacy path notice" in result.stderr
    assert "--list-models" in result.stdout
