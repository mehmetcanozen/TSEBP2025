"""Separation models used by runtime and export.

Keep imports lazy so CodecSep-only tooling does not require the full
Waveformer dependency stack at import time.
"""

__all__ = [
    "AudioSepHive15CatSeparator",
    "CodecSepDNRv2_15CatSeparator",
    "CodecSepDNRv2_15CatExecuTorchSeparator",
    "CodecSepSeparator",
    "TARGET_SAMPLE_RATE",
    "TARGETS",
    "UniversalSeparator",
    "WaveformerSeparator",
]


def __getattr__(name: str):
    if name == "CodecSepSeparator":
        from .codecsep_separator import CodecSepSeparator

        globals()["CodecSepSeparator"] = CodecSepSeparator
        return CodecSepSeparator
    if name == "UniversalSeparator":
        from .universal_separator import UniversalSeparator

        globals()["UniversalSeparator"] = UniversalSeparator
        return UniversalSeparator
    if name == "AudioSepHive15CatSeparator":
        from .audiosep_hive15cat_separator import AudioSepHive15CatSeparator

        globals()["AudioSepHive15CatSeparator"] = AudioSepHive15CatSeparator
        return AudioSepHive15CatSeparator
    if name == "CodecSepDNRv2_15CatSeparator":
        from .codecsep_dnrv2_15cat_separator import CodecSepDNRv2_15CatSeparator

        globals()["CodecSepDNRv2_15CatSeparator"] = CodecSepDNRv2_15CatSeparator
        return CodecSepDNRv2_15CatSeparator
    if name == "CodecSepDNRv2_15CatExecuTorchSeparator":
        from .codecsep_dnrv2_15cat_executorch_separator import (
            CodecSepDNRv2_15CatExecuTorchSeparator,
        )

        globals()["CodecSepDNRv2_15CatExecuTorchSeparator"] = (
            CodecSepDNRv2_15CatExecuTorchSeparator
        )
        return CodecSepDNRv2_15CatExecuTorchSeparator
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
