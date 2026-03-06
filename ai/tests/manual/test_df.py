"""Manual smoke helper for SpeechEnhancer import/init."""

from __future__ import annotations

__test__ = False

import traceback
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    try:
        from ai.ai_runtime.enhancement import SpeechEnhancer

        _ = SpeechEnhancer()
        print("SpeechEnhancer initialized successfully!")
    except Exception:
        with open(repo_root / "trace.txt", "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
