"""
Baseline selectivity test for CodecSep.

Runs the same DnR test clip through CodecSep with three different SFX
prompts (generic, matching, non-matching) and compares the SFX stem
energy to assess whether the CLAP prompt actually steers separation.

Example:
    python ai/scripts/diagnostics/test_codecsep_selectivity.py ^
        --clip-dir ai/models/CodecSep/codecsep_supplementary_material/codecsep_code/datasets/dnr_v2/tt/10020

    python ai/scripts/diagnostics/test_codecsep_selectivity.py ^
        --clip-dir ai/models/CodecSep/codecsep_supplementary_material/codecsep_code/datasets/dnr_v2/tt/10285 ^
        --matching-prompt "tape ripping, packing tape sounds" ^
        --non-matching-prompt "dog barking, animal"
"""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

import numpy as np
import soundfile as sf

from ai.ai_runtime.separation.codecsep_separator import CodecSepSeparator

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _read_sfx_annotations(clip_dir: Path) -> list[str]:
    """Return FSD50K annotation labels for SFX rows in annots.csv."""
    annots_path = clip_dir / "annots.csv"
    if not annots_path.exists():
        return []
    labels: list[str] = []
    with open(annots_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("class") == "sfx":
                labels.append(row.get("annotation", ""))
    return labels


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))


