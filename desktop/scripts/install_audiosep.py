"""
Install AudioSep
Utility script to clone the AudioSep repository and download the required weights.
This simplifies the Phase 3 Universal Extraction setup.
"""

import os
import subprocess
import urllib.request
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def download_file(url: str, dest_path: Path, timeout: int = 30, max_retries: int = 3):
    """Download a file with progress tracking, timeout, and basic retry logic."""
    if dest_path.exists():
        logger.info(f"File already exists: {dest_path}")
        return

    logger.info(f"Downloading {url} to {dest_path}...")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    chunk_size = 8192  # 8 KB
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
                                logger.info(f"Download progress: {percent}%")
                                last_reported_percent = percent
                        else:
                            # If total size is unknown, log every additional 10 MB.
                            downloaded_mb = downloaded // (10 * 1024 * 1024)
                            if downloaded_mb > last_reported_mb:
                                logger.info(f"Downloaded approximately {downloaded_mb * 10} MB...")
                                last_reported_mb = downloaded_mb

            logger.info("Download complete.")
            return

        except Exception as e:
            logger.error(f"Download attempt {attempt} failed: {e}")
            if dest_path.exists():
                try:
                    dest_path.unlink()
                except Exception as cleanup_error:
                    logger.warning(f"Failed to remove incomplete file {dest_path}: {cleanup_error}")
            
            if attempt < max_retries:
                # Exponential backoff before retrying
                sleep_seconds = 2 * attempt
                logger.info(f"Retrying download in {sleep_seconds} seconds (attempt {attempt + 1}/{max_retries})...")
                time.sleep(sleep_seconds)
            else:
                logger.error("All download attempts failed.")
                raise


def install_audiosep():
    project_root = Path(__file__).resolve().parents[2]
    models_dir = project_root / "models"
    audiosep_dir = models_dir / "AudioSep"
    
    # 1. Clone AudioSep
    if not audiosep_dir.exists():
        logger.info(f"Cloning AudioSep into {audiosep_dir}...")
        try:
            subprocess.run(
                ["git", "clone", "https://github.com/Audio-AGI/AudioSep.git", str(audiosep_dir)],
                check=True
            )
            logger.info("Clone complete.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Git clone failed: {e}")
            return
    else:
        logger.info(f"AudioSep already exists at {audiosep_dir}")

    # 2. Download Checkpoint
    checkpoint_url = "https://huggingface.co/spaces/badayvedat/AudioSep/resolve/main/checkpoint/audiosep_base_4M_steps.ckpt"
    checkpoint_dir = audiosep_dir / "checkpoint"
    checkpoint_path = checkpoint_dir / "audiosep_base_4M_steps.ckpt"
    
    try:
        download_file(checkpoint_url, checkpoint_path)
    except Exception:
        logger.error("Failed to download checkpoint.")
        return

    logger.info("\n✅ AudioSep installation complete! You can now use the --universal flag.")


if __name__ == "__main__":
    install_audiosep()
