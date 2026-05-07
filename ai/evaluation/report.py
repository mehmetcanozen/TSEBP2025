"""Markdown, HTML, and figure generation for evaluation runs."""

from __future__ import annotations

import csv
import html
import json
import math
from pathlib import Path
from typing import Any, Iterable


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _float(value: Any, default: float = float("nan")) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_number(value: Any, digits: int = 2) -> str:
    number = _float(value)
    if math.isnan(number) or math.isinf(number):
        return "-"
    return f"{number:.{digits}f}"


def _markdown_table(rows: list[dict[str, Any]], columns: list[str], limit: int | None = None) -> str:
    selected = rows[:limit] if limit else rows
    if not selected:
        return "_No rows._"
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in selected:
        body.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join([header, divider, *body])


def _html_table(rows: list[dict[str, Any]], columns: list[str], limit: int | None = None) -> str:
    selected = rows[:limit] if limit else rows
    if not selected:
        return "<p><em>No rows.</em></p>"
    head = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body = []
    for row in selected:
        body.append(
            "<tr>"
            + "".join(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns)
            + "</tr>"
        )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _try_generate_figures(run_dir: Path) -> list[Path]:
    figures_dir = run_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    rankings_path = run_dir / "rankings.csv"
    metrics_path = run_dir / "metrics.csv"
    resources_path = run_dir / "resources.csv"

    try:
        import matplotlib.pyplot as plt  # type: ignore
        import pandas as pd  # type: ignore
        import seaborn as sns  # type: ignore
    except Exception:
        return []

    generated: list[Path] = []
    def read_frame(path: Path):
        if not path.exists() or path.stat().st_size == 0:
            return pd.DataFrame()
        try:
            return pd.read_csv(path)
        except Exception:
            return pd.DataFrame()

    rankings = read_frame(rankings_path)
    metrics = read_frame(metrics_path)
    resources = read_frame(resources_path)
    sns.set_theme(style="whitegrid")

    def save_current(name: str) -> None:
        path = figures_dir / name
        plt.tight_layout()
        plt.savefig(path, dpi=150)
        plt.close()
        generated.append(path)

    if not rankings.empty:
        order = rankings.sort_values("overall_score", ascending=False)
        plt.figure(figsize=(10, 5))
        sns.barplot(data=order, x="overall_score", y="model", color="#2b8cbe")
        plt.title("Overall Score")
        plt.xlabel("Score (0-100)")
        plt.ylabel("Model")
        save_current("quality_ranking.png")

        plt.figure(figsize=(10, 5))
        sns.scatterplot(
            data=order,
            x="median_real_time_factor",
            y="quality_score",
            hue="model",
            s=90,
        )
        plt.title("Quality vs Speed")
        plt.xlabel("Median real-time factor (lower is faster)")
        plt.ylabel("Quality score")
        save_current("quality_vs_speed.png")

        plt.figure(figsize=(10, 5))
        sns.scatterplot(data=order, x="peak_rss_mb", y="quality_score", hue="model", s=90)
        plt.title("Quality vs Peak Memory")
        plt.xlabel("Peak RSS MB")
        plt.ylabel("Quality score")
        save_current("quality_vs_memory.png")

        pareto = []
        for _, row in order.iterrows():
            dominated = False
            for _, other in order.iterrows():
                if (
                    other["quality_score"] >= row["quality_score"]
                    and other["median_real_time_factor"] <= row["median_real_time_factor"]
                    and (
                        other["quality_score"] > row["quality_score"]
                        or other["median_real_time_factor"] < row["median_real_time_factor"]
                    )
                ):
                    dominated = True
                    break
            pareto.append(not dominated)
        pareto_df = order.copy()
        pareto_df["pareto"] = pareto
        plt.figure(figsize=(10, 5))
        sns.scatterplot(
            data=pareto_df,
            x="median_real_time_factor",
            y="quality_score",
            hue="pareto",
            style="model",
            s=100,
        )
        plt.title("Pareto Frontier")
        plt.xlabel("Median real-time factor")
        plt.ylabel("Quality score")
        save_current("pareto_frontier.png")

    if not resources.empty:
        plt.figure(figsize=(10, 5))
        sns.barplot(
            data=resources.sort_values("peak_rss_mb", ascending=False),
            x="peak_rss_mb",
            y="model",
            color="#7bccc4",
        )
        plt.title("Peak Worker Memory")
        plt.xlabel("Peak RSS MB")
        plt.ylabel("Model")
        save_current("peak_memory.png")

    if not metrics.empty:
        success = metrics[metrics.get("status") == "success"] if "status" in metrics else metrics
        if not success.empty and "real_time_factor" in success:
            speed = success.groupby("model", as_index=False)["real_time_factor"].median()
            plt.figure(figsize=(10, 5))
            sns.barplot(
                data=speed.sort_values("real_time_factor"),
                x="real_time_factor",
                y="model",
                color="#fdbb84",
            )
            plt.title("Median Real-Time Factor")
            plt.xlabel("RTF (lower is faster)")
            plt.ylabel("Model")
            save_current("speed_rtf.png")

        metric_name = "clean_si_sdr_improvement_db"
        if metric_name in success and not success.empty:
            pivot = success.pivot_table(
                index="model",
                columns="case_id",
                values=metric_name,
                aggfunc="mean",
            )
            if not pivot.empty:
                plt.figure(figsize=(max(8, len(pivot.columns) * 1.4), max(4, len(pivot) * 0.5)))
                sns.heatmap(pivot, annot=True, fmt=".1f", cmap="viridis")
                plt.title("Per-Case Clean SI-SDR Improvement")
                save_current("per_case_metric_heatmap.png")

        if {"model", "case_id", "status"}.issubset(set(metrics.columns)):
            matrix = metrics.assign(failed=metrics["status"] != "success").pivot_table(
                index="model",
                columns="case_id",
                values="failed",
                aggfunc="max",
                fill_value=False,
            )
            if not matrix.empty:
                plt.figure(figsize=(max(8, len(matrix.columns) * 1.2), max(4, len(matrix) * 0.45)))
                sns.heatmap(matrix.astype(int), annot=True, fmt="d", cmap="Reds", cbar=False)
                plt.title("Failure Matrix")
                save_current("failure_matrix.png")

    _try_generate_triptych(run_dir, figures_dir, generated)
    return generated


