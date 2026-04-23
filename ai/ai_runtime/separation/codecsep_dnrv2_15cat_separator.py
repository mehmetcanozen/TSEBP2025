"""ONNX wrapper for the frozen CodecSepDNRv2_15Cat separator."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .packaged_onnx_category_separator import PackagedOnnxCategorySeparator
from ai.ai_runtime.utils.paths import (
    get_codecsep_dnrv2_15cat_categories_path,
    get_codecsep_dnrv2_15cat_model_path,
    get_codecsep_dnrv2_15cat_onnx_path,
)

TARGET_SAMPLE_RATE = 16000
SEGMENT_SECONDS = 2.0
OVERLAP_SECONDS = 0.5
SEGMENT_SAMPLES = int(TARGET_SAMPLE_RATE * SEGMENT_SECONDS)
OVERLAP_SAMPLES = int(TARGET_SAMPLE_RATE * OVERLAP_SECONDS)


class CodecSepDNRv2_15CatSeparator(PackagedOnnxCategorySeparator):
    """Inference wrapper for the frozen 15-category CodecSep DNRv2 ONNX export."""

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        categories_path: Optional[Union[str, Path]] = None,
        device: Optional[str] = None,
    ) -> None:
        super().__init__(
            model_label="CodecSepDNRv2_15Cat",
            default_model_path=get_codecsep_dnrv2_15cat_onnx_path(),
            default_model_dir=get_codecsep_dnrv2_15cat_model_path(),
            default_categories_path=get_codecsep_dnrv2_15cat_categories_path(),
            default_model_filename="codecsep_dnrv2_15cat.onnx",
            model_path=model_path,
            categories_path=categories_path,
            device=device,
            default_sample_rate=TARGET_SAMPLE_RATE,
            default_segment_seconds=SEGMENT_SECONDS,
            default_overlap_seconds=OVERLAP_SECONDS,
        )


__all__ = [
    "CodecSepDNRv2_15CatSeparator",
    "OVERLAP_SAMPLES",
    "SEGMENT_SAMPLES",
    "TARGET_SAMPLE_RATE",
]
