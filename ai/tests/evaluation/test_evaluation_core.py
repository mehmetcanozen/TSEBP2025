from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from ai.evaluation import worker as worker_module
from ai.evaluation.adapters import SemanticBatchAdapter
from ai.evaluation.cases import build_coverage_cases, build_evaluation_cases
from ai.evaluation.contracts import AdapterResult, EvalCase, EvaluationSettings, ModelEvalSpec
from ai.evaluation.metrics import compute_case_metrics
from ai.evaluation.report import generate_report
from ai.evaluation.runner import _resolve_output_root, build_rankings


def _write_wav(path: Path, audio: np.ndarray, sample_rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio.astype(np.float32), sample_rate)


def test_reference_manifest_parses_repo_cases():
    cases = build_evaluation_cases(suite="reference")

    case_ids = {case.case_id for case in cases}
    assert "speech_barking" in case_ids
    assert "speech_keyboard" in case_ids
    assert all(case.tier == "reference" for case in cases)
    assert any(case.target_for_surface("waveformer20") == "dog" for case in cases)


def test_coverage_case_inference_uses_raw_file_names(tmp_path):
    _write_wav(tmp_path / "speech_keyboard_demo.wav", np.zeros(1600, dtype=np.float32))

    cases = build_coverage_cases(input_dir=tmp_path)

    assert len(cases) == 1
    assert cases[0].target_for_surface("waveformer20") == "computer_typing"
    assert cases[0].target_for_surface("exact15") == "keyboard typing"


def test_reference_metrics_improve_when_output_matches_clean_reference(tmp_path):
    sample_rate = 16000
    t = np.arange(sample_rate, dtype=np.float32) / sample_rate
    clean = 0.2 * np.sin(2 * np.pi * 440 * t)
    unwanted = 0.1 * np.sin(2 * np.pi * 1200 * t)
    mixture = clean + unwanted

    input_path = tmp_path / "mixture.wav"
    clean_ref = tmp_path / "clean.wav"
    unwanted_ref = tmp_path / "unwanted.wav"
    clean_out = tmp_path / "out" / "clean.wav"
    removed_out = tmp_path / "out" / "removed.wav"
    _write_wav(input_path, mixture, sample_rate)
    _write_wav(clean_ref, clean, sample_rate)
    _write_wav(unwanted_ref, unwanted, sample_rate)
    _write_wav(clean_out, clean, sample_rate)
    _write_wav(removed_out, unwanted, sample_rate)

    case = EvalCase(
        case_id="synthetic",
        tier="reference",
        input_path=input_path,
        clean_reference_path=clean_ref,
        unwanted_reference_path=unwanted_ref,
        targets={"waveformer20": "dog"},
        primary_ranking=True,
        speech_reference=False,
    )
    metrics = compute_case_metrics(
        case=case,
        result=AdapterResult(
            clean_path=clean_out,
            removed_path=removed_out,
            sample_rate=sample_rate,
            duration_seconds=1.0,
            metadata={"target": "dog"},
        ),
        model_id="synthetic_model",
        repeat_index=1,
        end_to_end_seconds=0.5,
        status="success",
    )

    assert metrics["clean_si_sdr_improvement_db"] > 10.0
    assert metrics["removed_unwanted_correlation"] > 0.99
    assert metrics["real_time_factor"] == 0.5


def test_rankings_handle_unsupported_rows():
    rankings = build_rankings(
        metrics_rows=[
            {
                "model": "good",
                "case_id": "case",
                "tier": "reference",
                "primary_ranking": True,
                "status": "success",
                "clean_si_sdr_improvement_db": 5.0,
                "removed_unwanted_si_sdr_db": 4.0,
                "residual_unwanted_correlation": 0.1,
                "clipping_rate": 0.0,
                "real_time_factor": 0.5,
            },
            {
                "model": "unsupported",
                "case_id": "case",
                "tier": "reference",
                "primary_ranking": True,
                "status": "unsupported",
            },
        ],
        resources_rows=[
            {"model": "good", "peak_rss_mb": 200.0},
            {"model": "unsupported", "peak_rss_mb": 0.0},
        ],
    )

    assert rankings[0]["model"] == "good"
    assert any(row["model"] == "unsupported" for row in rankings)


