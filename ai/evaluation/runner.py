"""Evaluation planning, execution, ranking, and report orchestration."""

from __future__ import annotations

import csv
import importlib.metadata
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from ai.evaluation.cases import build_evaluation_cases
from ai.evaluation.contracts import EvalCase, EvaluationSettings, ModelEvalSpec
from ai.evaluation.models import list_model_specs, resolve_model_specs
from ai.evaluation.report import generate_report
from ai.evaluation.resources import ResourceSummary, monitor_process


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "ai" / "data" / "audio" / "raw"
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "ai" / "data" / "audio" / "processed"


def _now_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _resolve_output_root(output_root: Path | None) -> Path:
    if output_root is not None:
        return Path(output_root).expanduser().resolve()
    return DEFAULT_PROCESSED_DIR / f"evaluation_{_now_slug()}"


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _git_dirty() -> bool | str:
    try:
        output = subprocess.check_output(
            ["git", "status", "--short"],
            cwd=PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return bool(output.strip())
    except Exception:
        return "unknown"


def _dependency_versions() -> dict[str, str]:
    names = [
        "numpy",
        "soundfile",
        "typer",
        "onnxruntime",
        "torch",
        "torchaudio",
        "pandas",
        "matplotlib",
        "seaborn",
        "psutil",
        "scipy",
        "librosa",
        "jinja2",
        "pesq",
        "pystoi",
    ]
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "missing"
    return versions


def _artifact_rows(specs: Iterable[ModelEvalSpec]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in specs:
        if not spec.artifact_paths:
            rows.append(
                {
                    "model": spec.model_id,
                    "path": "",
                    "exists": "",
                    "size_bytes": 0,
                    "status": "no_artifacts_declared",
                }
            )
        for path in spec.artifact_paths:
            rows.append(
                {
                    "model": spec.model_id,
                    "path": str(path),
                    "exists": bool(path.exists()),
                    "size_bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
                    "status": "ok" if path.exists() else "missing",
                }
            )
    return rows


def _model_cards(specs: Iterable[ModelEvalSpec]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for spec in specs:
        artifact_size = sum(
            path.stat().st_size for path in spec.artifact_paths if path.exists() and path.is_file()
        )
        payload = spec.to_json_dict()
        payload["artifact_size_bytes"] = artifact_size
        cards.append(payload)
    return cards


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _write_plan_files(
    *,
    run_dir: Path,
    cases: list[EvalCase],
    specs: list[ModelEvalSpec],
    manifest: dict[str, Any],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "manifest.json", manifest)
    _write_csv(run_dir / "cases.csv", [case.to_row() for case in cases])
    _write_json(run_dir / "model_cards.json", _model_cards(specs))
    _write_csv(run_dir / "artifacts.csv", _artifact_rows(specs))


def _build_manifest(
    *,
    input_dir: Path,
    suite: str,
    models: list[str],
    run_dir: Path,
    settings: EvaluationSettings,
    cases: list[EvalCase],
    specs: list[ModelEvalSpec],
    include_unsupported: bool,
    command: list[str] | None,
) -> dict[str, Any]:
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(PROJECT_ROOT),
        "input_dir": str(input_dir),
        "output_root": str(run_dir),
        "suite": suite,
        "requested_models": models,
        "resolved_models": [spec.model_id for spec in specs],
        "case_count": len(cases),
        "reference_case_count": sum(1 for case in cases if case.tier == "reference"),
        "coverage_case_count": sum(1 for case in cases if case.tier == "coverage"),
        "settings": settings.to_json_dict(),
        "include_unsupported": include_unsupported,
        "git_commit": _git_commit(),
        "git_dirty": _git_dirty(),
        "python": sys.version,
        "python_executable": sys.executable,
        "dependency_versions": _dependency_versions(),
        "command": command or sys.argv,
        "evaluation_policy": {
            "primary_quality": "reference-tier cases with primary_ranking=true",
            "coverage": "reported as robustness/proxy evidence only",
            "target_speaker_windows": "available but out of scope for semantic evaluation",
        },
    }


def _artifact_missing_reason(spec: ModelEvalSpec) -> str:
    missing = [str(path) for path in spec.artifact_paths if not path.exists()]
    if missing:
        return "Missing artifact(s): " + "; ".join(missing)
    return ""


def _unsupported_rows(
    *,
    spec: ModelEvalSpec,
    cases: list[EvalCase],
    reason: str,
    status: str = "unsupported",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    run_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    for case in cases:
        run_rows.append(
            {
                "model": spec.model_id,
                "case_id": case.case_id,
                "tier": case.tier,
                "repeat": 0,
                "status": status,
                "target": case.target_for_surface(spec.target_surface),
                "clean_path": "",
                "removed_path": "",
                "sample_rate": "",
                "duration_seconds": "",
                "end_to_end_seconds": "",
                "error": reason,
            }
        )
        metric_rows.append(
            {
                "model": spec.model_id,
                "case_id": case.case_id,
                "tier": case.tier,
                "primary_ranking": bool(case.primary_ranking),
                "repeat": 0,
                "status": status,
                "target": case.target_for_surface(spec.target_surface),
                "error": reason,
            }
        )
    resource_row = {
        "model": spec.model_id,
        "status": status,
        "model_load_seconds": 0.0,
        "warm_inference_seconds": 0.0,
        "peak_rss_mb": 0.0,
        "average_cpu_percent": 0.0,
        "cpu_time_seconds": 0.0,
        "sample_count": 0,
        "monitor_status": status,
        "artifact_size_bytes": sum(
            path.stat().st_size for path in spec.artifact_paths if path.exists() and path.is_file()
        ),
        "error": reason,
    }
    return run_rows, metric_rows, resource_row


def _numeric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    values = []
    for row in rows:
        try:
            value = float(row.get(key, float("nan")))
        except (TypeError, ValueError):
            value = float("nan")
        if math.isfinite(value):
            values.append(value)
    return values


def _normalize_higher(value: float, values: list[float]) -> float:
    finite = [item for item in values if math.isfinite(item)]
    if not finite or not math.isfinite(value):
        return 0.0
    minimum = min(finite)
    maximum = max(finite)
    if abs(maximum - minimum) < 1.0e-12:
        return 100.0
    return max(0.0, min(100.0, 100.0 * (value - minimum) / (maximum - minimum)))


def _normalize_lower(value: float, values: list[float]) -> float:
    finite = [item for item in values if math.isfinite(item)]
    if not finite or not math.isfinite(value):
        return 0.0
    minimum = min(finite)
    maximum = max(finite)
    if abs(maximum - minimum) < 1.0e-12:
        return 100.0
    return max(0.0, min(100.0, 100.0 * (maximum - value) / (maximum - minimum)))


def build_rankings(
    *,
    metrics_rows: list[dict[str, Any]],
    resources_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build deterministic model rankings from collected metrics and resources."""

    models = sorted({row.get("model", "") for row in metrics_rows if row.get("model")})
    resource_by_model = {row.get("model"): row for row in resources_rows}
    aggregates: list[dict[str, Any]] = []
    for model in models:
        model_metrics = [
            row
            for row in metrics_rows
            if row.get("model") == model
            and row.get("status") == "success"
            and row.get("tier") == "reference"
            and str(row.get("primary_ranking", "")).lower() in {"true", "1"}
        ]
        all_success = [
            row
            for row in metrics_rows
            if row.get("model") == model and row.get("status") == "success"
        ]
        clean_improvements = _numeric_values(model_metrics, "clean_si_sdr_improvement_db")
        removed_scores = _numeric_values(model_metrics, "removed_unwanted_si_sdr_db")
        residual_corr = _numeric_values(model_metrics, "residual_unwanted_correlation")
        clipping = _numeric_values(model_metrics, "clipping_rate")
        rtfs = _numeric_values(all_success, "real_time_factor")
        resource = resource_by_model.get(model, {})
        peak_rss = float(resource.get("peak_rss_mb") or 0.0)
        quality_raw = (
            (sum(clean_improvements) / max(len(clean_improvements), 1) if clean_improvements else float("nan"))
            + 0.5
            * (sum(removed_scores) / max(len(removed_scores), 1) if removed_scores else 0.0)
            - 10.0
            * (sum(abs(item) for item in residual_corr) / max(len(residual_corr), 1) if residual_corr else 0.0)
            - 50.0
            * (sum(clipping) / max(len(clipping), 1) if clipping else 0.0)
        )
        median_rtf = sorted(rtfs)[len(rtfs) // 2] if rtfs else float("nan")
        aggregates.append(
            {
                "model": model,
                "quality_raw": quality_raw,
                "median_real_time_factor": median_rtf,
                "peak_rss_mb": peak_rss,
                "reference_success_rows": len(model_metrics),
                "success_rows": len(all_success),
                "status": "success" if all_success else "no_successful_runs",
            }
        )

    quality_values = [float(row["quality_raw"]) for row in aggregates]
    speed_values = [float(row["median_real_time_factor"]) for row in aggregates]
    memory_values = [float(row["peak_rss_mb"]) for row in aggregates if float(row["peak_rss_mb"]) > 0.0]
    for row in aggregates:
        row["quality_score"] = _normalize_higher(float(row["quality_raw"]), quality_values)
        row["speed_score"] = _normalize_lower(float(row["median_real_time_factor"]), speed_values)
        row["memory_score"] = _normalize_lower(
            float(row["peak_rss_mb"]),
            memory_values,
        )
        row["overall_score"] = (
            0.60 * float(row["quality_score"])
            + 0.25 * float(row["speed_score"])
            + 0.15 * float(row["memory_score"])
        )

    aggregates.sort(key=lambda row: (-float(row["overall_score"]), row["model"]))
    for index, row in enumerate(aggregates, start=1):
        row["rank"] = index
    return aggregates


def plan_evaluation(
    *,
    input_dir: Path = DEFAULT_INPUT_DIR,
    suite: str = "full",
    models: list[str] | None = None,
    output_root: Path | None = None,
    max_cases: int | None = None,
    include_unsupported: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    selected_models = models or ["auto"]
    run_dir = _resolve_output_root(output_root)
    cases = build_evaluation_cases(input_dir=input_dir, suite=suite, max_cases=max_cases)
    specs = resolve_model_specs(selected_models, include_unsupported=include_unsupported)
    settings = EvaluationSettings()
    manifest = _build_manifest(
        input_dir=input_dir,
        suite=suite,
        models=selected_models,
        run_dir=run_dir,
        settings=settings,
        cases=cases,
        specs=specs,
        include_unsupported=include_unsupported,
        command=sys.argv,
    )
    if not dry_run:
        _write_plan_files(run_dir=run_dir, cases=cases, specs=specs, manifest=manifest)
    return {
        "run_dir": str(run_dir),
        "case_count": len(cases),
        "models": [spec.model_id for spec in specs],
        "dry_run": dry_run,
    }


def run_evaluation(
    *,
    input_dir: Path = DEFAULT_INPUT_DIR,
    suite: str = "full",
    models: list[str] | None = None,
    output_root: Path | None = None,
    max_cases: int | None = None,
    repeats: int = 1,
    warmup_runs: int = 1,
    include_unsupported: bool = True,
    save_audio: bool = True,
    report_formats: Iterable[str] = ("md", "html"),
    monitor_interval_seconds: float = 0.25,
) -> dict[str, Any]:
    selected_models = models or ["auto"]
    run_dir = _resolve_output_root(output_root)
    cases = build_evaluation_cases(input_dir=input_dir, suite=suite, max_cases=max_cases)
    specs = resolve_model_specs(selected_models, include_unsupported=include_unsupported)
    settings = EvaluationSettings(
        repeats=max(1, int(repeats)),
        warmup_runs=max(0, int(warmup_runs)),
        save_audio=bool(save_audio),
    )
    manifest = _build_manifest(
        input_dir=input_dir,
        suite=suite,
        models=selected_models,
        run_dir=run_dir,
        settings=settings,
        cases=cases,
        specs=specs,
        include_unsupported=include_unsupported,
        command=sys.argv,
    )
    _write_plan_files(run_dir=run_dir, cases=cases, specs=specs, manifest=manifest)

    runs: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    worker_dir = run_dir / "workers"
    worker_dir.mkdir(parents=True, exist_ok=True)

    for spec in specs:
        missing_reason = _artifact_missing_reason(spec)
        if not spec.runnable or missing_reason:
            reason = spec.unsupported_reason or missing_reason
            status = "unsupported" if not spec.runnable else "missing_artifact"
            run_rows, metric_rows, resource_row = _unsupported_rows(
                spec=spec,
                cases=cases,
                reason=reason,
                status=status,
            )
            runs.extend(run_rows)
            metrics.extend(metric_rows)
            resources.append(resource_row)
            continue

        model_dir = run_dir / "outputs" / spec.model_id
        payload_path = worker_dir / f"{spec.model_id}.payload.json"
        result_path = worker_dir / f"{spec.model_id}.result.json"
        stdout_path = worker_dir / f"{spec.model_id}.stdout.log"
        stderr_path = worker_dir / f"{spec.model_id}.stderr.log"
        payload = {
            "model": spec.to_json_dict(),
            "settings": settings.to_json_dict(),
            "cases": [case.to_json_dict() for case in cases],
            "output_dir": str(model_dir),
            "result_path": str(result_path),
        }
        _write_json(payload_path, payload)
        with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr_handle:
            process = subprocess.Popen(
                [sys.executable, "-m", "ai.evaluation.worker", "--payload", str(payload_path)],
                cwd=PROJECT_ROOT,
                stdout=stdout_handle,
                stderr=stderr_handle,
            )
            resource_summary = monitor_process(process, interval_seconds=monitor_interval_seconds)

        worker_payload: dict[str, Any]
        if result_path.exists():
            worker_payload = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            worker_payload = {
                "model": spec.model_id,
                "status": "failed",
                "error": "Worker exited without result payload.",
                "runs": [],
                "metrics": [],
                "load_seconds": 0.0,
                "warm_inference_seconds": 0.0,
            }

        runs.extend(worker_payload.get("runs", []))
        metrics.extend(worker_payload.get("metrics", []))
        if worker_payload.get("status") != "completed":
            error = worker_payload.get("error", "worker failed")
            run_rows, metric_rows, _ = _unsupported_rows(
                spec=spec,
                cases=cases,
                reason=error,
                status="failed",
            )
            existing = {(row.get("case_id"), row.get("repeat")) for row in worker_payload.get("runs", [])}
            runs.extend(row for row in run_rows if (row.get("case_id"), row.get("repeat")) not in existing)
            metrics.extend(metric_rows)

        artifact_size = sum(
            path.stat().st_size for path in spec.artifact_paths if path.exists() and path.is_file()
        )
        resource_row = {
            "model": spec.model_id,
            "status": worker_payload.get("status", "failed"),
            "model_load_seconds": worker_payload.get("load_seconds", 0.0),
            "warm_inference_seconds": worker_payload.get("warm_inference_seconds", 0.0),
            "artifact_size_bytes": artifact_size,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
            "error": worker_payload.get("error", ""),
        }
        resource_row.update(resource_summary.to_row())
        resources.append(resource_row)

    rankings = build_rankings(metrics_rows=metrics, resources_rows=resources)
    _write_csv(run_dir / "runs.csv", runs)
    _write_csv(run_dir / "metrics.csv", metrics)
    _write_csv(run_dir / "resources.csv", resources)
    _write_csv(run_dir / "rankings.csv", rankings)
    report_result: dict[str, Any] = {"written": [], "figures": []}
    selected_formats = {item for item in report_formats if item in {"md", "html"}}
    if selected_formats:
        report_result = generate_report(run_dir, selected_formats)
    return {
        "run_dir": str(run_dir),
        "case_count": len(cases),
        "models": [spec.model_id for spec in specs],
        "runs": len(runs),
        "metrics": len(metrics),
        "reports": report_result,
    }


def regenerate_report(run_dir: Path, report_formats: Iterable[str] = ("md", "html")) -> dict[str, Any]:
    return generate_report(Path(run_dir), report_formats)


def available_models() -> list[dict[str, Any]]:
    return _model_cards(list_model_specs())
