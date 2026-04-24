from __future__ import annotations

import numpy as np

from ai.ai_runtime.batch import batch_processor


def test_batch_processor_forwards_codecsep15_options_for_mono_audio(monkeypatch, tmp_path):
    captured: dict = {}

    class FakeSuppressor:
        separator_backend = "codecsep_dnrv2_15cat"

        def suppress(self, **kwargs):
            captured.update(kwargs)
            return np.asarray(kwargs["audio"], dtype=np.float32) * 0.5

    audio = np.linspace(-1.0, 1.0, 16, dtype=np.float32)
    monkeypatch.setattr(batch_processor.sf, "read", lambda *_args, **_kwargs: (audio, 16000))
    monkeypatch.setattr(batch_processor.sf, "write", lambda *_args, **_kwargs: None)

    processor = batch_processor.BatchProcessor(suppressor=FakeSuppressor())
    processor.process_file(
        input_path=tmp_path / "in.wav",
        output_path=tmp_path / "out.wav",
        suppress_categories=["keyboard typing"],
        codecsep_dnrv2_15cat_model_path=str(tmp_path / "codecsep_dnrv2_15cat.pte"),
        codecsep_dnrv2_15cat_runtime="executorch",
        codecsep_dnrv2_15cat_device="cpu",
        codecsep_dnrv2_15cat_realtime_hop_seconds=0.5,
    )

    assert captured["codecsep_dnrv2_15cat_model_path"] == str(
        tmp_path / "codecsep_dnrv2_15cat.pte",
    )
    assert captured["codecsep_dnrv2_15cat_runtime"] == "executorch"
    assert captured["codecsep_dnrv2_15cat_device"] == "cpu"
    assert captured["codecsep_dnrv2_15cat_realtime_hop_seconds"] == 0.5
