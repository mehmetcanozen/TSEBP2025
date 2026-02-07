"""
ONNX Model Export - Desktop Deployment

Export Waveformer to ONNX with FP16 quantization for desktop GPU acceleration.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

from training.models.audio_mixer import WaveformerSeparator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ONNXExporter:
    """Export Waveformer to ONNX format."""

    def __init__(self, separator: WaveformerSeparator):
        self.separator = separator

    def export(
        self,
        output_path: Path,
        opset_version: int = 17, # Use 17 for max compatibility with onnxrt/TFLite
        use_fp16: bool = True,
    ) -> Path:
        """
        Export model to ONNX.
        
        Args:
            output_path: Path to save .onnx file
            opset_version: ONNX opset version
            use_fp16: Apply FP16 quantization
        
        Returns:
            Path to exported ONNX file
        """
        logger.info(f"Exporting Waveformer to ONNX: {output_path}")

        # Create dummy inputs (batch=1, channels=1, samples=44100*3 = 132300)
        # STATIC SHAPE required for TFLite stability
        dummy_audio = torch.randn(1, 1, 132300)  # ~3s at 44.1kHz
        dummy_query = torch.ones(1, 41)  # 41 Waveformer targets

        # Export
        model = self.separator.model
        model.eval()

        torch.onnx.export(
            model,
            (dummy_audio.to(self.separator.device), dummy_query.to(self.separator.device)),
            output_path,
            opset_version=opset_version,
            input_names=["audio_input", "query_vector"],
            output_names=["separated_audio"],
            # dynamic_axes={
            #     "audio_input": {0: "batch_size", 2: "audio_length"},
            #     "query_vector": {0: "batch_size"},
            #     "separated_audio": {0: "batch_size", 2: "audio_length"},
            # },
            do_constant_folding=True,
        )

        logger.info("ONNX export complete")

        # Validate
        onnx_model = onnx.load(output_path)
        onnx.checker.check_model(onnx_model)
        logger.info("ONNX model validated")

        # FP16 quantization
        if use_fp16:
            logger.info("Applying FP16 quantization...")
            from onnxruntime.quantization import quantize_dynamic, QuantType
            
            fp16_path = output_path.with_stem(output_path.stem + "_fp16")
            quantize_dynamic(
                str(output_path),
                str(fp16_path),
                weight_type=QuantType.QFloat16,
            )
            
            # Use FP16 version
            output_path.unlink()
            fp16_path.rename(output_path)
            logger.info(f"FP16 quantized model saved: {output_path}")

        return output_path

    def validate(
        self,
        onnx_path: Path,
        test_audio: np.ndarray,
        sample_rate: int,
    ) -> dict:
        """
        Validate ONNX export against PyTorch model.
        
        Returns:
            Validation metrics (MSE, correlation)
        """
        logger.info("Validating ONNX export...")

        # PyTorch inference
        with torch.inference_mode():
            pt_output = self.separator.separate(test_audio, sample_rate)

        # ONNX inference
        session = ort.InferenceSession(
            str(onnx_path),
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
        )

        # Prepare inputs
        audio_tensor = torch.from_numpy(test_audio).float()
        if audio_tensor.ndim == 1:
            audio_tensor = audio_tensor.unsqueeze(0).unsqueeze(0)
        elif audio_tensor.ndim == 2:
            audio_tensor = audio_tensor.unsqueeze(0)

        query_tensor = torch.ones(1, 41)

        onnx_output = session.run(
            None,
            {
                "audio_input": audio_tensor.numpy(),
                "query_vector": query_tensor.numpy(),
            }
        )[0]

        # Compare outputs
        onnx_output_2d = onnx_output[0].transpose(1, 0)  # (C, T) -> (T, C)
        min_len = min(pt_output.shape[0], onnx_output_2d.shape[0])

        pt_trimmed = pt_output[:min_len]
        onnx_trimmed = onnx_output_2d[:min_len]

        mse = np.mean((pt_trimmed - onnx_trimmed) ** 2)
        correlation = np.corrcoef(pt_trimmed.flatten(), onnx_trimmed.flatten())[0, 1]

        metrics = {
            "mse": float(mse),
            "correlation": float(correlation),
        }

        logger.info(f"Validation metrics: MSE={mse:.6f}, Correlation={correlation:.4f}")

        if mse < 0.01 and correlation > 0.99:
            logger.info("✅ ONNX export validated successfully")
        else:
            logger.warning("⚠️ ONNX export may have quality issues")

        return metrics


def main():
    parser = argparse.ArgumentParser(description="Export Waveformer to ONNX")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("models/exports/onnx/waveformer.onnx"),
        help="Output ONNX file path"
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
    exporter = ONNXExporter(separator)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    
    onnx_path = exporter.export(
        output_path=args.output,
        use_fp16=not args.no_fp16,
    )

    # Validate with dummy audio
    test_audio = np.random.randn(44100 * 3).astype(np.float32)
    metrics = exporter.validate(onnx_path, test_audio, 44100)

    print(f"\n✅ Export complete: {onnx_path}")
    print(f"MSE: {metrics['mse']:.6f}")
    print(f"Correlation: {metrics['correlation']:.4f}")


if __name__ == "__main__":
    main()
