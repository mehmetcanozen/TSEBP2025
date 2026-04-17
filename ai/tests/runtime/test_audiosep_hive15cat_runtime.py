from __future__ import annotations

import time

import numpy as np

from ai.ai_runtime.audio.recorder_cleaner import BufferedRealtimeSuppressor
from ai.ai_runtime.batch import batch_processor


def test_batch_processor_uses_overlap_add_for_audiosep15(monkeypatch, tmp_path):
    calls: list[np.ndarray] = []
    written: dict = {}

    class FakeSuppressor:
        separator_backend = "audiosep_hive15cat"

        def suppress(self, **kwargs):
            audio = np.asarray(kwargs["audio"], dtype=np.float32)
            calls.append(audio.copy())
            return audio * 0.5

    audio = np.ones(40, dtype=np.float32)
    monkeypatch.setattr(batch_processor.sf, "read", lambda *_args, **_kwargs: (audio, 10))
    monkeypatch.setattr(
        batch_processor.sf,
        "write",
        lambda path, data, sample_rate: written.update(
            {"path": path, "data": np.asarray(data), "sample_rate": sample_rate}
        ),
    )

    processor = batch_processor.BatchProcessor(suppressor=FakeSuppressor())
    processor.process_file(
        input_path=tmp_path / "in.wav",
        output_path=tmp_path / "out.wav",
        suppress_categories=["keyboard typing"],
        chunk_size_seconds=2.0,
    )

    assert len(calls) == 4
    np.testing.assert_allclose(written["data"], np.full_like(audio, 0.5), atol=1e-6)
    assert np.max(np.abs(np.diff(written["data"]))) < 1e-6


def test_batch_processor_output_noise_uses_original_minus_clean_for_audiosep15(monkeypatch, tmp_path):
    class FakeSuppressor:
        separator_backend = "audiosep_hive15cat"

        def suppress(self, **kwargs):
            audio = np.asarray(kwargs["audio"], dtype=np.float32)
            if kwargs.get("return_details"):
                return {
                    "clean_audio": audio * 0.6,
                    "removed_audio": np.full_like(audio, 123.0),
                }
            return audio * 0.6

    audio = np.linspace(-1.0, 1.0, 12, dtype=np.float32)
    monkeypatch.setattr(batch_processor.sf, "read", lambda *_args, **_kwargs: (audio, 12))
    monkeypatch.setattr(batch_processor.sf, "write", lambda *_args, **_kwargs: None)

    processor = batch_processor.BatchProcessor(suppressor=FakeSuppressor())
    stats = processor.process_file(
        input_path=tmp_path / "in.wav",
        output_path=tmp_path / "out.wav",
        suppress_categories=["alarm"],
        chunk_size_seconds=10.0,
        output_noise=True,
    )

    np.testing.assert_allclose(stats["noise_audio"], audio - (audio * 0.6), atol=1e-6)


def test_batch_processor_projects_removed_audio_to_stereo_for_audiosep15(monkeypatch, tmp_path):
    calls: list[np.ndarray] = []
    written: dict = {}

    class FakeSuppressor:
        separator_backend = "audiosep_hive15cat"

        def suppress(self, **kwargs):
            audio = np.asarray(kwargs["audio"], dtype=np.float32)
            calls.append(audio.copy())
            removed = np.full_like(audio, 0.25, dtype=np.float32)
            if kwargs.get("return_details"):
                return {
                    "clean_audio": audio - removed,
                    "removed_audio": removed,
                }
            return audio - removed

    stereo = np.column_stack(
        [
            np.linspace(-1.0, 1.0, 16, dtype=np.float32),
            np.linspace(1.0, -1.0, 16, dtype=np.float32),
        ],
    )

    monkeypatch.setattr(batch_processor.sf, "read", lambda *_args, **_kwargs: (stereo, 16000))

    def fake_write(path, data, sample_rate):
        written["path"] = path
        written["data"] = np.asarray(data)
        written["sample_rate"] = sample_rate

    monkeypatch.setattr(batch_processor.sf, "write", fake_write)

    processor = batch_processor.BatchProcessor(suppressor=FakeSuppressor())
    processor.process_file(
        input_path=tmp_path / "in.wav",
        output_path=tmp_path / "out.wav",
        suppress_categories=["dog barking"],
    )

    assert len(calls) == 1
    np.testing.assert_allclose(calls[0], stereo.mean(axis=1))
    expected = stereo - 0.25
    np.testing.assert_allclose(written["data"], expected, atol=1e-6)


def test_buffered_realtime_suppressor_throttles_and_reuses_gain():
    calls: list[np.ndarray] = []
    fake_time = [0.0]

    def clock() -> float:
        return fake_time[0]

    def suppress_fn(*, audio, sample_rate, **kwargs):
        del sample_rate, kwargs
        audio = np.asarray(audio, dtype=np.float32)
        calls.append(audio.copy())
        return audio * 0.25

    helper = BufferedRealtimeSuppressor(
        suppress_fn=suppress_fn,
        sample_rate=10,
        context_duration=5.0,
        hop_seconds=1.0,
        clock=clock,
    )
    helper.start()
    rolling_buffer = np.ones(50, dtype=np.float32)

    assert helper.submit_if_due(rolling_buffer, suppress_kwargs={}) is True

    deadline = time.monotonic() + 1.0
    while not helper.poll_results():
        assert time.monotonic() < deadline
        time.sleep(0.01)

    clean_chunk, original_chunk = helper.render_chunk(
        rolling_buffer,
        chunk_len=10,
        lookahead_seconds=0.0,
    )
    np.testing.assert_allclose(original_chunk, np.ones(10, dtype=np.float32), atol=1e-6)
    np.testing.assert_allclose(clean_chunk, np.full(10, 0.25, dtype=np.float32), atol=1e-6)

    fake_time[0] = 0.5
    assert helper.submit_if_due(rolling_buffer, suppress_kwargs={}) is False
    fake_time[0] = 1.1
    assert helper.submit_if_due(rolling_buffer, suppress_kwargs={}) is True

    deadline = time.monotonic() + 1.0
    while not helper.poll_results():
        assert time.monotonic() < deadline
        time.sleep(0.01)

    helper.stop()
    assert len(calls) == 2


def test_buffered_realtime_suppressor_falls_back_when_worker_misses_deadline():
    def suppress_fn(*, audio, sample_rate, **kwargs):
        del sample_rate, kwargs
        time.sleep(0.2)
        return np.zeros_like(np.asarray(audio, dtype=np.float32))

    helper = BufferedRealtimeSuppressor(
        suppress_fn=suppress_fn,
        sample_rate=10,
        context_duration=5.0,
        hop_seconds=1.0,
    )
    helper.start()
    rolling_buffer = np.ones(50, dtype=np.float32)

    assert helper.submit_if_due(rolling_buffer, suppress_kwargs={}) is True
    clean_chunk, original_chunk = helper.render_chunk(
        rolling_buffer,
        chunk_len=10,
        lookahead_seconds=0.0,
    )

    np.testing.assert_allclose(clean_chunk, original_chunk, atol=1e-6)
    helper.stop()
