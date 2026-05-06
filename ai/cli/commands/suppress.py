"""File suppression commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import soundfile as sf
import typer

from ai.ai_runtime.batch.batch_processor import BatchProcessor
from ai.ai_runtime.batch.waveformer_onnx_processor import WaveformerOnnxBatchProcessor
from ai.ai_runtime.contracts import BackendId
from ai.ai_runtime.suppression import SemanticSuppressor
from ai.ai_runtime.utils.target_speaker import DEFAULT_TARGET_SPEAKER_ENGINE

app = typer.Typer(no_args_is_help=True)


def _split_values(values: list[str] | None) -> list[str]:
    targets: list[str] = []
    for value in values or []:
        for part in str(value).split(","):
            cleaned = part.strip()
            if cleaned:
                targets.append(cleaned)
    return targets


def _noise_path(output: Path) -> Path:
    return output.with_name(f"{output.stem}_noise{output.suffix or '.wav'}")


@app.command("file")
def suppress_file(
    input_path: Annotated[Path, typer.Option("--input", "-i", help="Input WAV/FLAC/etc.")],
    output_path: Annotated[Path, typer.Option("--output", "-o", help="Cleaned output WAV path.")],
    target: Annotated[
        list[str] | None,
        typer.Option("--target", "-t", help="Category or prompt to suppress. Repeat or comma-separate."),
    ] = None,
    backend: Annotated[
        BackendId,
        typer.Option("--backend", "-b", help="Runtime backend to use."),
    ] = BackendId.WAVEFORMER,
    aggressiveness: Annotated[
        float,
        typer.Option("--aggressiveness", "-a", min=0.0, help="Suppression strength."),
    ] = 1.5,
    threshold: Annotated[
        float,
        typer.Option("--threshold", min=0.0, max=1.0, help="Detection confidence threshold."),
    ] = 0.5,
    chunk_size: Annotated[
        float,
        typer.Option("--chunk-size", min=0.01, help="Outer batch chunk size in seconds."),
    ] = 10.0,
    output_noise: Annotated[
        bool,
        typer.Option("--output-noise", help="Also save removed/noise estimate next to output."),
    ] = False,
    suppress_all: Annotated[
        bool,
        typer.Option("--suppress-all", help="Use suppress-all speech enhancement path."),
    ] = False,
    universal: Annotated[
        list[str] | None,
        typer.Option("--universal", "-u", help="Open-vocabulary prompts. Repeat or comma-separate."),
    ] = None,
    masking_method: Annotated[
        str,
        typer.Option("--masking-method", help="Masking method for supported backends."),
    ] = "wiener_dd",
    codecsep15_runtime: Annotated[
        str,
        typer.Option("--codecsep15-runtime", help="Runtime for codecsep_dnrv2_15cat."),
    ] = "onnx",
    device: Annotated[
        str | None,
        typer.Option("--device", help="Optional backend device hint, e.g. cpu, cuda, cuda:0."),
    ] = None,
) -> None:
    """Suppress one or more semantic targets from an audio file."""

    targets = _split_values(target)
    universal_prompts = _split_values(universal)
    if backend == BackendId.TARGET_SPEAKER:
        raise typer.BadParameter(
            "Use `tsebp-ai suppress target-speaker` when backend is target_speaker.",
            param_hint="--backend",
        )
    if not targets and not universal_prompts and not suppress_all:
        raise typer.BadParameter(
            "Provide --target, --universal, or --suppress-all.",
            param_hint="--target",
        )

    if backend == BackendId.WAVEFORMER and targets and not universal_prompts and not suppress_all:
        processor = WaveformerOnnxBatchProcessor()
    else:
        suppressor = SemanticSuppressor(
            separator_backend=backend.value,
            masking_method=masking_method,
            audiosep_hive15cat_device=device,
            codecsep_dnrv2_15cat_runtime=codecsep15_runtime,
            codecsep_dnrv2_15cat_device=device,
        )
        processor = BatchProcessor(suppressor=suppressor)
    stats = processor.process_file(
        input_path=input_path,
        output_path=output_path,
        suppress_categories=targets,
        chunk_size_seconds=chunk_size,
        detection_threshold=threshold,
        aggressiveness=aggressiveness,
        suppress_all=suppress_all,
        universal_prompts=universal_prompts,
        output_noise=output_noise,
        audiosep_hive15cat_device=device,
        codecsep_dnrv2_15cat_runtime=codecsep15_runtime,
        codecsep_dnrv2_15cat_device=device,
    )

    typer.echo(f"Saved cleaned audio: {stats['output_file']}")
    if output_noise and stats.get("noise_audio") is not None:
        noise_path = _noise_path(output_path)
        sf.write(noise_path, stats["noise_audio"], int(stats["sample_rate"]))
        typer.echo(f"Saved removed audio: {noise_path}")
    typer.echo(f"Duration: {stats['duration_seconds']:.2f}s")
    typer.echo(f"RMS reduction: {stats['rms_reduction_db']:.2f} dB")


@app.command("target-speaker")
def suppress_target_speaker(
    input_path: Annotated[Path, typer.Option("--input", "-i", help="Input WAV/FLAC/etc.")],
    output_path: Annotated[Path, typer.Option("--output", "-o", help="Cleaned output WAV path.")],
    reference: Annotated[Path, typer.Option("--reference", "-r", help="Reference speaker clip.")],
    engine: Annotated[
        str,
        typer.Option("--engine", help="Target-speaker engine, e.g. tsextract_onnx or clearvoice."),
    ] = DEFAULT_TARGET_SPEAKER_ENGINE,
    device: Annotated[
        str | None,
        typer.Option("--device", help="Optional execution hint, e.g. cpu, cuda, cuda:0."),
    ] = None,
    reconstruction: Annotated[
        str,
        typer.Option("--reconstruction", help="direct_subtract or spectral_mask."),
    ] = "direct_subtract",
    scale: Annotated[
        float,
        typer.Option("--scale", min=0.0, help="Gain applied to selected-speaker estimate before removal."),
    ] = 1.0,
    chunk_size: Annotated[
        float,
        typer.Option("--chunk-size", min=0.01, help="Outer batch chunk size in seconds."),
    ] = 10.0,
    output_noise: Annotated[
        bool,
        typer.Option("--output-noise", help="Also save removed speaker estimate next to output."),
    ] = False,
) -> None:
    """Suppress the speaker matching a reference clip."""

    suppressor = SemanticSuppressor(
        separator_backend=BackendId.TARGET_SPEAKER.value,
        target_speaker_device=device,
        target_speaker_engine=engine,
    )
    processor = BatchProcessor(suppressor=suppressor)
    stats = processor.process_file(
        input_path=input_path,
        output_path=output_path,
        suppress_categories=[],
        chunk_size_seconds=chunk_size,
        output_noise=output_noise,
        target_speaker_reference_path=str(reference),
        target_speaker_device=device,
        target_speaker_engine=engine,
        target_speaker_reconstruction=reconstruction,
        target_speaker_scale=scale,
    )
    typer.echo(f"Saved cleaned audio: {stats['output_file']}")
    if output_noise and stats.get("noise_audio") is not None:
        noise_path = _noise_path(output_path)
        sf.write(noise_path, stats["noise_audio"], int(stats["sample_rate"]))
        typer.echo(f"Saved removed audio: {noise_path}")
    typer.echo(f"Duration: {stats['duration_seconds']:.2f}s")
    typer.echo(f"RMS reduction: {stats['rms_reduction_db']:.2f} dB")
