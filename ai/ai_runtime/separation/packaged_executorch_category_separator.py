"""
Shared ExecuTorch wrapper for packaged fixed-category separators.
"""

from __future__ import annotations

import json
import logging
import platform
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np

from .packaged_onnx_category_separator import PackagedOnnxCategorySeparator

logger = logging.getLogger(__name__)


class PackagedExecuTorchCategorySeparator(PackagedOnnxCategorySeparator):
    """Inference wrapper for packaged fixed-category ExecuTorch separators."""

    def __init__(
        self,
        *,
        model_label: str,
        default_model_path: Path,
        default_model_dir: Path,
        default_categories_path: Path,
        default_model_filename: str,
        model_path: Optional[Union[str, Path]] = None,
        categories_path: Optional[Union[str, Path]] = None,
        device: Optional[str] = None,
        default_sample_rate: int,
        default_segment_seconds: float,
        default_overlap_seconds: float,
    ) -> None:
        try:
            import torch
        except ImportError as exc:
            raise ImportError(
                f"torch is required for {model_label} ExecuTorch inference. "
                "Install with: pip install torch"
            ) from exc
        try:
            from executorch.extension.pybindings import portable_lib
        except ImportError as exc:
            raise ImportError(
                f"executorch is required for {model_label} ExecuTorch inference. "
                "Install with: pip install executorch"
            ) from exc

        self._torch = torch
        self._portable_lib = portable_lib
        self.model_label = str(model_label)
        self._default_overlap_seconds = float(default_overlap_seconds)

        model_candidate = Path(model_path) if model_path else default_model_path
        if model_candidate.is_dir():
            self.model_dir = model_candidate
            self.model_path = model_candidate / default_model_filename
        else:
            self.model_path = model_candidate
            self.model_dir = model_candidate.parent if model_candidate.parent else default_model_dir

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"{self.model_label} ExecuTorch model not found: {self.model_path}"
            )

        self.sidecar_path = self.model_path.with_suffix(".pte.json")
        self.executorch_metadata = self._load_executorch_metadata(self.sidecar_path)
        self.executorch_backend = str(
            self.executorch_metadata.get("backend", "portable"),
        ).strip().casefold() or "portable"

        self.categories_yaml_path = (
            Path(categories_path) if categories_path else default_categories_path
        )
        self.categories_txt_path = (
            self.categories_yaml_path.with_suffix(".txt")
            if self.categories_yaml_path.name == "categories_15.yaml"
            else self.model_dir / "categories_15.txt"
        )
        metadata, self.categories = self._load_categories()
        self._category_lookup = {
            str(label).strip().casefold(): index
            for index, label in enumerate(self.categories)
        }

        self.sample_rate = int(metadata.get("sample_rate", default_sample_rate) or default_sample_rate)
        self.segment_seconds = float(
            metadata.get("segment_seconds", default_segment_seconds) or default_segment_seconds
        )
        self.overlap_seconds = float(
            metadata.get("overlap_seconds", default_overlap_seconds) or default_overlap_seconds
        )
        self.segment_samples = max(1, int(round(self.sample_rate * self.segment_seconds)))
        self.overlap_samples = min(
            int(round(self.sample_rate * self.overlap_seconds)),
            max(0, self.segment_samples - 1),
        )

        requested = (device or "").strip().casefold()
        if requested and requested != "cpu":
            logger.warning(
                "%s ExecuTorch runtime ignores device=%s and runs on CPU.",
                self.model_label,
                device,
            )

        if (
            platform.system() == "Windows"
            and self.model_label == "CodecSepDNRv2_15Cat"
            and self.executorch_backend == "portable"
        ):
            raise RuntimeError(
                "CodecSepDNRv2_15Cat portable ExecuTorch exports stall on Windows desktop. "
                "Re-export the package with XNNPACK and retry: "
                "python -m ai.export.export_codecsep_dnrv2_15cat_pte_only --prefer-xnnpack --skip-parity"
            )

        if platform.system() == "Windows" and self.executorch_backend != "xnnpack":
            # ExecuTorch's own pybinding tests use a smaller threadpool to avoid
            # flaky runtime/threading failures. Use a conservative size here to
            # keep first-chunk inference from stalling on Windows.
            try:
                self._portable_lib._unsafe_reset_threadpool(1)
                logger.info(
                    "%s ExecuTorch reset portable threadpool to 1 thread on Windows",
                    self.model_label,
                )
            except Exception as exc:
                logger.warning(
                    "%s ExecuTorch could not reset portable threadpool on Windows: %s",
                    self.model_label,
                    exc,
                )

        self._module = self._portable_lib._load_for_executorch(
            str(self.model_path),
            None,
            False,
            0,
            self._portable_lib.Verification.Minimal,
        )
        logger.info(
            "%s ExecuTorch initialized from %s (backend=%s)",
            self.model_label,
            self.model_path,
            self.executorch_backend,
        )

    @staticmethod
    def _load_executorch_metadata(path: Path) -> dict[str, object]:
        if not path.is_file():
            return {}
        try:
            return dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning("Failed to parse ExecuTorch sidecar %s: %s", path, exc)
            return {}

    @staticmethod
    def _coerce_output(value: Any) -> np.ndarray:
        if hasattr(value, "detach"):
            return value.detach().cpu().numpy()
        if hasattr(value, "numpy"):
            return np.asarray(value.numpy(), dtype=np.float32)
        return np.asarray(value, dtype=np.float32)

    def _method_inputs(self, padded: np.ndarray, category_idx: int) -> tuple[object, object]:
        label_vector = np.zeros((1, len(self.categories)), dtype=np.float32)
        label_vector[0, category_idx] = 1.0
        return (
            self._torch.from_numpy(
                padded.reshape(1, 1, -1).astype(np.float32, copy=False),
            ),
            self._torch.from_numpy(label_vector),
        )

    def _run_window(self, chunk: np.ndarray, category_idx: int) -> np.ndarray:
        valid_length = int(chunk.shape[0])
        if valid_length < self.segment_samples:
            padded = np.zeros(self.segment_samples, dtype=np.float32)
            padded[:valid_length] = chunk
        else:
            padded = np.asarray(chunk[: self.segment_samples], dtype=np.float32)

        outputs = self._module.run_method("forward", self._method_inputs(padded, category_idx))
        separated = self._coerce_output(outputs[0]).reshape(-1)
        return separated[:valid_length]
