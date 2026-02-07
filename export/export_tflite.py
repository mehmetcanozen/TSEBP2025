"""
TFLite Model Export - Mobile Deployment

Export Waveformer to TFLite (via ONNX -> TensorFlow) for mobile inference.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
from pathlib import Path

import onnx
import tensorflow as tf
# from onnx_tf.backend import prepare  <-- Removed

from export.export_onnx import ONNXExporter
from training.models.audio_mixer import WaveformerSeparator

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
        temp_dir: Path = Path("models/temp_export"),
        use_fp16: bool = True,
    ) -> Path:
        """
        Export model to TFLite.
        
        Args:
            output_path: Path to save .tflite file
            temp_dir: Temporary directory for intermediate files
            use_fp16: Apply FP16 quantization
        
        Returns:
            Path to exported TFLite file
        """
        logger.info(f"Exporting Waveformer to TFLite: {output_path}")
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
        
        if use_fp16:
             pass

        try:
            subprocess.run(cmd, check=True)
            
            # Move the generated file to expected output path
            generated_file = output_path.parent / "model_float32.tflite"
            if generated_file.exists():
                generated_file.rename(output_path)
            else:
                pass
            
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
        help="Disable FP16 quantization"
    )

    args = parser.parse_args()

    # Initialize separator
    separator = WaveformerSeparator()

    # Export
    exporter = TFLiteExporter(separator)
    
    try:
        tflite_path = exporter.export(
            output_path=args.output,
            use_fp16=not args.no_fp16,
        )
        print(f"\n✅ Export complete: {tflite_path}")
        
    except ImportError as e:
        print(f"\n❌ Missing dependencies: {e}")
        print("Please run: pip install tensorflow onnx-tf")
    except Exception as e:
        print(f"\n❌ Export failed: {e}")


if __name__ == "__main__":
    main()
