import numpy as np
import pytest
import torch

from ai.ai_runtime.separation import TARGETS, WaveformerSeparator
from ai.ai_runtime.utils.paths import get_waveformer_checkpoint_path, get_waveformer_config_path

CONFIG = get_waveformer_config_path()
CKPT = get_waveformer_checkpoint_path()


def test_missing_assets_error(monkeypatch):
    bad_config = CONFIG.parent / "missing_config.json"
    with pytest.raises(FileNotFoundError):
        WaveformerSeparator(config_path=bad_config, checkpoint_path=CKPT)


def test_invalid_target_error():
    sep = WaveformerSeparator(config_path=CONFIG, checkpoint_path=CKPT, device="cpu")
    audio = np.zeros((160,), dtype=np.float32)
    with pytest.raises(ValueError):
        sep.separate(audio, sample_rate=16_000, targets=["not_a_target"])


def test_resample_and_shape_cpu():
    sep = WaveformerSeparator(config_path=CONFIG, checkpoint_path=CKPT, device="cpu")
    audio = np.zeros((160,), dtype=np.float32)
    out = sep.separate(audio, sample_rate=16_000, targets=TARGETS[:1])
    assert out.shape[0] == audio.shape[0]
    assert out.ndim == 2


def test_query_vector_list_and_tensor():
    sep = WaveformerSeparator(config_path=CONFIG, checkpoint_path=CKPT, device="cpu")
    audio = np.zeros((80,), dtype=np.float32)
    out_list = sep.separate(audio, sample_rate=44_100, targets=TARGETS[:2])
    assert out_list.shape[0] == audio.shape[0]
    vec = torch.zeros(len(TARGETS), dtype=torch.float32)
    vec[0] = 1.0
    out_tensor = sep.separate(audio, sample_rate=44_100, targets=vec)
    assert out_tensor.shape[0] == audio.shape[0]
