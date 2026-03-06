import shutil
import sys
import urllib.request
from pathlib import Path

_root = Path(__file__).resolve().parents[3]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from ai.ai_runtime.utils.paths import get_models_checkpoints_path

CHECKPOINTS = get_models_checkpoints_path()

WAVEFORMER_URL = "https://targetsound.cs.washington.edu/files/experiments.zip"
YAMNET_URL = "https://tfhub.dev/google/yamnet/1?tf-hub-format=compressed"
YAMNET_CLASS_MAP_URL = "https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv"


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"[skip] {dest.name} already exists")
        return
    print(f"[download] {url} -> {dest}")
    with urllib.request.urlopen(url) as resp, dest.open("wb") as f:
        shutil.copyfileobj(resp, f)


def main() -> None:
    download(WAVEFORMER_URL, CHECKPOINTS / "waveformer_experiments.zip")
    download(YAMNET_URL, CHECKPOINTS / "yamnet_1.tar.gz")
    download(YAMNET_CLASS_MAP_URL, CHECKPOINTS / "yamnet_class_map.csv")
    print("Downloads completed.")


if __name__ == "__main__":
    main()

