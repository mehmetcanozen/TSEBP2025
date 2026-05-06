"""ONNX wrapper for the exact-15 AudioSepHive15Cat separator."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .packaged_onnx_category_separator import PackagedOnnxCategorySeparator
from ai.ai_runtime.utils.paths import (
    get_audiosep_hive15cat_categories_path,
    get_audiosep_hive15cat_onnx_path,
    get_audiosep_hive15cat_shared_export_path,
)

TARGET_SAMPLE_RATE = 32000
SEGMENT_SECONDS = 5.0
OVERLAP_SECONDS = 1.0
SEGMENT_SAMPLES = int(TARGET_SAMPLE_RATE * SEGMENT_SECONDS)
OVERLAP_SAMPLES = int(TARGET_SAMPLE_RATE * OVERLAP_SECONDS)


class AudioSepHive15CatSeparator(PackagedOnnxCategorySeparator):
    """Inference wrapper for the exact-15 fixed-category AudioSep ONNX export."""

    def __init__(
        self,
        model_path: Optional[Union[str, Path]] = None,
        categories_path: Optional[Union[str, Path]] = None,
        device: Optional[str] = None,
    ) -> None:
        super().__init__(
            model_label="AudioSepHive15Cat",
            default_model_path=get_audiosep_hive15cat_onnx_path(),
            default_model_dir=get_audiosep_hive15cat_shared_export_path(),
            default_categories_path=get_audiosep_hive15cat_categories_path(),
            default_model_filename="frozensep_hive_15cat.onnx",
            model_path=model_path,
            categories_path=categories_path,
            device=device,
            default_sample_rate=TARGET_SAMPLE_RATE,
            default_segment_seconds=SEGMENT_SECONDS,
            default_overlap_seconds=OVERLAP_SECONDS,
        )

__all__ = [
    "AudioSepHive15CatSeparator",
    "OVERLAP_SAMPLES",
    "SEGMENT_SAMPLES",
    "TARGET_SAMPLE_RATE",
]
