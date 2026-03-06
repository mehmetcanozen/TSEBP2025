"""
TFLite Model Export - Mobile Deployment

Export Waveformer to TFLite (via ONNX -> TensorFlow) for mobile inference.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
from pathlib import Path
# from onnx_tf.backend import prepare  <-- Removed

from ai.ai_runtime.separation import WaveformerSeparator
from ai.ai_runtime.utils.paths import get_temp_export_path
from ai.export.export_onnx import ONNXExporter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TFLiteExporter:
    """Export Waveformer to TFLite format."""

    def __init__(self, separator: WaveformerSeparator):
        self.separator = separator
        self.onnx_exporter = ONNXExporter(separator)

    def export(
        self,
        output_path: Path,
        temp_dir: Path = None,
        quantization: str = "fp16",
    ) -> Path:
        """
        Export model to TFLite.
        
        Args:
            output_path: Path to save .tflite file
            temp_dir: Temporary directory for intermediate files
            quantization: Quantization mode: "fp32", "fp16", or "int8"
        
        Returns:
            Path to exported TFLite file
        """
        if temp_dir is None:
            temp_dir = get_temp_export_path()
        logger.info(f"Exporting Waveformer to TFLite: {output_path} (quantization={quantization})")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Export to ONNX
        onnx_path = temp_dir / "model.onnx"
        self.onnx_exporter.export(
            output_path=onnx_path,
            opset_version=17,
            use_fp16=False,  # Don't quantize ONNX, we'll quantize TFLite
        )

        # Step 2: Convert ONNX to TFLite using onnx2tf
        logger.info("Converting ONNX to TFLite using onnx2tf...")
        
        # Construct onnx2tf command
        cmd = [
            "onnx2tf",
            "-i", str(onnx_path),
            "-o", str(output_path.parent),
            "-osd" # Output standard TFLite
        ]
        
        if quantization not in {"fp32", "fp16", "int8"}:
            raise ValueError(f"Unsupported quantization: {quantization}. Must be one of: 'fp32', 'fp16', 'int8'")

        if quantization == "fp16":
            logger.info("Applying FP16 quantization...")
            cmd.append("-opt")
            cmd.append("--float16_quantization")
        elif quantization == "int8":
            logger.info("Applying INT8 quantization (for mobile CPU deployment)...")
            cmd.append("-oiqt")  # onnx2tf flag for INT8 quantization

        try:
            subprocess.run(cmd, check=True)
            
            # Determine expected generated file based on quantization
            name_map = {
                "fp32": "model_float32.tflite",
                "fp16": "model_float16.tflite",
                "int8": "model_integer_quant.tflite",
            }
            expected_name = name_map.get(quantization, "model_float32.tflite")
            generated_file = output_path.parent / expected_name

            # Move the generated file to expected output path
            if generated_file.exists():
                generated_file.rename(output_path)
            else:
                raise FileNotFoundError(
                    f"Expected TFLite file '{expected_name}' not found in "
                    f"'{output_path.parent}'. onnx2tf may have failed or produced "
                    f"a differently named file (quantization={quantization})."
                )

            logger.info("onnx2tf conversion complete")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"onnx2tf failed: {e}")
            raise

        logger.info(f"TFLite model saved: {output_path}")
        
        return output_path


def main():
    parser = argparse.ArgumentParser(description="Export Waveformer to TFLite")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("mobile/assets/models/waveformer.tflite"),
        help="Output TFLite file path"
    )
    parser.add_argument(
        "--no-fp16",
        action="store_true",
        help="Disable FP16 quantization (use FP32)"
    )
    parser.add_argument(
        "--int8",
        action="store_true",
        help="Use INT8 quantization for mobile CPU (4x smaller, 2-3x faster)"
    )

    args = parser.parse_args()

    # Determine quantization mode
    if args.int8:
        quant_mode = "int8"
    elif args.no_fp16:
        quant_mode = "fp32"
    else:
        quant_mode = "fp16"

    # Initialize separator
    separator = WaveformerSeparator()

    # Export
    exporter = TFLiteExporter(separator)
    
    try:
        tflite_path = exporter.export(
            output_path=args.output,
            quantization=quant_mode,
        )
        print(f"\n✅ Export complete: {tflite_path}")
        
    except ImportError as e:
        print(f"\n❌ Missing dependencies: {e}")
        print("Please run: pip install onnx2tf tensorflow")
    except Exception as e:
        print(f"\n❌ Export failed: {e}")


if __name__ == "__main__":
    main()
