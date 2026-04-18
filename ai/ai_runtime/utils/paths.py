"""
Centralized path resolution for AI runtime and project layout.
"""

from pathlib import Path
from typing import Iterable

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


def get_waveformer_model_path() -> Path:
    """Return the Waveformer model directory (ai/models/Waveformer/)."""
    return get_models_path() / "Waveformer"


def get_waveformer_assets_path() -> Path:
    """Return the Waveformer asset root (ai/models/Waveformer/assets/)."""
    return get_waveformer_model_path() / "assets"


def get_waveformer_config_path(name: str = "default_config.json") -> Path:
    """Return a Waveformer config path inside assets/config/."""
    return get_waveformer_assets_path() / "config" / name


def get_waveformer_checkpoint_path(name: str = "default_ckpt.pt") -> Path:
    """Return a Waveformer checkpoint path inside assets/checkpoints/."""
    return get_waveformer_assets_path() / "checkpoints" / name


def get_waveformer_archive_path(name: str = "waveformer_experiments.zip") -> Path:
    """Return a Waveformer archive path inside assets/archives/."""
    return get_waveformer_assets_path() / "archives" / name


def get_waveformer_experiments_path() -> Path:
    """Return the extracted Waveformer experiments directory."""
    return get_waveformer_model_path() / "experiments"


def get_yamnet_model_path() -> Path:
    """Return the YAMNet model directory (ai/models/YAMNet/)."""
    return get_models_path() / "YAMNet"


def get_yamnet_saved_models_path() -> Path:
    """Return the YAMNet SavedModel root (ai/models/YAMNet/saved_models/)."""
    return get_yamnet_model_path() / "saved_models"


def get_yamnet_saved_model_path(version: str = "yamnet_1") -> Path:
    """Return a versioned extracted YAMNet SavedModel directory."""
    return get_yamnet_saved_models_path() / version


def get_yamnet_archives_path() -> Path:
    """Return the YAMNet archive root (ai/models/YAMNet/archives/)."""
    return get_yamnet_model_path() / "archives"


def get_yamnet_archive_path(name: str = "yamnet_1.tar.gz") -> Path:
    """Return the default YAMNet TF Hub archive path."""
    return get_yamnet_archives_path() / name


def get_yamnet_tflite_archive_path(
    name: str = "yamnet-tflite-classification-tflite-v1.tar.gz",
) -> Path:
    """Return the archived YAMNet TFLite package path."""
    return get_yamnet_archives_path() / name


def get_yamnet_metadata_path() -> Path:
    """Return the YAMNet metadata directory."""
    return get_yamnet_model_path() / "metadata"


def get_yamnet_class_map_csv_path(name: str = "yamnet_class_map.csv") -> Path:
    """Return the YAMNet class-map CSV path."""
    return get_yamnet_metadata_path() / name


def get_yamnet_tflite_path(name: str = "1.tflite") -> Path:
    """Return the extracted YAMNet TFLite model path."""
    return get_yamnet_model_path() / "tflite" / name


def get_data_audio_path(subdir: str = "raw") -> Path:
    """Return path to audio data (ai/data/audio/raw or processed)."""
    return _AI_ROOT / "data" / "audio" / subdir


def get_temp_export_path() -> Path:
    """Return path to temp export directory (ai/models/temp_export)."""
    return get_models_path() / "temp_export"


def get_codecsep_model_path() -> Path:
    """Return the CodecSep model directory (ai/models/CodecSep/)."""
    return get_models_path() / "CodecSep"


def get_codecsep_bundle_path() -> Path:
    """Return the cleaned DNR CodecSep bundle root."""
    return get_codecsep_model_path() / "Runs" / "CodecSep_DNR_USS_ModelBundle"


def get_audiosep_hive15cat_model_path() -> Path:
    """Return the AudioSepHive15Cat model directory (ai/models/AudioSepHive15Cat/)."""
    return get_models_path() / "AudioSepHive15Cat"


def get_audiosep_hive15cat_onnx_path() -> Path:
    """Return the default AudioSepHive15Cat ONNX path."""
    return get_audiosep_hive15cat_model_path() / "frozensep_hive_15cat.onnx"


def get_audiosep_hive15cat_categories_path() -> Path:
    """Return the default AudioSepHive15Cat category catalog YAML path."""
    return get_audiosep_hive15cat_model_path() / "categories_15.yaml"


def get_codecsep_code_path() -> Path:
    """Return the archived CodecSep source snapshot shipped with the clean bundle."""
    return get_codecsep_bundle_path() / "source_snapshot" / "backup_src"


