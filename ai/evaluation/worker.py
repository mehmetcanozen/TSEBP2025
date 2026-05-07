"""Isolated per-model evaluation worker."""

from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path
from typing import Any

from ai.evaluation.adapters import build_adapter
from ai.evaluation.contracts import EvalCase, EvaluationSettings, ModelEvalSpec
from ai.evaluation.metrics import compute_case_metrics


def _case_output_dir(base_dir: Path, case: EvalCase, repeat_index: int, repeats: int) -> Path:
    if repeats <= 1:
        return base_dir / "outputs" / case.case_id
    return base_dir / "outputs" / case.case_id / f"repeat_{repeat_index}"


def _delete_audio_outputs(paths: list[Path]) -> None:
    for path in paths:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass


def _failed_metric_row(
    *,
    spec: ModelEvalSpec,
    case: EvalCase,
    repeat_index: int,
    end_to_end_seconds: float,
    error: str,
) -> dict[str, Any]:
    return {
        "model": spec.model_id,
        "case_id": case.case_id,
        "tier": case.tier,
        "primary_ranking": bool(case.primary_ranking),
        "repeat": int(repeat_index),
        "status": "failed",
        "target": case.target_for_surface(spec.target_surface),
        "duration_seconds": "",
        "end_to_end_seconds": float(end_to_end_seconds),
        "real_time_factor": "",
        "error": error,
    }


def run_worker(payload_path: Path) -> int:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    spec = ModelEvalSpec.from_json_dict(payload["model"])
    settings = EvaluationSettings.from_json_dict(payload["settings"])
    cases = [EvalCase.from_json_dict(item) for item in payload["cases"]]
    output_dir = Path(payload["output_dir"])
    result_path = Path(payload["result_path"])
    result_path.parent.mkdir(parents=True, exist_ok=True)

    runs: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    load_seconds = 0.0
    warm_inference_seconds = 0.0

    try:
        adapter = build_adapter(spec, settings)
        start = time.perf_counter()
        load_metadata = adapter.load()
        load_seconds = time.perf_counter() - start

        if cases and settings.warmup_runs > 0:
            warm_case = cases[0]
            for warm_index in range(1, settings.warmup_runs + 1):
                warm_dir = output_dir / "_warmup" / warm_case.case_id / f"warmup_{warm_index}"
                start = time.perf_counter()
                warm_result = adapter.process(warm_case, warm_dir, warm_index)
                warm_inference_seconds += time.perf_counter() - start
                _delete_audio_outputs([warm_result.clean_path, warm_result.removed_path])

        for case in cases:
            for repeat_index in range(1, settings.repeats + 1):
                case_dir = _case_output_dir(output_dir, case, repeat_index, settings.repeats)
                start = time.perf_counter()
                try:
                    adapter_result = adapter.process(case, case_dir, repeat_index)
                    end_to_end_seconds = time.perf_counter() - start
                    run_row = {
                        "model": spec.model_id,
                        "case_id": case.case_id,
                        "tier": case.tier,
                        "repeat": repeat_index,
                        "status": "success",
                        "target": adapter_result.metadata.get("target", ""),
                        "clean_path": str(adapter_result.clean_path),
                        "removed_path": str(adapter_result.removed_path),
                        "sample_rate": adapter_result.sample_rate,
                        "duration_seconds": adapter_result.duration_seconds,
                        "end_to_end_seconds": end_to_end_seconds,
                        "error": "",
                    }
                    run_row.update(
                        {
                            f"adapter_{key}": value
                            for key, value in adapter_result.metadata.items()
                            if isinstance(value, (str, int, float, bool))
                        }
                    )
                    runs.append(run_row)
                    metrics.append(
                        compute_case_metrics(
                            case=case,
                            result=adapter_result,
                            model_id=spec.model_id,
                            repeat_index=repeat_index,
                            end_to_end_seconds=end_to_end_seconds,
                            status="success",
                        )
                    )
                    if not settings.save_audio:
                        _delete_audio_outputs([adapter_result.clean_path, adapter_result.removed_path])
                except Exception as exc:
                    end_to_end_seconds = time.perf_counter() - start
                    error = f"{type(exc).__name__}: {exc}"
                    runs.append(
                        {
                            "model": spec.model_id,
                            "case_id": case.case_id,
                            "tier": case.tier,
                            "repeat": repeat_index,
                            "status": "failed",
                            "target": case.target_for_surface(spec.target_surface),
                            "clean_path": "",
                            "removed_path": "",
                            "sample_rate": "",
                            "duration_seconds": "",
                            "end_to_end_seconds": end_to_end_seconds,
                            "error": error,
                        }
                    )
                    metrics.append(
                        _failed_metric_row(
                            spec=spec,
                            case=case,
                            repeat_index=repeat_index,
                            end_to_end_seconds=end_to_end_seconds,
                            error=error,
                        )
                    )
        adapter.close()
        payload_out = {
            "model": spec.model_id,
            "status": "completed",
            "load_seconds": load_seconds,
            "warm_inference_seconds": warm_inference_seconds,
            "load_metadata": load_metadata,
            "runs": runs,
            "metrics": metrics,
        }
        result_path.write_text(json.dumps(payload_out, indent=2, default=str), encoding="utf-8")
        return 0
    except Exception as exc:
        payload_out = {
            "model": spec.model_id,
            "status": "failed",
            "load_seconds": load_seconds,
            "warm_inference_seconds": warm_inference_seconds,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "runs": runs,
            "metrics": metrics,
        }
        result_path.write_text(json.dumps(payload_out, indent=2, default=str), encoding="utf-8")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TSEBP2025 per-model evaluation worker")
    parser.add_argument("--payload", required=True, type=Path)
    args = parser.parse_args(argv)
    return run_worker(args.payload)


if __name__ == "__main__":
    raise SystemExit(main())
