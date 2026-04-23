"""Suppression orchestration pipeline.

Keep imports lazy so CLI entrypoints can parse arguments and report progress
before heavier runtime dependencies such as SciPy are loaded.
"""

__all__ = [
    "CIRMMasking",
    "MaskingStrategy",
    "SemanticSuppressor",
    "WienerDDMasking",
]


def __getattr__(name: str):
    if name == "SemanticSuppressor":
        from .semantic_suppressor import SemanticSuppressor

        globals()["SemanticSuppressor"] = SemanticSuppressor
        return SemanticSuppressor
    if name in {"CIRMMasking", "MaskingStrategy", "WienerDDMasking"}:
        from .masking import CIRMMasking, MaskingStrategy, WienerDDMasking

        globals().update(
            {
                "CIRMMasking": CIRMMasking,
                "MaskingStrategy": MaskingStrategy,
                "WienerDDMasking": WienerDDMasking,
            }
        )
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
