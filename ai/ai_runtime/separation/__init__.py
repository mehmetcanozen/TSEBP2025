"""Separation models used by runtime and export.

Keep imports lazy so CodecSep-only tooling does not require the full
Waveformer dependency stack at import time.
"""

__all__ = [
    "AudioSepHive15CatSeparator",
    "CodecSepDNRv2_15CatSeparator",
    "CodecSepDNRv2_15CatExecuTorchSeparator",
    "CodecSepSeparator",
    "ClearVoiceNativeBundle",
    "ExportedTSExtractOnnx",
    "TARGET_SAMPLE_RATE",
    "TARGETS",
    "TargetSpeakerSeparator",
    "UniversalSeparator",
    "WaveformerOnnxStream",
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
    if name == "TargetSpeakerSeparator":
        from .target_speaker_separator import TargetSpeakerSeparator

        globals()["TargetSpeakerSeparator"] = TargetSpeakerSeparator
        return TargetSpeakerSeparator
    if name == "ExportedTSExtractOnnx":
        from .exported_target_speaker import ExportedTSExtractOnnx

        globals()["ExportedTSExtractOnnx"] = ExportedTSExtractOnnx
        return ExportedTSExtractOnnx
    if name == "ClearVoiceNativeBundle":
        from .exported_target_speaker import ClearVoiceNativeBundle

        globals()["ClearVoiceNativeBundle"] = ClearVoiceNativeBundle
        return ClearVoiceNativeBundle
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
    if name == "WaveformerOnnxStream":
        from .waveformer_onnx_stream import WaveformerOnnxStream

        globals()["WaveformerOnnxStream"] = WaveformerOnnxStream
        return WaveformerOnnxStream
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
