"""Audit the bundled Waveformer desktop ONNX export.

By default this prints a JSON report and does not write repo artifacts. Pass
``--write-json`` when you want a saved report for handoff or CI evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.ai_runtime.separation.waveformer_onnx_stream import WaveformerOnnxStream, suppress_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit the Waveformer ONNX desktop export.")
    parser.add_argument(
        "--model-package",
        type=Path,
        default=PROJECT_ROOT / "ai" / "models" / "Waveformer" / "model_package.json",
        help="Path to the Waveformer model_package.json.",
    )
    parser.add_argument("--target", default="dog", help="Waveformer category id for the smoke run.")
    parser.add_argument("--input-wav", type=Path, default=None, help="Optional WAV to suppress.")
    parser.add_argument("--output-wav", type=Path, default=None, help="Optional cleaned WAV output.")
    parser.add_argument("--noise-wav", type=Path, default=None, help="Optional residual WAV output.")
    parser.add_argument("--aggressiveness", type=float, default=1.1)
    parser.add_argument("--write-json", type=Path, default=None, help="Optional report path.")
    parser.add_argument(
        "--skip-onnx-checker",
        action="store_true",
        help="Skip optional onnx.checker validation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runner = WaveformerOnnxStream(args.model_package)
    report: dict[str, Any] = {
        "contract": runner.audit_contract(check_onnx=not args.skip_onnx_checker),
        "two_step_smoke": runner.smoke_two_step(args.target),
    }

    if args.input_wav is not None:
        if args.output_wav is None:
            raise SystemExit("--output-wav is required when --input-wav is provided")
        file_stats = suppress_file(
            input_path=args.input_wav,
            output_path=args.output_wav,
            noise_path=args.noise_wav,
            categories=[args.target],
            aggressiveness=args.aggressiveness,
            model_package_path=args.model_package,
        )
        file_stats.pop("noise_audio", None)
        report["file_suppression"] = file_stats

    encoded = json.dumps(report, indent=2)
    print(encoded)
    if args.write_json is not None:
        args.write_json.parent.mkdir(parents=True, exist_ok=True)
        args.write_json.write_text(encoded + "\n", encoding="utf-8")

    contract_ok = bool(report["contract"].get("ok"))
    smoke_ok = bool(report["two_step_smoke"].get("ok"))
    return 0 if contract_ok and smoke_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
