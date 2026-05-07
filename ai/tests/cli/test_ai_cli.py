from __future__ import annotations

import csv
import importlib
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
    assert "audiosep_open_vocab" in result.output
    assert "audiosep_hive_raw" in result.output
    assert "clapsep_research" in result.output


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
    assert "--audiosep-prompt" in result.output


def test_evaluate_help_runs():
    result = runner.invoke(app, ["evaluate", "--help"])

    assert result.exit_code == 0, result.output
    assert "plan" in result.output
    assert "run" in result.output
    assert "report" in result.output


def test_evaluate_list_models_runs():
    result = runner.invoke(app, ["evaluate", "list-models"])

    assert result.exit_code == 0, result.output
    assert "waveformer_onnx_export" in result.output
    assert "target_speaker_windows" in result.output
    assert "out of scope" in result.output.lower()


def test_evaluate_plan_dry_run_does_not_require_model_imports(tmp_path):
    result = runner.invoke(
        app,
        [
            "evaluate",
            "plan",
            "--models",
            "all",
            "--max-cases",
            "1",
            "--output-root",
            str(tmp_path / "plan"),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "waveformer_onnx_export" in result.output
    assert not (tmp_path / "plan" / "manifest.json").exists()


def test_cli_command_modules_do_not_import_heavy_runtimes():
    from ai.cli.commands import compare as compare_command
    from ai.cli.commands import suppress as suppress_command

    heavy_modules = [
        "ai.scripts.run_model_comparison",
        "ai.ai_runtime.batch.batch_processor",
        "ai.ai_runtime.separation.codecsep_separator",
    ]
    for module_name in heavy_modules:
        sys.modules.pop(module_name, None)

    importlib.reload(compare_command)
    importlib.reload(suppress_command)

    for module_name in heavy_modules:
        assert module_name not in sys.modules


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

    monkeypatch.setattr(suppress_command, "_build_waveformer_processor", FakeWaveformerProcessor)

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


def test_compare_run_repeated_model_options_are_written_as_two_dry_run_rows(tmp_path):
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
            "--output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    with (tmp_path / "comparison_summary.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["model"] for row in rows] == ["waveformer", "waveformer_onnx_export"]
    assert [row["status"] for row in rows] == ["planned", "planned"]


def test_compare_run_dry_run_expands_default_auto_group(tmp_path):
    result = runner.invoke(
        app,
        [
            "compare",
            "run",
            "--dry-run",
            "--output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    with (tmp_path / "comparison_summary.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["model"] for row in rows] == [
        "waveformer",
        "audiosep_hive15cat_onnx",
        "codecsep_dnrv2_15cat_onnx",
        "codecsep_dnrv2_15cat_executorch",
    ]


def test_compare_run_dry_run_expands_exact15_group(tmp_path):
    result = runner.invoke(
        app,
        [
            "compare",
            "run",
            "--model",
            "exact15",
            "--dry-run",
            "--output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    with (tmp_path / "comparison_summary.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["model"] for row in rows] == [
        "audiosep_hive15cat_onnx",
        "codecsep_dnrv2_15cat_onnx",
        "codecsep_dnrv2_15cat_executorch",
    ]


def test_compare_run_dry_run_uses_audiosep_open_vocab_name(tmp_path):
    result = runner.invoke(
        app,
        [
            "compare",
            "run",
            "--model",
            "audiosep_open_vocab",
            "--dry-run",
            "--audiosep-prompt",
            "boat engine",
            "--output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    with (tmp_path / "comparison_summary.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["model"] == "audiosep_open_vocab"
    assert rows[0]["audiosep_prompt"] == "boat engine"


def test_compare_run_dry_run_maps_legacy_pure_audiosep_alias(tmp_path):
    result = runner.invoke(
        app,
        [
            "compare",
            "run",
            "--model",
            "pure_audiosep",
            "--dry-run",
            "--output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    with (tmp_path / "comparison_summary.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["model"] == "audiosep_open_vocab"


def test_compare_run_dry_run_maps_package_model_aliases(tmp_path):
    result = runner.invoke(
        app,
        [
            "compare",
            "run",
            "--model",
            "audiosep_hive15cat",
            "--model",
            "codecsep_dnrv2_15cat",
            "--dry-run",
            "--output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    with (tmp_path / "comparison_summary.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["model"] for row in rows] == [
        "audiosep_hive15cat_onnx",
        "codecsep_dnrv2_15cat_onnx",
    ]


def test_compare_run_dry_run_rejects_unknown_model(tmp_path):
    result = runner.invoke(
        app,
        [
            "compare",
            "run",
            "--model",
            "not_a_model",
            "--dry-run",
            "--output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "Unknown model 'not_a_model'" in result.output
    assert not (tmp_path / "comparison_summary.csv").exists()


def test_compare_run_real_path_forwards_package_aliases(monkeypatch):
    from ai.cli.commands import compare as compare_command

    captured = {}

    def fake_run_legacy(argv):
        captured["argv"] = list(argv)
        return 0

    monkeypatch.setattr(compare_command, "_run_legacy_comparison", fake_run_legacy)

    result = runner.invoke(
        app,
        [
            "compare",
            "run",
            "--model",
            "audiosep_hive15cat",
            "--model",
            "codecsep_dnrv2_15cat",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["argv"] == [
        "--models",
        "audiosep_hive15cat_onnx",
        "codecsep_dnrv2_15cat_onnx",
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
