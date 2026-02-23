import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
import traceback

try:
    from training.models.speech_enhancer import SpeechEnhancer
    se = SpeechEnhancer()
    print("SpeechEnhancer initialized successfully!")
except Exception as e:
    with open("trace.txt", "w") as f:
        f.write(traceback.format_exc())