def _try_generate_triptych(run_dir: Path, figures_dir: Path, generated: list[Path]) -> None:
    try:
        import matplotlib.pyplot as plt  # type: ignore
        import numpy as np
        import soundfile as sf
    except Exception:
        return

    runs = _read_csv(run_dir / "runs.csv")
    candidates = [row for row in runs if row.get("status") == "success" and row.get("clean_path")]
    if not candidates:
        return
    row = candidates[0]
    input_path = ""
    cases = _read_csv(run_dir / "cases.csv")
    for case in cases:
        if case.get("case_id") == row.get("case_id"):
            input_path = case.get("input_path", "")
            break
    paths = [Path(input_path), Path(row["clean_path"]), Path(row["removed_path"])]
    if not all(path.exists() for path in paths):
        return

    labels = ["Input", "Clean output", "Removed output"]
    plt.figure(figsize=(12, 7))
    loaded = []
    for index, (label, path) in enumerate(zip(labels, paths), start=1):
        audio, sample_rate = sf.read(path, dtype="float32")
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)
        loaded.append((label, audio, int(sample_rate), path))
        time_axis = np.arange(len(audio)) / max(float(sample_rate), 1.0)
        ax = plt.subplot(3, 1, index)
        ax.plot(time_axis, audio, linewidth=0.5)
        ax.set_title(f"{label}: {path.name}")
        ax.set_xlabel("Seconds")
        ax.set_ylabel("Amplitude")
    output_path = figures_dir / "waveform_triptych.png"
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    generated.append(output_path)

    plt.figure(figsize=(12, 8))
    for index, (label, audio, sample_rate, path) in enumerate(loaded, start=1):
        ax = plt.subplot(3, 1, index)
        ax.specgram(audio, NFFT=1024, Fs=sample_rate, noverlap=768, cmap="magma")
        ax.set_title(f"{label} spectrogram: {path.name}")
        ax.set_xlabel("Seconds")
        ax.set_ylabel("Hz")
    output_path = figures_dir / "spectrogram_triptych.png"
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    generated.append(output_path)


