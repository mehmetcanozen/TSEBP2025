"""Unit tests for DetectionThread background classification."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import tensorflow as tf

from ai.ai_runtime.detection import AdaptiveDutyCycle, DetectionThread, SemanticDetective


class FakeYamnet:
    """Deterministic stand-in for tfhub YAMNet to avoid network calls."""

    def __call__(self, waveform):
        scores = np.zeros((1, 521), dtype=np.float32)
        scores[0, 0] = 0.8
        scores[0, 310] = 0.1
        scores[0, 396] = 0.95
        return tf.constant(scores), None, None


def make_class_map(tmp_path: Path) -> Path:
    yaml_content = """\
categories:
  speech:
    indices: [0]
    priority: medium
  wind:
    indices: [310]
    priority: low
  siren:
    indices: [396]
    priority: medium
"""
    path = tmp_path / "yamnet_map.yaml"
    path.write_text(yaml_content)
    return path


@patch("ai.ai_runtime.detection.semantic_detective.hub.load", return_value=FakeYamnet())
def test_detection_thread_init(mock_load, tmp_path: Path):
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


@patch("ai.ai_runtime.detection.semantic_detective.hub.load", return_value=FakeYamnet())
def test_detection_thread_stop(mock_load, tmp_path: Path):
    class_map = make_class_map(tmp_path)
    detective = SemanticDetective(class_map_path=class_map)
    thread = DetectionThread(
        get_audio=MagicMock(return_value=None),
        detective=detective,
        callback=MagicMock(),
        base_interval=0.1,
    )
    thread.start()
    time.sleep(0.05)
    thread.stop()
    thread.join(timeout=1.0)
    assert not thread.is_alive()


@patch("ai.ai_runtime.detection.semantic_detective.hub.load", return_value=FakeYamnet())
def test_detection_thread_callback_invoked(mock_load, tmp_path: Path):
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
    assert callback.call_count >= 1
    payload = callback.call_args[0][0]
    assert "raw" in payload
    assert "smoothed" in payload
    assert "top" in payload


@patch("ai.ai_runtime.detection.semantic_detective.hub.load", return_value=FakeYamnet())
def test_detection_thread_handles_classification_error(mock_load, tmp_path: Path):
    class_map = make_class_map(tmp_path)
    detective = SemanticDetective(class_map_path=class_map)
    call_count = [0]

    def get_audio_with_error():
        call_count[0] += 1
        if call_count[0] == 1:
            return (np.array([], dtype=np.float32), 16000)
        return None

    thread = DetectionThread(
        get_audio=get_audio_with_error,
        detective=detective,
        callback=MagicMock(),
        base_interval=0.05,
    )
    thread.start()
    time.sleep(0.15)
    thread.stop()
    thread.join(timeout=1.0)
    assert not thread.is_alive()


def test_detection_thread_adaptive_interval():
    thread = DetectionThread(
        get_audio=MagicMock(return_value=None),
        detective=MagicMock(),
        callback=MagicMock(),
        duty_cycle=AdaptiveDutyCycle(normal=1.0, saving=5.0, critical=10.0),
        battery_fn=lambda: 75,
    )
    assert thread._compute_interval() == 1.0
    thread.battery_fn = lambda: 15
    assert thread._compute_interval() == 10.0
