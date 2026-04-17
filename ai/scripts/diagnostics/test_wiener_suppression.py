"""
Test the new Wiener mask suppression vs old subtract_target on real audio.

Compares both policies side-by-side so you can listen and judge.

Example:
    python ai/scripts/diagnostics/test_wiener_suppression.py ^
        --input ai/data/audio/raw/speech_barking.wav ^
        --category pets

    python ai/scripts/diagnostics/test_wiener_suppression.py ^
        --input ai/data/audio/raw/speech_keyboard.wav ^
        --category typing
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf

from ai.ai_runtime.separation.codecsep_separator import CodecSepSeparator
from ai.ai_runtime.suppression.semantic_suppressor import SemanticSuppressor
from ai.ai_runtime.utils.codecsep import FixedCategoryRuntimeCatalog
from ai.ai_runtime.utils.paths import (
    get_codecsep_fixed_category_gate_thresholds_path,
    get_codecsep_fixed_category_identity_path,
    get_codecsep_runtime_fixed_category_mapping_path,
)


def _load_audio(path: Path) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(str(path), dtype="float32", always_2d=False)
    return audio, sr


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="A/B test Wiener mask vs subtract_target suppression.")
    p.add_argument("--input", type=Path, required=True, help="Input wav path.")
    p.add_argument("--category", type=str, required=True,
                   help="Suppress category (typing, pets, traffic, siren, etc.).")
    p.add_argument("--output-dir", type=Path,
                   default=Path("ai/data/audio/processed/wiener_ab_test"),
                   help="Output directory.")
    p.add_argument("--device", type=str, default=None)
    p.add_argument("--checkpoint", type=Path, default=None)
    p.add_argument("--max-length", type=float, default=10.0)
    p.add_argument("--aggressiveness", type=float, default=1.0)
    p.add_argument(
        "--target-gain",
        type=float,
        default=1.0,
        help="Extra post-separation gain multiplier for the removed target in fixed-category sum mode.",
    )
    p.add_argument(
        "--fixed-merge-policy",
        type=str,
        default="wiener_mask",
        choices=("wiener_mask", "sum"),
        help="How fixed-category targets are removed from the mix.",
    )
    return p


def run_suppression(
    audio,
    sr,
    category,
    mode_label,
    codecsep_mode,
    *,
    checkpoint=None,
    device=None,
    aggressiveness=1.0,
    fixed_merge_policy="wiener_mask",
    policy_override=None,
):
    """Run suppression with given settings and return clean audio."""
    supp = SemanticSuppressor(
        separator_backend="codecsep",
        masking_method="cirm",
        codecsep_checkpoint_path=checkpoint,
        codecsep_device=device,
    )
    catalog = FixedCategoryRuntimeCatalog.load(
        identity_path=get_codecsep_fixed_category_identity_path(),
        mapping_path=get_codecsep_runtime_fixed_category_mapping_path(),
        threshold_path=get_codecsep_fixed_category_gate_thresholds_path(),
    )
    resolution = catalog.resolve_targets(
        class_ids=[category],
        legacy_categories=[category],
        product_categories=[category],
    )
    resolved_class_ids = [int(value) for value in resolution["class_ids"]]

    kwargs = dict(
        audio=audio.copy(),
        sample_rate=sr,
        detection_threshold=-1,  # bypass detection, force suppression
        codecsep_mode=codecsep_mode,
        aggressiveness=float(aggressiveness),
        codecsep_fixed_merge_policy=str(fixed_merge_policy),
    )
    if resolved_class_ids:
        kwargs["codecsep_hive_class_ids"] = resolved_class_ids
        kwargs["codecsep_product_categories"] = []
        kwargs["suppress_categories"] = []
    else:
        kwargs["suppress_categories"] = [category]

    clean = supp.suppress(**kwargs)
    return clean


def run_stem_diagnostic(audio, sr, category, output_dir, device=None, checkpoint=None):
    """Run raw stem separation and save each stem for inspection."""
    import yaml
    from ai.ai_runtime.utils.paths import get_config_path

    mapping_path = get_config_path("category_to_codecsep.yaml")
    with open(mapping_path) as f:
        cfg = yaml.safe_load(f)

    prompts_cfg = cfg.get("queries", {}).get(category, {})
    sfx_prompt = (prompts_cfg.get("positive_prompts") or [cfg.get("prompts", {}).get(category, "sound effects")])[0]

    sep = CodecSepSeparator(checkpoint_path=checkpoint, device=device)
    if sep.supports_fixed_category():
        catalog = FixedCategoryRuntimeCatalog.load(
            identity_path=get_codecsep_fixed_category_identity_path(),
            mapping_path=get_codecsep_runtime_fixed_category_mapping_path(),
            threshold_path=get_codecsep_fixed_category_gate_thresholds_path(),
        )
        resolution = catalog.resolve_targets(legacy_categories=[category])
        class_ids = [int(value) for value in resolution["class_ids"]]
        if not class_ids:
            raise RuntimeError(f"No fixed-category class ids resolved for category '{category}'")
        bundle = sep.separate_class_id_bundle(
            audio,
            sample_rate=sr,
            class_ids=class_ids,
            query_mode="present",
        )
        stems = {}
        labels = catalog.describe_class_ids(class_ids)
        for class_id, label in zip(class_ids, labels):
            safe_label = str(label).replace("/", "_").replace("\\", "_").replace(" ", "_")
            stems[f"class_{class_id}_{safe_label}"] = bundle["targets"][class_id]
        print(f"\n--- Fixed-Category Diagnostics (category: '{category}', class_ids: {class_ids}) ---")
    else:
        stems = sep.separate_stems(
            audio,
            sample_rate=sr,
            stems=("speech", "music", "sfx"),
            prompt_overrides={"sfx": [sfx_prompt]},
        )
        print(f"\n--- Stem Diagnostics (prompt: '{sfx_prompt}') ---")

    stem_name = f"diag_{category}"
    for name, stem_audio in stems.items():
        s = np.asarray(stem_audio, dtype=np.float32)
        rms = np.sqrt(np.mean(s ** 2))
        peak = np.max(np.abs(s))
        out_path = output_dir / f"{stem_name}_{name}.wav"
        sf.write(str(out_path), s, sr)
        print(f"  {name:28s}: RMS={rms:.6f}  peak={peak:.6f}  -> {out_path.name}")

    rms_vals = {
        name: float(np.sqrt(np.mean(np.asarray(s, dtype=np.float32) ** 2)))
        for name, s in stems.items()
    }
    total = sum(rms_vals.values()) + 1e-10
    print(f"\n  Energy ratios:")
    for name, rms in rms_vals.items():
        print(f"    {name:28s}: {rms/total*100:.1f}%")

    return stems


def run_fixed_category_direct_subtract(
    audio,
    sr,
    category,
    *,
    checkpoint=None,
    device=None,
    target_gain=1.0,
):
    sep = CodecSepSeparator(checkpoint_path=checkpoint, device=device)
    if not sep.supports_fixed_category():
        raise RuntimeError("Direct fixed-category subtract test requires a fixed-category checkpoint.")
    catalog = FixedCategoryRuntimeCatalog.load(
        identity_path=get_codecsep_fixed_category_identity_path(),
        mapping_path=get_codecsep_runtime_fixed_category_mapping_path(),
        threshold_path=get_codecsep_fixed_category_gate_thresholds_path(),
    )
    resolution = catalog.resolve_targets(legacy_categories=[category], class_ids=[category], product_categories=[category])
    class_ids = [int(value) for value in resolution["class_ids"]]
    if not class_ids:
        raise RuntimeError(f"No fixed-category class ids resolved for category '{category}'")
    bundle = sep.separate_class_id_bundle(
        audio,
        sample_rate=sr,
        class_ids=class_ids,
        query_mode="present",
        merge_policy="sum",
        aggressiveness=float(target_gain),
    )
    return np.asarray(bundle["merged_target"], dtype=np.float32), np.asarray(bundle["clean_audio"], dtype=np.float32)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    input_path = args.input.resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    audio, sr = _load_audio(input_path)
    max_samples = int(args.max_length * sr)
    if max_samples > 0 and len(audio) > max_samples:
        audio = audio[:max_samples]
        print(f"Truncated to {args.max_length:.1f}s")

    stem = input_path.stem

    # Save original
    print(f"Audio shape: {audio.shape}, dtype: {audio.dtype}, sr: {sr}")
    sf.write(str(output_dir / f"{stem}_original.wav"), audio, sr)
    print(f"Original: {output_dir / f'{stem}_original.wav'}")

    # Step 1: Raw stem diagnostic — see what CodecSep actually produces
    print(f"\n{'='*60}")
    print(f"STEP 1: Raw stem separation diagnostic")
    print(f"{'='*60}")
    run_stem_diagnostic(audio, sr, args.category, output_dir,
                        device=args.device, checkpoint=args.checkpoint)

    # Step 2: Full suppression with Wiener mask
    print(f"\n{'='*60}")
    print(f"STEP 2: CodecSep suppression (category={args.category})")
    print(f"{'='*60}")
    clean_wiener = run_suppression(
        audio,
        sr,
        args.category,
        "codecsep",
        "fixed_category",
        checkpoint=args.checkpoint,
        device=args.device,
        aggressiveness=args.aggressiveness,
        fixed_merge_policy=args.fixed_merge_policy,
    )
    out_wiener = output_dir / f"{stem}_suppress_{args.category}_{args.fixed_merge_policy}.wav"
    clean_arr = np.asarray(clean_wiener, dtype=np.float32)
    sf.write(str(out_wiener), clean_arr, sr)
    print(f"Suppressed output: {out_wiener}")
    print(f"Output shape: {clean_arr.shape}")

    if args.fixed_merge_policy == "sum" and float(args.target_gain) != 1.0:
        print(f"\n{'='*60}")
        print(f"STEP 3: Direct boosted subtract sanity check")
        print(f"{'='*60}")
        boosted_removed, boosted_clean = run_fixed_category_direct_subtract(
            audio,
            sr,
            args.category,
            checkpoint=args.checkpoint,
            device=args.device,
            target_gain=args.target_gain,
        )
        boosted_out = output_dir / f"{stem}_suppress_{args.category}_directgain_{args.target_gain:.2f}.wav"
        sf.write(str(boosted_out), boosted_clean.astype(np.float32), sr)
        print(f"Boosted direct-subtract output: {boosted_out}")
        print(
            f"Boosted removed RMS: {np.sqrt(np.mean((boosted_removed.mean(axis=-1) if boosted_removed.ndim == 2 else boosted_removed) ** 2)):.6f}"
        )

    # Compute metrics on flattened mono for fair comparison
    orig_flat = audio.mean(axis=-1) if audio.ndim == 2 else audio
    clean_flat = clean_arr.mean(axis=-1) if clean_arr.ndim == 2 else clean_arr
    min_len = min(len(orig_flat), len(clean_flat))

    orig_rms = np.sqrt(np.mean(orig_flat[:min_len] ** 2))
    wiener_rms = np.sqrt(np.mean(clean_flat[:min_len] ** 2))
    diff = orig_flat[:min_len] - clean_flat[:min_len]
    removed_rms = np.sqrt(np.mean(diff ** 2))

    print(f"\n--- Metrics ---")
    print(f"Original RMS:          {orig_rms:.6f}")
    print(f"Wiener clean RMS:      {wiener_rms:.6f}")
    print(f"Removed RMS:           {removed_rms:.6f}")
    print(f"Suppression dB:        {20 * np.log10(wiener_rms / (orig_rms + 1e-10)):.2f} dB")

    print(f"\nAll outputs in: {output_dir}")
    print("Listen to the diag_* files to inspect the fixed-category target estimates that were used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
