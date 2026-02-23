"""
Install AudioSep
Utility script to clone the AudioSep repository and download the required weights.
This simplifies the Phase 3 Universal Extraction setup.
"""

import os
import subprocess
import urllib.request
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def download_file(url: str, dest_path: Path):
    """Download a file with progress tracking."""
    if dest_path.exists():
        logger.info(f"File already exists: {dest_path}")
        return

    logger.info(f"Downloading {url} to {dest_path}...")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        urllib.request.urlretrieve(url, dest_path)
        logger.info("Download complete.")
    except Exception as e:
        logger.error(f"Download failed: {e}")
        if dest_path.exists():
            dest_path.unlink()
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