def get_codecsep_runtime_assets_path() -> Path:
    """Return the CodecSep runtime asset directory shipped with the clean bundle."""
    return get_codecsep_bundle_path() / "runtime_assets"


def get_codecsep_clap_checkpoint_path(
    name: str = "630k-audioset-best.pt",
) -> Path:
    """Return the default CLAP checkpoint path for CodecSep runtime use."""
    return get_codecsep_runtime_assets_path() / "CLAP_weights" / name


def get_codecsep_default_run_dir() -> Path:
    """Return the default CodecSep runtime run directory."""
    return get_codecsep_bundle_path()


def get_codecsep_fixed_category_config_dir() -> Path:
    """Return the fixed-category artifact directory for optional runtime assets."""
    return get_codecsep_model_path() / "config" / "fixed_category"


def get_codecsep_fixed_category_identity_path() -> Path:
    """Return the fixed-category identity catalog path."""
    return get_codecsep_fixed_category_config_dir() / "hive_identity_catalog.json"


def get_codecsep_fixed_category_gate_thresholds_path() -> Path:
    """Return the fixed-category gate-threshold artifact path."""
    return get_codecsep_fixed_category_config_dir() / "gate_thresholds_v2.json"


def get_codecsep_runtime_fixed_category_mapping_path() -> Path:
    """Return the runtime mirror of the fixed-category product mapping."""
    return get_config_path("product_to_hive_fixedset.json")


def get_codecsep_legacy_checkpoint_path() -> Path:
    """Return the legacy single-file CodecSep checkpoint path."""
    return get_codecsep_model_path() / "codecsep_checkpoint.pt"


def get_codecsep_checkpoint_candidates(
    source_path: str | Path | None = None,
) -> tuple[Path, ...]:
    """Return candidate checkpoint files for a CodecSep source path."""
    source = Path(source_path) if source_path is not None else get_codecsep_default_run_dir()
    if source.suffix:
        return (source,)
    v5_family_dirs = {
        "ckpt_best_stable",
        "ckpt_gate_pass",
        "ckpt_best_screen",
        "ckpt_best_val",
        "ckpt_rolling_0",
        "ckpt_rolling_1",
        "ckpt_rolling_2",
    }
    if source.name in v5_family_dirs:
        return (source / "pytorch_model.bin",)
    if source.name == "ckpt_best":
        return (
            source / "pytorch_model.bin",
            source / "ckpt_model_best.pth",
        )
    if source.name == "ckpt_final":
        return (source / "ckpt_model_final.pth",)
    if source.name == "best_accelerate_resume_state":
        return (source / "pytorch_model.bin",)
    if source.name == "final_weights":
        return (source / "ckpt_model_final.pth",)
    return (
        source / "checkpoints" / "best_accelerate_resume_state" / "pytorch_model.bin",
        source / "checkpoints" / "final_weights" / "ckpt_model_final.pth",
        source / "best_accelerate_resume_state" / "pytorch_model.bin",
        source / "final_weights" / "ckpt_model_final.pth",
        source / "ckpt_best_stable" / "pytorch_model.bin",
        source / "ckpt_gate_pass" / "pytorch_model.bin",
        source / "ckpt_best_screen" / "pytorch_model.bin",
        source / "ckpt_best_val" / "pytorch_model.bin",
        source / "ckpt_rolling_2" / "pytorch_model.bin",
        source / "ckpt_rolling_1" / "pytorch_model.bin",
        source / "ckpt_rolling_0" / "pytorch_model.bin",
        source / "ckpt_best" / "pytorch_model.bin",
        source / "ckpt_best" / "ckpt_model_best.pth",
        source / "ckpt_final" / "ckpt_model_final.pth",
    )


def iter_existing_codecsep_checkpoints(
    source_path: str | Path | None = None,
) -> Iterable[Path]:
    """Yield existing checkpoint files for a CodecSep source path."""
    for candidate in get_codecsep_checkpoint_candidates(source_path):
        if candidate.exists():
            yield candidate


def resolve_codecsep_checkpoint_path(
    source_path: str | Path | None = None,
) -> Path:
    """Resolve a CodecSep source path into a concrete checkpoint file."""
    source = Path(source_path) if source_path is not None else get_codecsep_default_run_dir()
    if source.suffix:
        return source
    for candidate in iter_existing_codecsep_checkpoints(source):
        return candidate
    return get_codecsep_checkpoint_candidates(source)[0]


def get_exports_onnx_path(name: str = "waveformer.onnx") -> Path:
    """Return path to ONNX export (ai/models/exports/onnx/)."""
    return get_models_path() / "exports" / "onnx" / name


def setup_project_path() -> None:
    """Add project root to sys.path if not already present."""
    import sys
    root = str(_PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
