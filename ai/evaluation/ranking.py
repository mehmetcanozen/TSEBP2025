"""Ranking and summary scoring for evaluation results."""

from __future__ import annotations

from typing import Any


def _to_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    values = [value for value in values if value is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _normalize(values: dict[str, float | None], *, higher_is_better: bool = True) -> dict[str, float]:
    present = {key: value for key, value in values.items() if value is not None}
    if not present:
        return {key: 0.0 for key in values}
    min_value = min(present.values())
    max_value = max(present.values())
    if abs(max_value - min_value) < 1.0e-12:
        return {key: 100.0 if key in present else 0.0 for key in values}
    scores = {}
    for key, value in values.items():
        if value is None:
            scores[key] = 0.0
            continue
        raw = (value - min_value) / (max_value - min_value)
        if not higher_is_better:
            raw = 1.0 - raw
        scores[key] = 100.0 * raw
    return scores


def build_rankings(
    *,
    metrics_rows: list[dict[str, Any]],
    run_rows: list[dict[str, Any]],
    resource_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build model-level rankings from raw metric/run/resource rows."""

    model_ids = sorted({row.get("model_id", "") for row in run_rows if row.get("model_id")})
    reference_metrics = [
        row
        for row in metrics_rows
        if row.get("tier") == "reference"
        and str(row.get("primary_ranking", "")).casefold() == "true"
    ]

    quality_raw: dict[str, float | None] = {}
    speed_raw: dict[str, float | None] = {}
    memory_raw: dict[str, float | None] = {}

    for model_id in model_ids:
        model_metrics = [row for row in reference_metrics if row.get("model_id") == model_id]
        quality_components: list[float] = []
        for row in model_metrics:
            for key in ("clean_si_sdr_improvement_db", "unwanted_si_sdr_db"):
                value = _to_float(row.get(key))
                if value is not None:
                    quality_components.append(value)
            clip = _to_float(row.get("clip_fraction_cleaned"))
            if clip is not None:
                quality_components.append(-25.0 * clip)
        quality_raw[model_id] = _mean(quality_components)

        model_runs = [row for row in run_rows if row.get("model_id") == model_id and row.get("status") == "ok"]
        speed_raw[model_id] = _mean(
            [
                value
                for value in (_to_float(row.get("real_time_factor")) for row in model_runs)
                if value is not None
            ]
        )

        model_resources = [row for row in resource_rows if row.get("model_id") == model_id]
        memory_raw[model_id] = max(
            [
                value
                for value in (_to_float(row.get("peak_rss_mb")) for row in model_resources)
                if value is not None
            ],
            default=None,
        )

    quality_scores = _normalize(quality_raw, higher_is_better=True)
    speed_scores = _normalize(speed_raw, higher_is_better=False)
    memory_scores = _normalize(memory_raw, higher_is_better=False)

    rows: list[dict[str, Any]] = []
    for model_id in model_ids:
        ok_runs = [
            row for row in run_rows if row.get("model_id") == model_id and row.get("status") == "ok"
        ]
        failed_runs = [
            row
            for row in run_rows
            if row.get("model_id") == model_id and row.get("status") not in {"ok", "warmup"}
        ]
        overall = (
            0.60 * quality_scores.get(model_id, 0.0)
            + 0.25 * speed_scores.get(model_id, 0.0)
            + 0.15 * memory_scores.get(model_id, 0.0)
        )
        rows.append(
            {
                "model_id": model_id,
                "overall_score": overall,
                "quality_score": quality_scores.get(model_id, 0.0),
                "speed_score": speed_scores.get(model_id, 0.0),
                "memory_score": memory_scores.get(model_id, 0.0),
                "quality_raw": "" if quality_raw[model_id] is None else quality_raw[model_id],
                "mean_real_time_factor": "" if speed_raw[model_id] is None else speed_raw[model_id],
                "peak_rss_mb": "" if memory_raw[model_id] is None else memory_raw[model_id],
                "ok_runs": len(ok_runs),
                "failed_or_unsupported_runs": len(failed_runs),
            }
        )
    return sorted(rows, key=lambda row: float(row["overall_score"]), reverse=True)
