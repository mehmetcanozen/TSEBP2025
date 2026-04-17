"""Separation models used by runtime and export.

Keep imports lazy so CodecSep-only tooling does not require the full
Waveformer dependency stack at import time.
"""

from .codecsep_separator import CodecSepSeparator
from .universal_separator import UniversalSeparator

__all__ = [
    "AudioSepHive15CatSeparator",
    "CodecSepSeparator",
    "TARGET_SAMPLE_RATE",
    "TARGETS",
    "UniversalSeparator",
    "WaveformerSeparator",
]


def __getattr__(name: str):
    if name == "AudioSepHive15CatSeparator":
        from .audiosep_hive15cat_separator import AudioSepHive15CatSeparator

        globals()["AudioSepHive15CatSeparator"] = AudioSepHive15CatSeparator
        return AudioSepHive15CatSeparator
    if name in {"TARGET_SAMPLE_RATE", "TARGETS", "WaveformerSeparator"}:
        from .waveformer_separator import TARGET_SAMPLE_RATE, TARGETS, WaveformerSeparator

        globals().update(
            {
                "TARGET_SAMPLE_RATE": TARGET_SAMPLE_RATE,
                "TARGETS": TARGETS,
                "WaveformerSeparator": WaveformerSeparator,
            }
        )
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
