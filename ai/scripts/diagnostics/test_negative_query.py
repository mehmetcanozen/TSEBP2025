"""
Negative query selectivity test for CodecSep.

Tests whether applying negative query embedding arithmetic improves
prompt selectivity on the current checkpoint. Compares:
  1. Standard prompts (baseline)
  2. Negative query augmented prompts (e_combined = (1+a)·e_target - a·e_negative)

Example:
    python ai/scripts/diagnostics/test_negative_query.py ^
        --input ai/data/audio/raw/speech_barking.wav

    python ai/scripts/diagnostics/test_negative_query.py ^
        --input ai/data/audio/raw/speech_barking_keyboard.wav ^
        --output-dir ai/data/audio/processed/negative_query_test
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torch.nn.functional as F

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---- Test scenarios ----

SCENARIOS = [
    {
        "name": "typing_vs_barking",
        "target": {
            "prompt": ["keyboard typing, key clicks, typing sounds"],
            "negative": ["dog barking, animal sounds, pets"],
        },
        "contrast": {
            "prompt": ["dog barking, animal sounds, domestic pets"],
            "negative": ["keyboard typing, key clicks, mechanical sounds"],
        },
    },
    {
        "name": "barking_vs_typing",
        "target": {
            "prompt": ["dog barking, animal sounds, domestic pets"],
            "negative": ["keyboard typing, key clicks, mechanical sounds"],
        },
        "contrast": {
            "prompt": ["keyboard typing, key clicks, typing sounds"],
            "negative": ["dog barking, animal sounds, pets"],
        },
    },
    {
        "name": "traffic_vs_speech",
        "target": {
            "prompt": ["traffic noise, car engine, vehicle sounds"],
            "negative": ["speech, human voice, talking, conversation"],
        },
        "contrast": {
            "prompt": ["speech, human voice, talking, conversation"],
            "negative": ["traffic noise, car engine, vehicle sounds"],
        },
    },
    {
        "name": "siren_vs_generic",
        "target": {
            "prompt": ["ambulance siren, emergency vehicle, wailing siren"],
            "negative": ["speech, music, background noise"],
        },
        "contrast": {
            "prompt": ["sound effects, environmental sounds, noise"],
            "negative": ["ambulance siren, emergency vehicle"],
        },
    },
]


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))


def _si_sdr(reference: np.ndarray, estimate: np.ndarray) -> float:
    ref = reference.astype(np.float64).ravel()
    est = estimate.astype(np.float64).ravel()
    min_len = min(len(ref), len(est))
    ref, est = ref[:min_len], est[:min_len]
    dot = np.dot(ref, est)
    s_ref = ref * dot / (np.dot(ref, ref) + 1e-12)
    noise = est - s_ref
    return float(10 * np.log10(np.dot(s_ref, s_ref) / (np.dot(noise, noise) + 1e-12)))


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """1 - cosine_similarity. Higher = more different."""
    a_flat = a.astype(np.float64).ravel()
    b_flat = b.astype(np.float64).ravel()
    min_len = min(len(a_flat), len(b_flat))
    a_flat, b_flat = a_flat[:min_len], b_flat[:min_len]
    dot = np.dot(a_flat, b_flat)
    norm = np.sqrt(np.dot(a_flat, a_flat) * np.dot(b_flat, b_flat)) + 1e-12
    return 1.0 - dot / norm


def run_separation(separator, audio: np.ndarray, sr: int,
                   sfx_prompt: list[str]) -> np.ndarray:
    """Run CodecSep with a specific SFX prompt, return the SFX stem."""
    stems = separator.separate_stems(
        audio, sample_rate=sr,
        stems=("speech", "music", "sfx"),
        prompt_overrides={"sfx": sfx_prompt},
    )
    return stems["sfx"]


def run_separation_with_negative(separator, audio: np.ndarray, sr: int,
                                  target_prompts: list[str],
                                  negative_prompts: list[str],
                                  alpha: float = 0.3) -> np.ndarray:
    """Run CodecSep with negative query embedding arithmetic on the SFX stem."""
    separator._lazy_load_model()
    model = separator._model

    # Compute target embedding
    e_target = model.text_encoder.get_text_embedding(
        target_prompts, use_tensor=True,
    ).detach()
    if e_target.ndim == 2 and e_target.shape[0] > 1:
        e_target = e_target.mean(dim=0, keepdim=True)

    # Compute negative embedding
    e_negative = model.text_encoder.get_text_embedding(
        negative_prompts, use_tensor=True,
    ).detach()
    if e_negative.ndim == 2 and e_negative.shape[0] > 1:
        e_negative = e_negative.mean(dim=0, keepdim=True)

    # Apply the formula: e = (1 + a) * e_target - a * e_negative
    e_combined = (1.0 + alpha) * e_target - alpha * e_negative
    e_combined = F.normalize(e_combined.float(), p=2, dim=-1)

    # Run model with embedding override on the SFX slot
    stems = separator.separate_stems(
        audio, sample_rate=sr,
        stems=("speech", "music", "sfx"),
        prompt_overrides={"sfx": target_prompts},  # text prompt for non-overridden path
    )
    # Now run again with actual embedding override
    tensor, restore_gain = separator._prepare_input(audio, sr)
    raw_output, normalized, track_order = separator._run_normalized_model(
        tensor,
        prompt_overrides=None,
        embedding_overrides={"sfx": e_combined},
        restore_gain=restore_gain,
    )
    sfx_idx = track_order.index("sfx")
    sfx_audio = separator._resample_back(normalized[:, sfx_idx, :], sr)
    return separator._to_numpy(sfx_audio, audio)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test negative query selectivity on CodecSep.",
    )
    parser.add_argument(
        "--input", type=Path, required=True,
        help="Input audio file (WAV).",
    )
    parser.add_argument(
        "--checkpoint", type=Path, default=None,
        help="CodecSep checkpoint path (run dir or ckpt dir).",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Save separated stems as WAVs (optional).",
    )
    parser.add_argument("--device", type=str, default=None)
    parser.add_argument(
        "--max-length", type=float, default=10.0,
        help="Maximum seconds to process.",
    )
    parser.add_argument(
        "--alphas", type=str, default="0.0,0.2,0.3,0.4,0.5",
        help="Comma-separated alpha values to test.",
    )
    args = parser.parse_args()

    alphas = [float(a) for a in args.alphas.split(",")]

    # Load audio
    audio, sr = sf.read(str(args.input.resolve()), dtype="float32", always_2d=False)
    max_samples = int(args.max_length * sr)
    if max_samples > 0 and audio.shape[0] > max_samples:
        audio = audio[:max_samples]
        logger.info("Truncated to %.1fs (%d samples)", args.max_length, max_samples)

    # Load separator
    from ai.ai_runtime.separation.codecsep_separator import CodecSepSeparator
    separator = CodecSepSeparator(
        checkpoint_path=args.checkpoint,
        device=args.device,
    )

    print()
    print("=" * 80)
    print("NEGATIVE QUERY SELECTIVITY TEST")
    print("=" * 80)
    print(f"Input:      {args.input.name}")
    print(f"Checkpoint: {args.checkpoint or 'default'}")
    print(f"Duration:   {len(audio) / sr:.1f}s")
    print(f"Alphas:     {alphas}")
    print()

    for scenario in SCENARIOS:
        print("-" * 80)
        print(f"Scenario: {scenario['name']}")
        print(f"  Target prompt:   {scenario['target']['prompt']}")
        print(f"  Negative prompt: {scenario['target']['negative']}")
        print(f"  Contrast prompt: {scenario['contrast']['prompt']}")
        print()

        # --- Standard (no negative) ---
        sfx_target_std = run_separation(
            separator, audio, sr, scenario["target"]["prompt"],
        )
        sfx_contrast_std = run_separation(
            separator, audio, sr, scenario["contrast"]["prompt"],
        )

        rms_target_std = _rms(sfx_target_std)
        rms_contrast_std = _rms(sfx_contrast_std)
        cosine_dist_std = _cosine_distance(sfx_target_std, sfx_contrast_std)
        selectivity_std = 20 * np.log10(rms_target_std / (rms_contrast_std + 1e-12) + 1e-12)

        print(f"  {'Method':<25} {'Target RMS':>12} {'Contrast RMS':>14} {'Select.(dB)':>12} {'Cosine Dist':>12}")
        print(f"  {'-'*75}")
        print(f"  {'Standard (a=0.0)':<25} {rms_target_std:>12.6f} {rms_contrast_std:>14.6f} {selectivity_std:>12.2f} {cosine_dist_std:>12.6f}")

        # --- With negative query at various alphas ---
        for alpha in alphas:
            if alpha == 0.0:
                continue  # Already shown as standard

            sfx_target_neg = run_separation_with_negative(
                separator, audio, sr,
                scenario["target"]["prompt"],
                scenario["target"]["negative"],
                alpha=alpha,
            )
            sfx_contrast_neg = run_separation_with_negative(
                separator, audio, sr,
                scenario["contrast"]["prompt"],
                scenario["contrast"]["negative"],
                alpha=alpha,
            )

            rms_target_neg = _rms(sfx_target_neg)
            rms_contrast_neg = _rms(sfx_contrast_neg)
            cosine_dist_neg = _cosine_distance(sfx_target_neg, sfx_contrast_neg)
            selectivity_neg = 20 * np.log10(rms_target_neg / (rms_contrast_neg + 1e-12) + 1e-12)

            label = f"Negative (a={alpha:.1f})"
            print(f"  {label:<25} {rms_target_neg:>12.6f} {rms_contrast_neg:>14.6f} {selectivity_neg:>12.2f} {cosine_dist_neg:>12.6f}")

            # Save WAVs
            if args.output_dir:
                out_dir = args.output_dir.resolve()
                out_dir.mkdir(parents=True, exist_ok=True)
                stem_name = args.input.stem
                sf.write(
                    str(out_dir / f"{stem_name}_{scenario['name']}_target_alpha{alpha:.1f}.wav"),
                    sfx_target_neg.astype(np.float32), sr,
                )
                sf.write(
                    str(out_dir / f"{stem_name}_{scenario['name']}_contrast_alpha{alpha:.1f}.wav"),
                    sfx_contrast_neg.astype(np.float32), sr,
                )

        print()

    # --- Save standard outputs too ---
    if args.output_dir:
        out_dir = args.output_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        stem_name = args.input.stem
        for scenario in SCENARIOS:
            sfx_t = run_separation(separator, audio, sr, scenario["target"]["prompt"])
            sfx_c = run_separation(separator, audio, sr, scenario["contrast"]["prompt"])
            sf.write(str(out_dir / f"{stem_name}_{scenario['name']}_target_standard.wav"),
                     sfx_t.astype(np.float32), sr)
            sf.write(str(out_dir / f"{stem_name}_{scenario['name']}_contrast_standard.wav"),
                     sfx_c.astype(np.float32), sr)
        logger.info("WAVs saved to %s", out_dir)

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print("If negative query (a>0) increases cosine distance and selectivity (dB)")
    print("compared to standard (a=0), the technique is working.")
    print()
    print("Listen to the saved WAVs to judge qualitative improvement:")
    print("  *_target_alpha0.3.wav  should contain MORE of the target sound")
    print("  *_contrast_alpha0.3.wav should contain LESS of the target sound")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
