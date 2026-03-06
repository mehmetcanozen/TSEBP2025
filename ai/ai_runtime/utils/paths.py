"""
Centralized path resolution for AI runtime and project layout.
"""

from pathlib import Path

# Project root: ai/ai_runtime/utils/paths.py -> parents[3] = project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# AI package root
_AI_ROOT = _PROJECT_ROOT / "ai"
_AI_RUNTIME_ROOT = _AI_ROOT / "ai_runtime"


def get_project_root() -> Path:
    """Return the project root directory."""
    return _PROJECT_ROOT


def get_ai_root() -> Path:
    """Return the ai package root (ai/)."""
    return _AI_ROOT


def get_ai_runtime_root() -> Path:
    """Return the ai_runtime package root (ai/ai_runtime/)."""
    return _AI_RUNTIME_ROOT


def get_config_path(name: str) -> Path:
    """Return path to a config file in ai/ai_runtime/config/."""
    return _AI_RUNTIME_ROOT / "config" / name


def get_models_path() -> Path:
    """Return the models directory (ai/models/)."""
    return _AI_ROOT / "models"


def get_models_checkpoints_path() -> Path:
    """Return the checkpoints directory (ai/models/checkpoints/)."""
    return get_models_path() / "checkpoints"


def get_data_audio_path(subdir: str = "raw") -> Path:
    """Return path to audio data (ai/data/audio/raw or processed)."""
    return _AI_ROOT / "data" / "audio" / subdir


def get_temp_export_path() -> Path:
    """Return path to temp export directory (ai/models/temp_export)."""
    return get_models_path() / "temp_export"


def get_exports_onnx_path(name: str = "waveformer.onnx") -> Path:
    """Return path to ONNX export (ai/models/exports/onnx/)."""
    return get_models_path() / "exports" / "onnx" / name


def setup_project_path() -> None:
    """Add project root to sys.path if not already present."""
    import sys
    root = str(_PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
