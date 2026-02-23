import sys
from pathlib import Path
sys.path.insert(0, str(Path(r"c:\SoftwareProjects\TSEBP2025")))
import traceback

try:
    from training.models.speech_enhancer import SpeechEnhancer
    se = SpeechEnhancer()
    print("SpeechEnhancer initialized successfully!")
except Exception as e:
    with open("trace.txt", "w") as f:
        f.write(traceback.format_exc())