def test_failed_worker_case_writes_metric_row(monkeypatch, tmp_path):
    class FailingAdapter:
        def load(self):
            return {"adapter": "failing"}

        def process(self, case, output_dir, repeat_index):
            raise RuntimeError("boom")

        def close(self):
            return None

    monkeypatch.setattr(worker_module, "build_adapter", lambda spec, settings: FailingAdapter())
    input_path = tmp_path / "input.wav"
    _write_wav(input_path, np.zeros(1600, dtype=np.float32))
    spec = ModelEvalSpec(
        model_id="failing_model",
        display_name="Failing model",
        adapter_kind="semantic_batch",
        target_surface="exact15",
        runtime="test",
    )
    case = EvalCase(
        case_id="case",
        tier="reference",
        input_path=input_path,
        targets={"exact15": "dog barking"},
    )
    result_path = tmp_path / "worker.result.json"
    payload_path = tmp_path / "worker.payload.json"
    payload_path.write_text(
        json.dumps(
            {
                "model": spec.to_json_dict(),
                "settings": EvaluationSettings(warmup_runs=0).to_json_dict(),
                "cases": [case.to_json_dict()],
                "output_dir": str(tmp_path / "outputs"),
                "result_path": str(result_path),
            },
            default=str,
        ),
        encoding="utf-8",
    )

    assert worker_module.run_worker(payload_path) == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert result["runs"][0]["status"] == "failed"
    assert result["metrics"][0]["status"] == "failed"
    rankings = build_rankings(
        metrics_rows=result["metrics"],
        resources_rows=[{"model": "failing_model", "peak_rss_mb": 1.0}],
    )
    assert rankings[0]["model"] == "failing_model"
    assert rankings[0]["status"] == "no_successful_runs"


def test_relative_evaluation_output_root_resolves_to_absolute_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    resolved = _resolve_output_root(Path("relative_eval"))

    assert resolved == (tmp_path / "relative_eval").resolve()
    assert resolved.is_absolute()


def test_semantic_batch_adapter_writes_removed_without_noise_sidecar(tmp_path):
    sample_rate = 16000
    input_path = tmp_path / "input.wav"
    _write_wav(input_path, np.zeros(1600, dtype=np.float32), sample_rate)

    class FakeProcessor:
        def process_file(self, *, output_path, **kwargs):
            _write_wav(output_path, np.zeros(1600, dtype=np.float32), sample_rate)
            return {
                "sample_rate": sample_rate,
                "duration_seconds": 0.1,
                "noise_audio": np.ones(1600, dtype=np.float32) * 0.01,
            }

    spec = ModelEvalSpec(
        model_id="semantic",
        display_name="Semantic",
        adapter_kind="semantic_batch",
        target_surface="exact15",
        runtime="test",
    )
    adapter = SemanticBatchAdapter(spec, EvaluationSettings())
    adapter.processor = FakeProcessor()
    adapter.process_kwargs = {}
    case = EvalCase(
        case_id="case",
        tier="reference",
        input_path=input_path,
        targets={"exact15": "dog barking"},
    )

    result = adapter.process(case, tmp_path / "outputs", repeat_index=1)

    assert result.removed_path == tmp_path / "outputs" / "removed.wav"
    assert result.removed_path.exists()
    assert not (tmp_path / "outputs" / "clean_noise.wav").exists()


def test_report_generation_from_fixture_outputs(tmp_path):
    (tmp_path / "figures").mkdir()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "suite": "reference",
                "input_dir": "raw",
                "created_at": "2026-05-07T00:00:00",
                "git_commit": "test",
            }
        ),
        encoding="utf-8",
    )
    with (tmp_path / "rankings.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "rank",
                "model",
                "overall_score",
                "quality_score",
                "speed_score",
                "memory_score",
                "median_real_time_factor",
                "peak_rss_mb",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "rank": 1,
                "model": "waveformer",
                "overall_score": 88,
                "quality_score": 90,
                "speed_score": 80,
                "memory_score": 70,
                "median_real_time_factor": 0.2,
                "peak_rss_mb": 120,
            }
        )
    for name in ("runs.csv", "metrics.csv", "resources.csv", "cases.csv"):
        (tmp_path / name).write_text("", encoding="utf-8")

    result = generate_report(tmp_path, formats=("md", "html"))

    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "report.html").exists()
    assert "report.md" in result["written"][0]