def _si_sdr(reference: np.ndarray, estimate: np.ndarray) -> float:
    """Scale-Invariant Signal-to-Distortion Ratio in dB."""
    ref = reference.astype(np.float64).ravel()
    est = estimate.astype(np.float64).ravel()
    min_len = min(len(ref), len(est))
    ref, est = ref[:min_len], est[:min_len]
    dot = np.dot(ref, est)
    s_ref = ref * dot / (np.dot(ref, ref) + 1e-12)
    noise = est - s_ref
    return float(10 * np.log10(np.dot(s_ref, s_ref) / (np.dot(noise, noise) + 1e-12)))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test CodecSep SFX-prompt selectivity on a DnR clip.",
    )
    parser.add_argument(
        "--clip-dir", type=Path, required=True,
        help="Path to a DnR test clip directory (e.g. datasets/dnr_v2/tt/10020).",
    )
    parser.add_argument(
        "--matching-prompt", type=str, default=None,
        help="CLAP prompt that matches the SFX content. Auto-derived from annots.csv if omitted.",
    )
    parser.add_argument(
        "--non-matching-prompt", type=str, default="dog barking, animal sounds",
        help="CLAP prompt for a category NOT present in the clip.",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Save separated stems as WAVs (optional).",
    )
    parser.add_argument("--device", type=str, default=None)
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument(
        "--max-length",
        type=float,
        default=10.0,
        help="Maximum seconds to process, matching the vendored single-file demo default.",
    )
    args = parser.parse_args()

    clip_dir = args.clip_dir.resolve()
    mix_path = clip_dir / "mix.wav"
    sfx_ref_path = clip_dir / "sfx.wav"
    if not mix_path.exists():
        raise FileNotFoundError(f"mix.wav not found in {clip_dir}")

    # --- Load audio ---
    mix_audio, sr = sf.read(str(mix_path), dtype="float32", always_2d=False)
    sfx_ref = None
    if sfx_ref_path.exists():
        sfx_ref, _ = sf.read(str(sfx_ref_path), dtype="float32", always_2d=False)

    max_samples = int(args.max_length * sr)
    if max_samples > 0 and mix_audio.shape[0] > max_samples:
        mix_audio = mix_audio[:max_samples] if mix_audio.ndim == 1 else mix_audio[:max_samples, :]
        logger.info("Truncated mix to %.1fs (%d samples)", args.max_length, max_samples)
    if sfx_ref is not None and max_samples > 0 and sfx_ref.shape[0] > max_samples:
        sfx_ref = sfx_ref[:max_samples] if sfx_ref.ndim == 1 else sfx_ref[:max_samples, :]
        logger.info("Truncated sfx reference to %.1fs (%d samples)", args.max_length, max_samples)

    # --- Determine prompts ---
    sfx_labels = _read_sfx_annotations(clip_dir)
    logger.info("SFX annotations: %s", sfx_labels)

    if args.matching_prompt:
        matching = args.matching_prompt
    elif sfx_labels:
        # Use the raw FSD50K labels as a rough matching prompt
        matching = ", ".join(
            lbl.replace("_", " ") for lbl in sfx_labels[0].split(",")[:3]
        )
    else:
        matching = "sound effects"
        logger.warning("No SFX annotations found; matching prompt defaults to generic.")

    generic = "sound effects"
    non_matching = args.non_matching_prompt

    prompts = {
        "generic": generic,
        "matching": matching,
        "non_matching": non_matching,
    }

    logger.info("Prompts:")
    for name, p in prompts.items():
        logger.info("  %-15s: %s", name, p)

    # --- Run CodecSep ---
    separator = CodecSepSeparator(
        checkpoint_path=args.checkpoint,
        device=args.device,
    )

    results: dict[str, np.ndarray] = {}
    for name, prompt in prompts.items():
        logger.info("Running CodecSep with SFX prompt: '%s' ...", prompt)
        stems = separator.separate_stems(
            mix_audio,
            sample_rate=sr,
            stems=("speech", "music", "sfx"),
            prompt_overrides={"sfx": [prompt]},
        )
        results[name] = stems["sfx"]

    # --- Compute metrics ---
    print("\n" + "=" * 70)
    print("SELECTIVITY RESULTS")
    print("=" * 70)
    print(f"Clip:           {clip_dir.name}")
    print(f"SFX labels:     {sfx_labels}")
    print()

    header = f"{'Prompt':<20} {'RMS':>10} {'RMS ratio':>12}"
    if sfx_ref is not None:
        header += f" {'SI-SDR (dB)':>14}"
    print(header)
    print("-" * len(header))

    generic_rms = _rms(results["generic"])

    for name, prompt in prompts.items():
        sfx_out = results[name]
        rms_val = _rms(sfx_out)
        ratio = rms_val / (generic_rms + 1e-12)
        line = f"{name:<20} {rms_val:>10.6f} {ratio:>12.4f}"
        if sfx_ref is not None:
            sisdr = _si_sdr(sfx_ref, sfx_out)
            line += f" {sisdr:>14.2f}"
        print(line)

    print()
    match_rms = _rms(results["matching"])
    nonmatch_rms = _rms(results["non_matching"])
    selectivity_ratio = match_rms / (nonmatch_rms + 1e-12)
    selectivity_db = 20 * np.log10(selectivity_ratio + 1e-12)
    print(f"Selectivity (matching / non-matching RMS ratio): {selectivity_ratio:.4f}")
    print(f"Selectivity (dB):                                {selectivity_db:.2f} dB")
    print()
    if abs(selectivity_db) < 1.0:
        print("VERDICT: Prompt has MINIMAL effect on SFX extraction (~< 1 dB).")
        print("         The model likely ignores the text prompt for SFX.")
    elif selectivity_db > 1.0:
        print(f"VERDICT: Matching prompt extracts MORE energy (+{selectivity_db:.1f} dB).")
        print("         Some prompt sensitivity exists.")
    else:
        print(f"VERDICT: Non-matching prompt extracts MORE energy ({selectivity_db:.1f} dB).")
        print("         Unexpected — may indicate prompt-independent behavior.")

    # --- Save WAVs ---
    if args.output_dir:
        out_dir = args.output_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        clip_name = clip_dir.name
        for name in prompts:
            out_path = out_dir / f"{clip_name}_sfx_{name}.wav"
            sf.write(str(out_path), results[name].astype(np.float32), sr)
            logger.info("Saved: %s", out_path)
        # Also save the speech/music from the last run for reference
        logger.info("WAVs saved to %s", out_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
