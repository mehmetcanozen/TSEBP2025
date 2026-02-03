"""Unit tests for DetectionThread background classification."""

import sys
import time
import numpy as np
import tensorflow as tf
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure training module is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "training") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "training"))
if str(REPO_ROOT / "desktop" / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "desktop" / "src"))

from models.semantic_detective import AdaptiveDutyCycle, SemanticDetective
from audio.detection_thread import DetectionThread


class FakeYamnet:
    """Deterministic stand-in for tfhub YAMNet to avoid network calls."""

    def __call__(self, waveform):
        scores = np.zeros((1, 521), dtype=np.float32)
        scores[0, 0] = 0.8  # speech
        scores[0, 310] = 0.1  # wind
        scores[0, 396] = 0.95  # siren
        return tf.constant(scores), None, None


def make_class_map(tmp_path: Path) -> Path:
    yaml_content = """\
categories:
  speech:
    indices: [0]
    priority: medium
    safety_override: false
  wind:
    indices: [310]
    priority: low
    safety_override: false
  siren:
    indices: [396]
    priority: critical
    safety_override: true
"""
    path = tmp_path / "yamnet_map.yaml"
    path.write_text(yaml_content)
    return path


@patch("models.semantic_detective.hub.load", return_value=FakeYamnet())
def test_detection_thread_init(mock_load, tmp_path: Path):
    """Test DetectionThread initialization."""
    class_map = make_class_map(tmp_path)
    detective = SemanticDetective(class_map_path=class_map)
    get_audio = MagicMock(return_value=None)
    callback = MagicMock()

    thread = DetectionThread(
        get_audio=get_audio,
        detective=detective,
        callback=callback,
        base_interval=1.0,
    )

    assert thread.base_interval == 1.0
    assert thread.detective is detective
    assert thread.daemon is True


@patch("models.semantic_detective.hub.load", return_value=FakeYamnet())
def test_detection_thread_stop(mock_load, tmp_path: Path):
    """Test DetectionThread stop mechanism."""
    class_map = make_class_map(tmp_path)
    detective = SemanticDetective(class_map_path=class_map)
    get_audio = MagicMock(return_value=None)
    callback = MagicMock()

    thread = DetectionThread(
        get_audio=get_audio,
        detective=detective,
        callback=callback,
        base_interval=0.1,
    )

    thread.start()
    time.sleep(0.05)
    thread.stop()
    thread.join(timeout=1.0)

    assert not thread.is_alive()


@patch("models.semantic_detective.hub.load", return_value=FakeYamnet())
def test_detection_thread_callback_invoked(mock_load, tmp_path: Path):
    """Test that callback is invoked with detection results."""
    class_map = make_class_map(tmp_path)
    detective = SemanticDetective(class_map_path=class_map)
    audio = np.zeros(16000, dtype=np.float32)
    get_audio = MagicMock(return_value=(audio, 16000))
    callback = MagicMock()

    thread = DetectionThread(
        get_audio=get_audio,
        detective=detective,
        callback=callback,
        base_interval=0.05,
    )

    thread.start()
    time.sleep(0.2)
    thread.stop()
    thread.join(timeout=1.0)

    # Callback should have been called at least once
    assert callback.call_count >= 1
    # Check payload structure
    payload = callback.call_args[0][0]
    assert "raw" in payload
    assert "smoothed" in payload
    assert "top" in payload
    assert "safety_override" in payload


@patch("models.semantic_detective.hub.load", return_value=FakeYamnet())
def test_detection_thread_handles_classification_error(mock_load, tmp_path: Path):
    """Test that classification errors don't crash the thread."""
    class_map = make_class_map(tmp_path)
    detective = SemanticDetective(class_map_path=class_map)

    # Return invalid audio that will cause an error
    call_count = [0]

    def get_audio_with_error():
        call_count[0] += 1
        if call_count[0] == 1:
            return (np.array([], dtype=np.float32), 16000)  # Empty - will error
        return None

    callback = MagicMock()

    thread = DetectionThread(
        get_audio=get_audio_with_error,
        detective=detective,
        callback=callback,
        base_interval=0.05,
    )

    thread.start()
    time.sleep(0.15)
    thread.stop()
    thread.join(timeout=1.0)

    # Thread should still be stoppable (didn't crash)
    assert not thread.is_alive()


def test_detection_thread_adaptive_interval():
    """Test that adaptive duty cycle affects interval."""
    detective = MagicMock()
    get_audio = MagicMock(return_value=None)
    callback = MagicMock()
    duty_cycle = AdaptiveDutyCycle(normal=1.0, saving=5.0, critical=10.0)

    thread = DetectionThread(
        get_audio=get_audio,
        detective=detective,
        callback=callback,
        duty_cycle=duty_cycle,
        battery_fn=lambda: 75,  # High battery
    )

    assert thread._compute_interval() == 1.0

    # Low battery
    thread.battery_fn = lambda: 15
    assert thread._compute_interval() == 10.0
