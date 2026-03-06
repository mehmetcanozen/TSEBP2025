"""
Install AudioSep
Utility script to clone the AudioSep repository and download the required weights.
This simplifies the Phase 3 Universal Extraction setup.
"""

import logging
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

_root = Path(__file__).resolve().parents[3]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def download_file(url: str, dest_path: Path, timeout: int = 30, max_retries: int = 3):
    """Download a file with progress tracking, timeout, and basic retry logic."""
    if dest_path.exists():
        logger.info("File already exists: %s", dest_path)
        return

    logger.info("Downloading %s to %s...", url, dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    chunk_size = 8192
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                total_size_header = response.getheader("Content-Length")
                total_size = int(total_size_header) if total_size_header is not None else None
                downloaded = 0
                last_reported_percent = 0
                last_reported_mb = 0

                with open(dest_path, "wb") as out_file:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        out_file.write(chunk)
                        downloaded += len(chunk)

                        if total_size:
                            percent = int(downloaded * 100 / total_size)
                            if percent >= last_reported_percent + 10:
                                logger.info("Download progress: %s%%", percent)
                                last_reported_percent = percent
                        else:
                            downloaded_mb = downloaded // (10 * 1024 * 1024)
                            if downloaded_mb > last_reported_mb:
                                logger.info("Downloaded approximately %s MB...", downloaded_mb * 10)
                                last_reported_mb = downloaded_mb

            logger.info("Download complete.")
            return

        except Exception as e:
            logger.error("Download attempt %s failed: %s", attempt, e)
            if dest_path.exists():
                try:
                    dest_path.unlink()
                except Exception as cleanup_error:
                    logger.warning("Failed to remove incomplete file %s: %s", dest_path, cleanup_error)

            if attempt < max_retries:
                sleep_seconds = 2 * attempt
                logger.info(
                    "Retrying download in %s seconds (attempt %s/%s)...",
                    sleep_seconds,
                    attempt + 1,
                    max_retries,
                )
                time.sleep(sleep_seconds)
            else:
                logger.error("All download attempts failed.")
                raise


def install_audiosep():
    from ai.ai_runtime.utils.paths import get_models_path

    models_dir = get_models_path()
    audiosep_dir = models_dir / "AudioSep"

    if not audiosep_dir.exists():
        logger.info("Cloning AudioSep into %s...", audiosep_dir)
        try:
            subprocess.run(
                ["git", "clone", "https://github.com/Audio-AGI/AudioSep.git", str(audiosep_dir)],
                check=True,
            )
            logger.info("Clone complete.")
        except subprocess.CalledProcessError as e:
            logger.error("Git clone failed: %s", e)
            return
    else:
        logger.info("AudioSep already exists at %s", audiosep_dir)

    checkpoint_url = "https://huggingface.co/Aisaka/AudioSep/resolve/main/audiosep_base_4M_steps.ckpt"
    checkpoint_dir = audiosep_dir / "checkpoint"
    checkpoint_path = checkpoint_dir / "audiosep_base_4M_steps.ckpt"

    try:
        download_file(checkpoint_url, checkpoint_path)
    except Exception:
        logger.error("Failed to download checkpoint.")
        return

    clap_url = "https://huggingface.co/Aisaka/AudioSep/resolve/main/music_speech_audioset_epoch_15_esc_89.98.pt"
    clap_path = checkpoint_dir / "music_speech_audioset_epoch_15_esc_89.98.pt"

    try:
        download_file(clap_url, clap_path)
    except Exception:
        logger.error("Failed to download CLAP weights.")
        return

    logger.info("\nAudioSep installation complete. You can now use the --universal flag.")


if __name__ == "__main__":
    install_audiosep()
