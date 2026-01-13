"""Unit tests for SemanticDetective, temporal smoothing, and DetectionThread."""

import sys
import time
import numpy as np
import pytest
import tensorflow as tf
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure desktop module is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "desktop" / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "desktop" / "src"))

from training.models.semantic_detective import (
    AdaptiveDutyCycle,
    ConfidenceBuffer,
    MedianSmoother,
    SchmittTrigger,
    SemanticDetective,
)


class FakeYamnet:
    """Deterministic stand-in for tfhub YAMNet to avoid network calls."""

    def __call__(self, waveform):
        # waveform shape: (1, T)
        # Return scores shaped (frames, 521). Use a single frame for simplicity.
        scores = np.zeros((1, 521), dtype=np.float32)
        scores[0, 0] = 0.8  # speech bucket
        scores[0, 310] = 0.1  # wind
        scores[0, 396] = 0.95  # siren/alarm
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


@patch("tensorflow_hub.load", return_value=FakeYamnet())
def test_classify_maps_categories(mock_load, tmp_path: Path):
    class_map = make_class_map(tmp_path)
    detective = SemanticDetective(class_map_path=class_map, enable_median=False)
    audio = np.zeros(16000, dtype=np.float32)

    result = detective.classify(audio, sample_rate=16000)

    raw = result["raw"]
    assert raw["speech"] == pytest.approx(0.8, rel=1e-6)
    assert raw["wind"] == pytest.approx(0.1, rel=1e-6)
    assert raw["siren"] == pytest.approx(0.95, rel=1e-6)
    assert detective.check_safety_override(result["states"]) is True


def test_confidence_buffer_majority_vote():
    buffer = ConfidenceBuffer(window_size=3, threshold=0.5)
    # Below threshold twice, then above twice -> should become True
    outputs = buffer.update({"speech": 0.4})
    assert outputs["speech"] is False
    outputs = buffer.update({"speech": 0.4})
    assert outputs["speech"] is False
    outputs = buffer.update({"speech": 0.7})
    # Only one above-threshold hit so far -> still False
    assert outputs["speech"] is False
    outputs = buffer.update({"speech": 0.8})
    assert outputs["speech"] is True


def test_schmitt_trigger_hysteresis():
    trigger = SchmittTrigger(on_threshold=0.7, off_threshold=0.4)
    assert trigger.update("siren", 0.6) is False  # below on threshold
    assert trigger.update("siren", 0.72) is True  # turn on
    assert trigger.update("siren", 0.5) is True  # stays on
    assert trigger.update("siren", 0.3) is False  # turns off


def test_adaptive_duty_cycle():
    cycle = AdaptiveDutyCycle()
    assert cycle.get_interval(75) == 3.0
    assert cycle.get_interval(35) == 8.0
    assert cycle.get_interval(10) == 15.0


def test_median_smoother():
    smoother = MedianSmoother(window_size=3)
    # First value is just the value itself
    result = smoother.smooth({"speech": 0.8})
    assert result["speech"] == pytest.approx(0.8)
    # Add more values
    smoother.smooth({"speech": 0.2})
    result = smoother.smooth({"speech": 0.5})
    # Median of [0.8, 0.2, 0.5] = 0.5
    assert result["speech"] == pytest.approx(0.5)


def test_confidence_buffer_new_category():
    buffer = ConfidenceBuffer(window_size=3, threshold=0.5)
    # New category should start with empty history
    result = buffer.update({"new_cat": 0.9})
    # Only one hit, needs 2 for stable
    assert result["new_cat"] is False
    result = buffer.update({"new_cat": 0.9})
    # Now has 2 hits
    assert result["new_cat"] is True


@patch("tensorflow_hub.load", return_value=FakeYamnet())
def test_classify_empty_audio_raises(mock_load, tmp_path: Path):
    class_map = make_class_map(tmp_path)
    detective = SemanticDetective(class_map_path=class_map, enable_median=False)
    empty_audio = np.array([], dtype=np.float32)

    with pytest.raises(ValueError, match="empty"):
        detective.classify(empty_audio, sample_rate=16000)


@patch("tensorflow_hub.load", return_value=FakeYamnet())
def test_classify_stereo_audio(mock_load, tmp_path: Path):
    class_map = make_class_map(tmp_path)
    detective = SemanticDetective(class_map_path=class_map, enable_median=False)
    # Stereo audio (samples, 2 channels)
    stereo_audio = np.zeros((16000, 2), dtype=np.float32)

    # Should not raise - stereo is converted to mono
    result = detective.classify(stereo_audio, sample_rate=16000)
    assert "raw" in result


@patch("tensorflow_hub.load", return_value=FakeYamnet())
def test_get_top_detections(mock_load, tmp_path: Path):
    class_map = make_class_map(tmp_path)
    detective = SemanticDetective(class_map_path=class_map, enable_median=False)
    audio = np.zeros(16000, dtype=np.float32)

    result = detective.classify(audio, sample_rate=16000)
    top = detective.get_top_detections(result["smoothed"], n=2)

    assert len(top) == 2
    # siren should be top (0.95), speech second (0.8)
    assert top[0][0] == "siren"
    assert top[1][0] == "speech"


@patch("tensorflow_hub.load", return_value=FakeYamnet())
def test_empty_category_indices(mock_load, tmp_path: Path):
    """Test that empty category indices return 0.0 instead of NaN."""
    yaml_content = """\
categories:
  empty_cat:
    indices: []
    priority: low
    safety_override: false
  speech:
    indices: [0]
    priority: medium
    safety_override: false
"""
    path = tmp_path / "empty_map.yaml"
    path.write_text(yaml_content)

    detective = SemanticDetective(class_map_path=path, enable_median=False)
    audio = np.zeros(16000, dtype=np.float32)
    result = detective.classify(audio, sample_rate=16000)

    assert result["raw"]["empty_cat"] == 0.0
    assert not np.isnan(result["raw"]["empty_cat"])


# ---------------------- DetectionThread Tests ---------------------- #

@patch("tensorflow_hub.load", return_value=FakeYamnet())
def test_detection_thread_init(mock_load, tmp_path: Path):
    """Test DetectionThread initialization."""
    from audio.detection_thread import DetectionThread

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


@patch("tensorflow_hub.load", return_value=FakeYamnet())
def test_detection_thread_stop(mock_load, tmp_path: Path):
    """Test DetectionThread stop mechanism."""
    from audio.detection_thread import DetectionThread

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


@patch("tensorflow_hub.load", return_value=FakeYamnet())
def test_detection_thread_callback_invoked(mock_load, tmp_path: Path):
    """Test that callback is invoked with detection results."""
    from audio.detection_thread import DetectionThread

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


@patch("tensorflow_hub.load", return_value=FakeYamnet())
def test_detection_thread_handles_classification_error(mock_load, tmp_path: Path):
    """Test that classification errors don't crash the thread."""
    from audio.detection_thread import DetectionThread

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
    from audio.detection_thread import DetectionThread

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