def generate_report(run_dir: Path, formats: Iterable[str] = ("md", "html")) -> dict[str, Any]:
    """Generate report files and figures for an evaluation run directory."""

    run_dir = Path(run_dir)
    manifest = {}
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    figures = _try_generate_figures(run_dir)
    rankings = _read_csv(run_dir / "rankings.csv")
    resources = _read_csv(run_dir / "resources.csv")
    runs = _read_csv(run_dir / "runs.csv")
    unsupported = [row for row in runs if row.get("status") == "unsupported"]
    failures = [row for row in runs if row.get("status") not in {"success", "unsupported"}]

    ranked_rows = [
        {
            "rank": row.get("rank", ""),
            "model": row.get("model", ""),
            "overall": _format_number(row.get("overall_score")),
            "quality": _format_number(row.get("quality_score")),
            "speed": _format_number(row.get("speed_score")),
            "memory": _format_number(row.get("memory_score")),
            "median_rtf": _format_number(row.get("median_real_time_factor"), 3),
            "peak_rss_mb": _format_number(row.get("peak_rss_mb")),
        }
        for row in rankings
    ]
    resource_rows = [
        {
            "model": row.get("model", ""),
            "load_s": _format_number(row.get("model_load_seconds"), 3),
            "warm_s": _format_number(row.get("warm_inference_seconds"), 3),
            "peak_rss_mb": _format_number(row.get("peak_rss_mb")),
            "cpu_time_s": _format_number(row.get("cpu_time_seconds"), 3),
            "avg_cpu_pct": _format_number(row.get("average_cpu_percent"), 1),
        }
        for row in resources
    ]

    lines = [
        "# TSEBP2025 AI Evaluation Report",
        "",
        f"- Run directory: `{run_dir}`",
        f"- Suite: `{manifest.get('suite', '-')}`",
        f"- Input directory: `{manifest.get('input_dir', '-')}`",
        f"- Created: `{manifest.get('created_at', '-')}`",
        f"- Git commit: `{manifest.get('git_commit', '-')}`",
        "",
        "## Ranking",
        "",
        _markdown_table(
            ranked_rows,
            ["rank", "model", "overall", "quality", "speed", "memory", "median_rtf", "peak_rss_mb"],
        ),
        "",
        "Primary quality ranking uses only reference-tier cases marked for primary ranking. Coverage-tier files are robustness/proxy evidence and are not mixed into the primary quality score.",
        "",
        "## Resource Summary",
        "",
        _markdown_table(
            resource_rows,
            ["model", "load_s", "warm_s", "peak_rss_mb", "cpu_time_s", "avg_cpu_pct"],
        ),
        "",
        "## Unsupported Or Out Of Scope",
        "",
        _markdown_table(unsupported, ["model", "case_id", "status", "error"], limit=50),
        "",
        "## Failures",
        "",
        _markdown_table(failures, ["model", "case_id", "repeat", "status", "error"], limit=50),
        "",
        "## Figures",
        "",
    ]
    if figures:
        for figure in figures:
            lines.append(f"![{figure.stem}](figures/{figure.name})")
    else:
        lines.append("_Figure generation skipped because plotting dependencies were unavailable or no data was present._")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `target_speaker_windows` is listed as available but out of scope for this semantic suppression evaluation.",
            "- Optional PESQ/STOI columns are populated only when their local packages are installed.",
            "- DNSMOS-style no-reference scoring is not run by default because it requires a separately configured model/service.",
        ]
    )

    written: list[str] = []
    formats = set(formats)
    if "md" in formats:
        report_md = run_dir / "report.md"
        report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(str(report_md))
    if "html" in formats:
        report_html = run_dir / "report.html"
        body = "".join(
            [
                "<h1>TSEBP2025 AI Evaluation Report</h1>",
                f"<p><strong>Run directory:</strong> {html.escape(str(run_dir))}</p>",
                f"<p><strong>Suite:</strong> {html.escape(str(manifest.get('suite', '-')))}</p>",
                "<h2>Ranking</h2>",
                _html_table(
                    ranked_rows,
                    [
                        "rank",
                        "model",
                        "overall",
                        "quality",
                        "speed",
                        "memory",
                        "median_rtf",
                        "peak_rss_mb",
                    ],
                ),
                "<h2>Resource Summary</h2>",
                _html_table(resource_rows, ["model", "load_s", "warm_s", "peak_rss_mb", "cpu_time_s", "avg_cpu_pct"]),
                "<h2>Unsupported Or Out Of Scope</h2>",
                _html_table(unsupported, ["model", "case_id", "status", "error"], limit=50),
                "<h2>Failures</h2>",
                _html_table(failures, ["model", "case_id", "repeat", "status", "error"], limit=50),
                "<h2>Figures</h2>",
                "".join(
                    f'<figure><img src="figures/{html.escape(path.name)}" alt="{html.escape(path.stem)}"><figcaption>{html.escape(path.stem)}</figcaption></figure>'
                    for path in figures
                )
                or "<p><em>No figures generated.</em></p>",
            ]
        )
        report_html.write_text(
            "<!doctype html><html><head><meta charset='utf-8'><title>TSEBP2025 AI Evaluation</title>"
            "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:32px;line-height:1.45}"
            "table{border-collapse:collapse;margin:16px 0;width:100%;font-size:14px}"
            "th,td{border:1px solid #ddd;padding:6px;text-align:left}th{background:#f3f5f7}"
            "img{max-width:100%;height:auto}figure{margin:24px 0}</style></head><body>"
            + body
            + "</body></html>",
            encoding="utf-8",
        )
        written.append(str(report_html))
    return {"written": written, "figures": [str(path) for path in figures]}
