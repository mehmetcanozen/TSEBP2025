"""Tests for CodecSepSeparator (with mocked model to avoid heavy deps)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch
import yaml

from ai.ai_runtime.separation.codecsep_query import CodecSepQueryPlan
from ai.ai_runtime.separation.codecsep.model import CodecSep
from ai.ai_runtime.separation.codecsep_separator import (
    CodecSepSeparator,
    DEFAULT_PROMPTS,
    STEMS,
    TARGET_SAMPLE_RATE,
)
from ai.ai_runtime.utils.paths import (
    get_codecsep_default_run_dir,
    get_codecsep_fixed_category_gate_thresholds_path,
    resolve_codecsep_checkpoint_path,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_fake_model(tracks=("speech", "music", "sfx")):
    """Build a mock that quacks like CodecSep for testing the wrapper."""
    model = MagicMock()
    model.tracks = list(tracks)
    model.track2idx = {t: i for i, t in enumerate(tracks)}
    model.sample_rate = TARGET_SAMPLE_RATE
    model.text_encoder = MagicMock()

    def fake_text_embedding(prompts, use_tensor=True):
        if isinstance(prompts, str):
            prompts = [prompts]
        values = []
        for idx, prompt in enumerate(prompts):
            values.append(
                torch.tensor(
                    [float(idx + 1), float(len(str(prompt).split()))],
                    dtype=torch.float32,
                )
            )
        stacked = torch.stack(values, dim=0)
        return stacked if use_tensor else stacked.numpy()

    model.text_encoder.get_text_embedding = MagicMock(side_effect=fake_text_embedding)

    def fake_evaluate(input_audio_and_prompt, sample_rate=None,
                      output_tracks=None, embedding_overrides=None):
        audio_tensor = input_audio_and_prompt[0]
        B, _, T = audio_tensor.shape
        K = len(output_tracks) if output_tracks else 4
        # Return random but deterministic output
        torch.manual_seed(42)
        return torch.randn(B, K, T) * 0.1

    model.evaluate = MagicMock(side_effect=fake_evaluate)
    return model


def _make_fake_class_id_model():
    """Build a lightweight fixed-category mock model."""
    model = MagicMock()
    model.conditioning_mode = "class_id"
    model.num_classes = 8

    def fake_separate_class_ids(
        input_audio,
        class_ids,
        *,
        target_present=None,
        query_mode=None,
        sample_rate=None,
    ):
        del target_present, query_mode, sample_rate
        outputs = []
        for class_id in class_ids.detach().cpu().tolist():
            scale = 0.05 * (int(class_id) + 1)
            outputs.append(input_audio[0] * scale)
        return torch.stack(outputs, dim=0)

    model.separate_class_ids = MagicMock(side_effect=fake_separate_class_ids)
    return model


def _tiny_codecsep_kwargs(*, conditioning: dict | None = None, clap: dict | None = None) -> dict:
    return {
        "sample_rate": TARGET_SAMPLE_RATE,
        "mode": "single_target",
        "residual_mode": "waveform_subtract",
        "tracks": ["target"],
        "enc_params": {"name": "DACEncoder", "d_model": 8, "strides": [2, 2]},
        "dec_params": {"name": "DACDecoder", "d_model": 32, "strides": [2, 2]},
        "transformer_params": {
            "name": "Transformer",
            "d_model": 256,
            "nhead": 8,
            "dim_feedforward": 512,
            "num_layers": 2,
            "dropout": 0.0,
            "batch_first": True,
        },
        "separator_params": {"name": "Separator", "num_spks": 1, "channels": 32, "block_channels": 256},
        "film_clip": 5.0,
        "normalize_prompt_embeddings": True,
        "prompt_embed_eps": 1.0e-6,
        "conditioning": conditioning
        or {
            "mode": "class_id",
            "variant": "adaln_zero",
            "condition_size": 8,
            "num_classes": 4,
            "zero_for_absent": True,
            "use_zero_for_null": True,
            "dropout_prob": 0.0,
            "adaln_gate_bias": 0.001,
        },
        "num_classes": 4,
        "clap": clap or {},
        "pretrain": {},
    }


class TestCodecSepSeparatorInit:

    def test_default_device_selection(self):
        sep = CodecSepSeparator.__new__(CodecSepSeparator)
        dev = sep._auto_device()
        assert dev.type in ("cpu", "cuda")

    def test_default_prompts(self):
        assert "speech" in DEFAULT_PROMPTS
        assert "music" in DEFAULT_PROMPTS
        assert "sfx" in DEFAULT_PROMPTS

    def test_stems_tuple(self):
        assert STEMS == ("speech", "music", "sfx")

    def test_default_checkpoint_source_is_clean_dnr_bundle(self):
        sep = CodecSepSeparator()
        assert sep.checkpoint_path == get_codecsep_default_run_dir()

    def test_missing_checkpoint_raises(self, tmp_path):
        sep = CodecSepSeparator(
            checkpoint_path=tmp_path / "nonexistent.pt",
        )
        with pytest.raises(FileNotFoundError, match="CodecSep checkpoint"):
            sep._lazy_load_model()

    def test_run_dir_resolution_prefers_ckpt_best_pytorch_bin(self, tmp_path):
        run_dir = tmp_path / "CodecSep_DNR_USS_Weights"
        best_dir = run_dir / "ckpt_best"
        final_dir = run_dir / "ckpt_final"
        best_dir.mkdir(parents=True)
        final_dir.mkdir(parents=True)
        best_file = best_dir / "pytorch_model.bin"
        final_file = final_dir / "ckpt_model_final.pth"
        best_file.write_bytes(b"best")
        final_file.write_bytes(b"final")

        assert resolve_codecsep_checkpoint_path(run_dir) == best_file

    def test_run_dir_resolution_prefers_v5_gate_pass_before_best_screen(self, tmp_path):
        run_dir = tmp_path / "CodecSep_Hive_V5_50K_Pilot_Run1"
        gate_pass_dir = run_dir / "ckpt_gate_pass"
        best_screen_dir = run_dir / "ckpt_best_screen"
        gate_pass_dir.mkdir(parents=True)
        best_screen_dir.mkdir(parents=True)
        gate_pass_file = gate_pass_dir / "pytorch_model.bin"
        best_screen_file = best_screen_dir / "pytorch_model.bin"
        gate_pass_file.write_bytes(b"gate-pass")
        best_screen_file.write_bytes(b"best-screen")

        assert resolve_codecsep_checkpoint_path(run_dir) == gate_pass_file

    def test_explicit_v5_checkpoint_family_dir_resolves_pytorch_model_bin(self, tmp_path):
        checkpoint_dir = tmp_path / "ckpt_best_screen"
        checkpoint_dir.mkdir(parents=True)
        checkpoint_file = checkpoint_dir / "pytorch_model.bin"
        checkpoint_file.write_bytes(b"best-screen")

        assert resolve_codecsep_checkpoint_path(checkpoint_dir) == checkpoint_file

    def test_run_dir_resolution_falls_back_to_ckpt_final(self, tmp_path):
        run_dir = tmp_path / "CodecSep_DNR_USS_Weights"
        final_dir = run_dir / "ckpt_final"
        final_dir.mkdir(parents=True)
        final_file = final_dir / "ckpt_model_final.pth"
        final_file.write_bytes(b"final")

        assert resolve_codecsep_checkpoint_path(run_dir) == final_file

    def test_lazy_load_uses_run_dir_config_for_model_init(self, tmp_path):
        run_dir = tmp_path / "CodecSep_DNR_USS_Weights"
        hydra_dir = run_dir / ".hydra"
        best_dir = run_dir / "ckpt_best"
        hydra_dir.mkdir(parents=True)
        best_dir.mkdir(parents=True)
        checkpoint_file = best_dir / "pytorch_model.bin"
        checkpoint_file.write_bytes(b"dummy")
        with (hydra_dir / "config.yaml").open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                {
                    "sampling_rate": 16000,
                    "model": {
                        "codecsep_params": {
                            "name": "CodecSep",
                            "latent_dim": 256,
                            "tracks": ["speech", "music", "sfx"],
                            "enc_params": {"d_model": 32, "strides": [2, 4, 5, 8]},
                            "dec_params": {"d_model": 512, "strides": [8, 5, 4, 2]},
                            "transformer_params": {
                                "d_model": 128,
                                "nhead": 4,
                                "dim_feedforward": 256,
                                "num_layers": 2,
                                "batch_first": True,
                            },
                            "separator_params": {"channels": 256, "block_channels": 64},
                        },
                    },
                },
                f,
            )

        class DummyCodecSep:
            def __init__(self, sample_rate, latent_dim=None, tracks=None,
                         enc_params=None, dec_params=None,
                         transformer_params=None, separator_params=None,
                         conditioning=None, num_classes=None, clap=None):
                self.sample_rate = sample_rate
                self.latent_dim = latent_dim
                self.tracks = list(tracks or STEMS)
                self.track2idx = {t: i for i, t in enumerate(self.tracks)}
                self.enc_params = enc_params
                self.dec_params = dec_params
                self.transformer_params = transformer_params
                self.separator_params = separator_params
                self.conditioning = conditioning
                self.num_classes = num_classes
                self.clap = clap

            def load_state_dict(self, state_dict, strict=False):
                self.state_dict = state_dict

            def to(self, device):
                self.device = device
                return self

            def eval(self):
                return self

        with patch.object(CodecSepSeparator, "_resolve_model_class", return_value=DummyCodecSep):
            with patch("torch.load", return_value={}):
                with patch("torch.quantization.quantize_dynamic", side_effect=lambda model, *_args, **_kwargs: model):
                    sep = CodecSepSeparator(checkpoint_path=run_dir, device="cpu")
                    sep._lazy_load_model()

        assert sep.resolved_checkpoint_path == checkpoint_file
        assert sep._model is not None
        assert sep._model.latent_dim == 256
        assert sep._model.separator_params == {"channels": 256, "block_channels": 64}

    def test_runtime_model_loads_json_class_conditioning_init(self, tmp_path):
        init_path = tmp_path / "conditioning_init.json"
        init_path.write_text(
            json.dumps(
                {
                    "version": "fixed_category_embedding_init_v1",
                    "embedding": [[1.0, 2.0], [3.0, 4.0]],
                }
            ),
            encoding="utf-8",
        )
        model = CodecSep.__new__(CodecSep)
        torch.nn.Module.__init__(model)
        model.class_embedding = torch.nn.Embedding(2, 2)
        model.conditioning_cfg = {"embedding_init_path": str(init_path)}

        CodecSep._load_class_conditioning_init(model)

        assert torch.allclose(
            model.class_embedding.weight.detach(),
            torch.tensor([[1.0, 2.0], [3.0, 4.0]], dtype=torch.float32),
        )

    def test_lazy_load_rejects_core_checkpoint_mismatches(self, tmp_path):
        run_dir = tmp_path / "CodecSep_DNR_USS_Weights"
        hydra_dir = run_dir / ".hydra"
        best_dir = run_dir / "ckpt_best"
        hydra_dir.mkdir(parents=True)
        best_dir.mkdir(parents=True)
        checkpoint_file = best_dir / "pytorch_model.bin"
        checkpoint_file.write_bytes(b"dummy")
        with (hydra_dir / "config.yaml").open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                {
                    "sampling_rate": 16000,
                    "model": {
                        "codecsep_params": {
                            "name": "CodecSep",
                            "mode": "single_target",
                            "residual_mode": "waveform_subtract",
                            "tracks": ["target"],
                            "conditioning": {
                                "mode": "class_id",
                                "variant": "adaln_zero",
                                "condition_size": 8,
                                "num_classes": 4,
                            },
                            "enc_params": {"d_model": 8, "strides": [2, 2]},
                            "dec_params": {"d_model": 32, "strides": [2, 2]},
                            "transformer_params": {
                                "d_model": 16,
                                "nhead": 4,
                                "dim_feedforward": 32,
                                "num_layers": 2,
                                "batch_first": True,
                            },
                            "separator_params": {"channels": 32, "block_channels": 16},
                        },
                    },
                },
                f,
            )

        class DummyCodecSep:
            def __init__(self, sample_rate, tracks=None, conditioning=None, **kwargs):
                self.sample_rate = sample_rate
                self.tracks = list(tracks or ["target"])
                self.conditioning = conditioning
                self.kwargs = kwargs

            def load_state_dict(self, state_dict, strict=False):
                del state_dict, strict
                return (["separator.masker.weight"], [])

            def to(self, device):
                self.device = device
                return self

            def eval(self):
                return self

        with patch.object(CodecSepSeparator, "_resolve_model_class", return_value=DummyCodecSep):
            with patch("torch.load", return_value={}):
                sep = CodecSepSeparator(checkpoint_path=run_dir, device="cpu")
                with pytest.raises(RuntimeError, match="missing core conditioning/separator weights"):
                    sep._lazy_load_model()

    def test_lazy_load_accepts_legacy_additive_film_checkpoint(self, tmp_path):
        run_dir = tmp_path / "CodecSep_DNR_USS_Weights"
        hydra_dir = run_dir / ".hydra"
        best_dir = run_dir / "ckpt_best"
        hydra_dir.mkdir(parents=True)
        best_dir.mkdir(parents=True)
        checkpoint_file = best_dir / "pytorch_model.bin"
        checkpoint_file.write_bytes(b"dummy")
        with (hydra_dir / "config.yaml").open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                {
                    "sampling_rate": 16000,
                    "model": {
                        "codecsep_params": {
                            "name": "CodecSep",
                            "tracks": ["speech", "music", "sfx"],
                            "enc_params": {"d_model": 32, "strides": [2, 4, 5, 8]},
                            "dec_params": {"d_model": 512, "strides": [8, 5, 4, 2]},
                            "transformer_params": {
                                "d_model": 128,
                                "nhead": 4,
                                "dim_feedforward": 256,
                                "num_layers": 2,
                                "batch_first": True,
                            },
                            "separator_params": {"channels": 256, "block_channels": 64},
                        },
                    },
                },
                f,
            )

        class DummyCodecSep:
            conditioning_mode = "prompt"
            num_classes = 0

            def __init__(self, sample_rate, tracks=None, conditioning=None, **kwargs):
                self.sample_rate = sample_rate
                self.tracks = list(tracks or ["target"])
                self.conditioning = conditioning
                self.kwargs = kwargs

            def load_state_dict(self, state_dict, strict=False):
                del state_dict, strict
                return (
                    [
                        "film.gamma1.weight",
                        "film.gamma1.bias",
                        "film.block->layers->0->gamma1.weight",
                        "film.block->layers->0->gamma1.bias",
                        "film.block->layers->0->gamma2.weight",
                        "film.block->layers->0->gamma2.bias",
                    ],
                    [],
                )

            def to(self, device):
                self.device = device
                return self

            def eval(self):
                return self

        legacy_state_dict = {
            "film.beta1.weight": torch.zeros(1),
            "film.beta1.bias": torch.zeros(1),
            "film.beta2.weight": torch.zeros(1),
            "film.beta2.bias": torch.zeros(1),
        }

        with patch.object(CodecSepSeparator, "_resolve_model_class", return_value=DummyCodecSep):
            with patch("torch.load", return_value={"state_dict": legacy_state_dict}):
                sep = CodecSepSeparator(checkpoint_path=run_dir, device="cpu")
                sep._lazy_load_model()
                assert isinstance(sep._model, DummyCodecSep)


class TestCodecSepRuntimeParity:

    def test_runtime_model_exposes_expected_fixed_category_surface(self):
        runtime_model = CodecSep(**_tiny_codecsep_kwargs())
        assert runtime_model.conditioning_mode == "class_id"
        assert runtime_model.mode == "single_target"
        assert runtime_model.conditioning_zero_for_absent is True
        assert runtime_model.conditioning_zero_for_null is True
        assert any(key.startswith("film.") for key in runtime_model.state_dict().keys())
        assert runtime_model.class_embedding is not None

    def test_runtime_model_distinguishes_null_and_absent_zeroing(self):
        model = CodecSep(
            **_tiny_codecsep_kwargs(
                conditioning={
                    "mode": "class_id",
                    "variant": "adaln_zero",
                    "condition_size": 8,
                    "num_classes": 4,
                    "zero_for_absent": False,
                    "use_zero_for_null": True,
                    "dropout_prob": 0.0,
                    "adaln_gate_bias": 0.001,
                }
            )
        )
        with torch.no_grad():
            model.class_embedding.weight.copy_(
                torch.tensor(
                    [
                        [0.0] * 8,
                        [1.0] * 8,
                        [2.0] * 8,
                        [3.0] * 8,
                    ],
                    dtype=torch.float32,
                )
            )

        embeddings = model._encode_class_id_batch(
            torch.tensor([1, 2], dtype=torch.long),
            target_present=torch.tensor([False, True], dtype=torch.bool),
            query_mode=["absent", "null"],
        )

        assert torch.count_nonzero(embeddings[0]).item() == 8
        assert torch.count_nonzero(embeddings[1]).item() == 0

    def test_runtime_prompt_model_uses_embedding_overrides(self):
        class DummyTextEncoder:
            def __init__(self):
                self.calls = 0

            def parameters(self):
                return []

            def get_text_embedding(self, texts, use_tensor=True):
                del texts
                self.calls += 1
                return torch.zeros((1, 8), dtype=torch.float32) if use_tensor else np.zeros((1, 8), dtype=np.float32)

        kwargs = _tiny_codecsep_kwargs(
            conditioning={
                "mode": "prompt",
                "variant": "adaln_zero",
                "condition_size": 8,
                "zero_for_absent": True,
                "use_zero_for_null": False,
                "dropout_prob": 0.0,
                "adaln_gate_bias": 0.001,
            },
            clap={},
        )
        kwargs.pop("num_classes", None)
        dummy_text_encoder = DummyTextEncoder()

        with patch.object(CodecSep, "_build_text_encoder", return_value=dummy_text_encoder):
            model = CodecSep(**kwargs)

        embeddings = model._build_track_embeddings(
            prompt={
                "target": ["sound effects"],
            },
            batch_size=1,
            embedding_overrides={
                "target": torch.full((8,), 3.0),
            },
        )

        assert dummy_text_encoder.calls == 0
        assert set(embeddings.keys()) == {"target"}
        assert embeddings["target"].shape == (1, 8)
        assert float(embeddings["target"][0, 0]) == pytest.approx(3.0)

    def test_fixed_category_threshold_path_uses_v2(self):
        assert get_codecsep_fixed_category_gate_thresholds_path().name == "gate_thresholds_v2.json"

    def test_fixed_category_catalog_rejects_stale_threshold_versions(self):
        from ai.ai_runtime.utils.codecsep import FixedCategoryRuntimeCatalog

        with pytest.raises(ValueError, match="gate_thresholds_v2"):
            FixedCategoryRuntimeCatalog(
                identity_payload={},
                mapping_payload={},
                threshold_payload={"version": "gate_thresholds_v1", "thresholds": {}},
            )


class TestCodecSepSeparatorSeparate:

    @pytest.fixture(autouse=True)
    def _patch_model(self):
        """Patch lazy loading to inject our fake model."""
        self.fake_model = _make_fake_model()
        with patch.object(CodecSepSeparator, "_lazy_load_model"):
            yield

    def _make_sep(self):
        sep = CodecSepSeparator(checkpoint_path=Path("dummy.pt"))
        sep._model = self.fake_model
        return sep

    def test_separate_returns_numpy(self):
        sep = self._make_sep()
        audio = np.random.randn(16000).astype(np.float32)
        out = sep.separate(audio, sample_rate=TARGET_SAMPLE_RATE, stems=["sfx"])
        assert isinstance(out, np.ndarray)

    def test_separate_shape_mono(self):
        sep = self._make_sep()
        audio = np.random.randn(16000).astype(np.float32)
        out = sep.separate(audio, sample_rate=TARGET_SAMPLE_RATE, stems=["sfx"])
        assert out.ndim == 1
        assert out.shape[0] == audio.shape[0]

    def test_separate_stems_returns_dict(self):
        sep = self._make_sep()
        audio = np.random.randn(16000).astype(np.float32)
        result = sep.separate_stems(audio, sample_rate=TARGET_SAMPLE_RATE)
        assert isinstance(result, dict)
        assert set(result.keys()) == set(STEMS)
        for v in result.values():
            assert isinstance(v, np.ndarray)

    def test_separate_stems_applies_mag_normalization(self):
        model = MagicMock()
        model.tracks = list(STEMS)
        model.track2idx = {stem: idx for idx, stem in enumerate(STEMS)}

        def fake_evaluate(input_audio_and_prompt, sample_rate=None, output_tracks=None, embedding_overrides=None):
            audio_tensor = input_audio_and_prompt[0]
            _, _, num_samples = audio_tensor.shape
            mix = torch.zeros((1, 1, num_samples), dtype=torch.float32)
            speech = torch.full((1, 1, num_samples), 0.1, dtype=torch.float32)
            music = torch.full((1, 1, num_samples), 0.2, dtype=torch.float32)
            sfx = torch.full((1, 1, num_samples), 0.3, dtype=torch.float32)
            return torch.cat([mix, speech, music, sfx], dim=1)

        model.evaluate = MagicMock(side_effect=fake_evaluate)

        class FakeNormalizer:
            def __call__(self, mix, signal_sep):
                return signal_sep * 2.0

        with patch.object(CodecSepSeparator, "_lazy_load_model"):
            sep = CodecSepSeparator(checkpoint_path=Path("dummy.pt"))
            sep._model = model
            with patch.object(sep, "_get_mag_normalizer", return_value=FakeNormalizer()):
                result = sep.separate_stems(
                    np.ones(16000, dtype=np.float32),
                    sample_rate=TARGET_SAMPLE_RATE,
                    stems=["speech", "sfx"],
                )

        np.testing.assert_allclose(result["speech"], np.full(16000, 0.2, dtype=np.float32))
        np.testing.assert_allclose(result["sfx"], np.full(16000, 0.6, dtype=np.float32))

    def test_separate_multi_query(self):
        sep = self._make_sep()
        audio = np.random.randn(16000).astype(np.float32)
        groups = [["speech"], ["sfx", "music"]]
        results = sep.separate_multi_query(
            audio, sample_rate=TARGET_SAMPLE_RATE, stem_groups=groups,
        )
        assert len(results) == 2
        assert all(isinstance(r, np.ndarray) for r in results)
        assert self.fake_model.evaluate.call_count == 1

    def test_prompt_overrides_are_forwarded(self):
        sep = self._make_sep()
        audio = np.random.randn(16000).astype(np.float32)
        sep.separate_stems(
            audio,
            sample_rate=TARGET_SAMPLE_RATE,
            stems=["sfx"],
            prompt_overrides={"sfx": ["dog barking", "cat meowing"]},
        )
        args, kwargs = self.fake_model.evaluate.call_args
        prompts = args[0][1]
        assert prompts[self.fake_model.track2idx["speech"]] == DEFAULT_PROMPTS["speech"]
        assert prompts[self.fake_model.track2idx["sfx"]] == ["dog barking, cat meowing"]
        assert kwargs["output_tracks"] == ["mix", "speech", "music", "sfx"]

    def test_resampling_path(self):
        """Verify audio at 44100 Hz is resampled to 16 kHz internally."""
        sep = self._make_sep()
        audio = np.random.randn(44100).astype(np.float32)
        out = sep.separate(audio, sample_rate=44100, stems=["sfx"])
        assert isinstance(out, np.ndarray)
        # Output should be close to original length at 44100
        assert abs(out.shape[0] - 44100) < 100

    def test_unknown_stem_warns(self):
        sep = self._make_sep()
        audio = np.random.randn(16000).astype(np.float32)
        out = sep.separate(audio, sample_rate=TARGET_SAMPLE_RATE,
                           stems=["nonexistent"])
        # Should return zeros when no valid stems found
        assert np.allclose(out, 0.0)

    def test_build_target_embedding_uses_negative_query_offset(self):
        sep = self._make_sep()

        class FakeTextEncoder:
            @staticmethod
            def get_text_embedding(prompts, use_tensor=True):
                values = []
                for prompt in prompts:
                    if "dog" in prompt or "bark" in prompt:
                        values.append(torch.tensor([2.0, 0.0], dtype=torch.float32))
                    elif "speech" in prompt:
                        values.append(torch.tensor([0.0, 2.0], dtype=torch.float32))
                    else:
                        values.append(torch.tensor([1.0, 1.0], dtype=torch.float32))
                return torch.stack(values, dim=0)

        sep._model.text_encoder = FakeTextEncoder()
        positive = CodecSepQueryPlan(
            target_prompts=["dog barking"],
            preferred_slot="sfx",
        )
        negative = CodecSepQueryPlan(
            target_prompts=["dog barking"],
            negative_prompts=["speech, talking, voice"],
            preferred_slot="sfx",
        )

        positive_embedding = sep._build_target_embedding(positive)
        negative_embedding = sep._build_target_embedding(negative)

        assert positive_embedding.shape == negative_embedding.shape == (1, 2)
        assert not torch.allclose(positive_embedding, negative_embedding)

    def test_query_plan_normalized_preserves_multiple_prompt_variants(self):
        plan = CodecSepQueryPlan(
            target_prompts=[
                "a dog barking loudly",
                "canine vocalization, an animal sound",
            ],
            negative_prompts=[
                "speech, talking, voice",
                "music, musical instruments",
            ],
            preferred_slot="sfx",
        ).normalized()

        assert plan.target_prompts == [
            "a dog barking loudly",
            "canine vocalization, an animal sound",
        ]
        assert plan.negative_prompts == [
            "speech, talking, voice",
            "music, musical instruments",
        ]

    def test_query_prefers_higher_scored_alternate_slot(self):
        sep = self._make_sep()
        audio = np.ones(16000, dtype=np.float32)
        plan = CodecSepQueryPlan(
            target_prompts=["bell chimes"],
            preferred_slot="sfx",
            alternate_slots=["music"],
            mode="experimental_search",
            query_strategy="slot_search",
        )

        def fake_run_query_candidate(**kwargs):
            target_slot = kwargs["target_slot"]
            target_audio = np.full_like(audio, 0.5 if target_slot == "music" else 0.25)
            score = MagicMock()
            score.slot = target_slot
            score.target_score = 0.9 if target_slot == "music" else 0.6
            score.preserve_score = 0.0
            score.mixture_score = 1.0
            score.total_score = 1.2 if target_slot == "music" else 0.8
            score.strategy = kwargs["strategy_tag"]
            return {
                "target_audio": target_audio,
                "raw_outputs": {"speech": audio * 0.3, "music": audio * 0.2, "sfx": audio * 0.5},
                "normalized_outputs": {"speech": audio * 0.3, "music": audio * 0.2, "sfx": audio * 0.5},
                "score": score,
            }

        with patch.object(sep, "_run_query_candidate", side_effect=fake_run_query_candidate):
            with patch.object(sep, "_build_clean_audio", return_value=(audio * 0.8, "subtract_target")):
                result = sep.query(audio, TARGET_SAMPLE_RATE, plan)

        assert result.selected_slot == "music"
        assert result.candidate_scores["music"].total_score > result.candidate_scores["sfx"].total_score

    def test_query_audiocaps_native_uses_fixed_slot_without_clap_search(self):
        sep = self._make_sep()
        audio = np.ones(16000, dtype=np.float32)
        plan = CodecSepQueryPlan(
            target_prompts=["keyboard typing"],
            preferred_slot="sfx",
            mode="audiocaps_native",
        )

        with patch.object(sep, "_get_clap_scorer", side_effect=AssertionError("CLAP scorer should stay unused")):
            result = sep.query(audio, TARGET_SAMPLE_RATE, plan)

        assert result.selected_slot == "sfx"
        assert result.score.strategy == "audiocaps_native"
        assert result.chosen_policy == "subtract_target"
        assert set(result.normalized_outputs.keys()) == set(STEMS)

    def test_query_audiocaps_native_uses_target_embedding_override(self):
        sep = self._make_sep()
        audio = np.ones(16000, dtype=np.float32)
        plan = CodecSepQueryPlan(
            target_prompts=[
                "a dog barking loudly",
                "canine vocalization, an animal sound",
            ],
            preferred_slot="sfx",
            mode="audiocaps_native",
        )

        sep.query(audio, TARGET_SAMPLE_RATE, plan)

        _args, kwargs = self.fake_model.evaluate.call_args
        embedding_overrides = kwargs["embedding_overrides"]
        assert "sfx" in embedding_overrides
        assert tuple(embedding_overrides["sfx"].shape) == (1, 2)

    def test_separate_stems_restores_original_scale_after_input_normalization(self):
        model = MagicMock()
        model.tracks = list(STEMS)
        model.track2idx = {stem: idx for idx, stem in enumerate(STEMS)}
        model.text_encoder = MagicMock()
        model.text_encoder.get_text_embedding = MagicMock(
            return_value=torch.tensor([[1.0, 1.0]], dtype=torch.float32)
        )

        def fake_evaluate(input_audio_and_prompt, sample_rate=None, output_tracks=None, embedding_overrides=None):
            audio_tensor = input_audio_and_prompt[0]
            speech = audio_tensor * 0.1
            music = audio_tensor * 0.2
            sfx = audio_tensor * 0.3
            mix = torch.zeros_like(audio_tensor)
            return torch.cat([mix, speech, music, sfx], dim=1)

        model.evaluate = MagicMock(side_effect=fake_evaluate)

        class IdentityNormalizer:
            def __call__(self, mix, signal_sep):
                return signal_sep

        with patch.object(CodecSepSeparator, "_lazy_load_model"):
            sep = CodecSepSeparator(checkpoint_path=Path("dummy.pt"))
            sep._model = model
            sep._peak_norm_gain = 0.95
            with patch.object(
                sep,
                "_apply_inference_normalization",
                side_effect=lambda tensor: (tensor * 2.0, torch.full((1, 1, 1), 2.0)),
            ):
                with patch.object(sep, "_get_mag_normalizer", return_value=IdentityNormalizer()):
                    result = sep.separate_stems(
                        np.ones(16000, dtype=np.float32),
                        sample_rate=TARGET_SAMPLE_RATE,
                        stems=["speech", "music", "sfx"],
                    )

        np.testing.assert_allclose(result["speech"], np.full(16000, 0.1, dtype=np.float32))
        np.testing.assert_allclose(result["music"], np.full(16000, 0.2, dtype=np.float32))
        np.testing.assert_allclose(result["sfx"], np.full(16000, 0.3, dtype=np.float32))


class TestCodecSepSeparatorFixedCategory:

    @pytest.fixture(autouse=True)
    def _patch_model(self):
        self.fake_model = _make_fake_class_id_model()
        with patch.object(CodecSepSeparator, "_lazy_load_model"):
            yield

    def _make_sep(self):
        sep = CodecSepSeparator(checkpoint_path=Path("dummy.pt"))
        sep._model = self.fake_model
        sep._conditioning_mode = "class_id"
        sep._num_classes = 8
        return sep

    def test_separate_class_ids_returns_targets_and_merge_bundle(self):
        sep = self._make_sep()
        audio = np.ones(16000, dtype=np.float32)

        bundle = sep.separate_class_id_bundle(
            audio=audio,
            sample_rate=TARGET_SAMPLE_RATE,
            class_ids=[2, 4],
            aggressiveness=1.5,
        )

        assert bundle["selected_class_ids"] == [2, 4]
        assert set(bundle["targets"].keys()) == {2, 4}
        assert bundle["merged_target"].shape == audio.shape
        assert bundle["clean_audio"].shape == audio.shape
        assert bundle["merge_policy"] in {"wiener_mask", "sum", "wiener_mask_passthrough"}
        assert self.fake_model.separate_class_ids.call_count == 1

    def test_prompt_path_rejects_fixed_category_checkpoint(self):
        sep = self._make_sep()
        audio = np.ones(16000, dtype=np.float32)

        with pytest.raises(RuntimeError, match="Use separate_class_ids"):
            sep.separate_stems(audio, sample_rate=TARGET_SAMPLE_RATE)


class TestWienerMaskReconstruction:
    """Tests for the Wiener soft mask reconstruction policy."""

    @pytest.fixture(autouse=True)
    def _patch_model(self):
        self.fake_model = _make_fake_model()
        with patch.object(CodecSepSeparator, "_lazy_load_model"):
            yield

    def _make_sep(self):
        sep = CodecSepSeparator(checkpoint_path=Path("dummy.pt"))
        sep._model = self.fake_model
        return sep

    def test_build_clean_audio_dispatches_wiener(self):
        """Policy 'wiener_mask' routes to _build_clean_audio_wiener."""
        sep = self._make_sep()
        sr = TARGET_SAMPLE_RATE
        duration = 1.0
        n = int(sr * duration)
        t = np.linspace(0, duration, n, dtype=np.float32)

        original = np.sin(2 * np.pi * 440 * t) + 0.3 * np.sin(2 * np.pi * 4000 * t)
        outputs = {
            "speech": np.sin(2 * np.pi * 440 * t).astype(np.float32),
            "music": np.zeros(n, dtype=np.float32),
            "sfx": (0.3 * np.sin(2 * np.pi * 4000 * t)).astype(np.float32),
        }

        clean, policy = sep._build_clean_audio(
            original_audio=original.astype(np.float32),
            normalized_outputs=outputs,
            target_slot="sfx",
            aggressiveness=2.0,
            policy="wiener_mask",
        )
        assert policy == "wiener_mask"
        assert clean.shape == original.shape
        assert clean.dtype == np.float32

    def test_wiener_mask_suppresses_target_frequency(self):
        """Wiener mask should reduce energy in the target stem's frequency band."""
        sep = self._make_sep()
        sr = TARGET_SAMPLE_RATE
        duration = 1.0
        n = int(sr * duration)
        t = np.linspace(0, duration, n, dtype=np.float32)

        # Mix: speech at 440 Hz + SFX at 4000 Hz
        speech_signal = np.sin(2 * np.pi * 440 * t).astype(np.float32)
        sfx_signal = (0.5 * np.sin(2 * np.pi * 4000 * t)).astype(np.float32)
        original = speech_signal + sfx_signal

        outputs = {
            "speech": speech_signal.copy(),
            "music": np.zeros(n, dtype=np.float32),
            "sfx": sfx_signal.copy(),
        }

        clean, policy = sep._build_clean_audio_wiener(
            original_audio=original,
            normalized_outputs=outputs,
            target_slot="sfx",
            aggressiveness=2.0,
        )

        # Compute energy around 4000 Hz in original vs clean
        from scipy import signal as scipy_signal
        _, _, Z_orig = scipy_signal.stft(original, nperseg=2048)
        _, _, Z_clean = scipy_signal.stft(clean, nperseg=2048)

        # Find bin closest to 4000 Hz
        freqs = np.fft.rfftfreq(2048, d=1.0 / sr)
        sfx_bin = np.argmin(np.abs(freqs - 4000))

        orig_sfx_energy = np.mean(np.abs(Z_orig[sfx_bin]) ** 2)
        clean_sfx_energy = np.mean(np.abs(Z_clean[sfx_bin]) ** 2)

        # SFX energy should be significantly reduced
        assert clean_sfx_energy < 0.5 * orig_sfx_energy, (
            f"SFX energy not reduced enough: {clean_sfx_energy:.4f} vs {orig_sfx_energy:.4f}"
        )

    def test_wiener_mask_preserves_wanted_frequency(self):
        """Wiener mask should preserve energy in the wanted stems' frequency bands."""
        sep = self._make_sep()
        sr = TARGET_SAMPLE_RATE
        duration = 1.0
        n = int(sr * duration)
        t = np.linspace(0, duration, n, dtype=np.float32)

        speech_signal = np.sin(2 * np.pi * 440 * t).astype(np.float32)
        sfx_signal = (0.5 * np.sin(2 * np.pi * 4000 * t)).astype(np.float32)
        original = speech_signal + sfx_signal

        outputs = {
            "speech": speech_signal.copy(),
            "music": np.zeros(n, dtype=np.float32),
            "sfx": sfx_signal.copy(),
        }

        clean, _ = sep._build_clean_audio_wiener(
            original_audio=original,
            normalized_outputs=outputs,
            target_slot="sfx",
            aggressiveness=2.0,
        )

        from scipy import signal as scipy_signal
        _, _, Z_orig = scipy_signal.stft(original, nperseg=2048)
        _, _, Z_clean = scipy_signal.stft(clean, nperseg=2048)

        freqs = np.fft.rfftfreq(2048, d=1.0 / sr)
        speech_bin = np.argmin(np.abs(freqs - 440))

        orig_speech_energy = np.mean(np.abs(Z_orig[speech_bin]) ** 2)
        clean_speech_energy = np.mean(np.abs(Z_clean[speech_bin]) ** 2)

        # Speech energy should be mostly preserved (>70%)
        assert clean_speech_energy > 0.7 * orig_speech_energy, (
            f"Speech energy damaged: {clean_speech_energy:.4f} vs {orig_speech_energy:.4f}"
        )

    def test_wiener_mask_passthrough_on_silent_stems(self):
        """If stems have near-zero energy, return original audio unchanged."""
        sep = self._make_sep()
        n = 16000
        original = np.random.randn(n).astype(np.float32)
        outputs = {
            "speech": np.zeros(n, dtype=np.float32),
            "music": np.zeros(n, dtype=np.float32),
            "sfx": np.zeros(n, dtype=np.float32),
        }

        clean, policy = sep._build_clean_audio_wiener(
            original_audio=original,
            normalized_outputs=outputs,
            target_slot="sfx",
            aggressiveness=2.0,
        )
        assert policy == "wiener_mask_passthrough"
        np.testing.assert_array_equal(clean, original)

    def test_wiener_mask_bounds(self):
        """Wiener mask output should never exceed original mixture energy."""
        sep = self._make_sep()
        sr = TARGET_SAMPLE_RATE
        n = 16000
        np.random.seed(42)
        original = np.random.randn(n).astype(np.float32)
        outputs = {
            "speech": np.random.randn(n).astype(np.float32) * 0.5,
            "music": np.random.randn(n).astype(np.float32) * 0.3,
            "sfx": np.random.randn(n).astype(np.float32) * 0.2,
        }

        clean, _ = sep._build_clean_audio_wiener(
            original_audio=original,
            normalized_outputs=outputs,
            target_slot="sfx",
            aggressiveness=2.0,
        )

        # Clean RMS should not exceed original RMS (masks are bounded)
        orig_rms = np.sqrt(np.mean(original ** 2))
        clean_rms = np.sqrt(np.mean(clean ** 2))
        assert clean_rms <= orig_rms + 1e-4, (
            f"Clean RMS {clean_rms:.4f} exceeds original {orig_rms:.4f}"
        )

    def test_perceptual_floor_shape(self):
        """Floor array has correct length and range."""
        floor = CodecSepSeparator._build_wiener_perceptual_floor(
            n_freqs=1025, floor_min=0.01, floor_max=0.05,
        )
        assert floor.shape == (1025,)
        assert floor[0] == pytest.approx(0.05, abs=1e-6)
        assert floor[-1] == pytest.approx(0.01, abs=1e-6)
        assert np.all(floor >= 0.01 - 1e-6)
        assert np.all(floor <= 0.05 + 1e-6)

    def test_native_target_embedding_uses_negative_prompts(self):
        """_build_native_target_embedding should apply negative prompt arithmetic."""
        sep = self._make_sep()

        class FakeTextEncoder:
            @staticmethod
            def get_text_embedding(prompts, use_tensor=True):
                values = []
                for prompt in prompts:
                    if "dog" in prompt or "bark" in prompt:
                        values.append(torch.tensor([2.0, 0.0], dtype=torch.float32))
                    elif "speech" in prompt:
                        values.append(torch.tensor([0.0, 2.0], dtype=torch.float32))
                    else:
                        values.append(torch.tensor([1.0, 1.0], dtype=torch.float32))
                return torch.stack(values, dim=0)

        sep._model.text_encoder = FakeTextEncoder()

        plan_no_neg = CodecSepQueryPlan(
            target_prompts=["dog barking"],
            preferred_slot="sfx",
        )
        plan_with_neg = CodecSepQueryPlan(
            target_prompts=["dog barking"],
            negative_prompts=["speech, talking, voice"],
            preferred_slot="sfx",
            aggressiveness=2.0,
        )

        embed_no_neg = sep._build_native_target_embedding(plan_no_neg)
        embed_with_neg = sep._build_native_target_embedding(plan_with_neg)

        assert embed_no_neg.shape == embed_with_neg.shape == (1, 2)
        # Negative prompt should push embedding away from speech direction
        assert not torch.allclose(embed_no_neg, embed_with_neg)
        # With negative "speech" (0,2), the dog embedding (2,0) should become
        # more extreme in the dog direction and less in the speech direction
        assert embed_with_neg[0, 0] > embed_no_neg[0, 0] or embed_with_neg[0, 1] < embed_no_neg[0, 1]


class TestCodecSepSeparatorWithSuppressor:
    """Integration-like tests verifying CodecSep works with SemanticSuppressor."""

    def test_suppressor_accepts_codecsep_backend(self):
        """SemanticSuppressor should initialize with codecsep backend."""
        from ai.ai_runtime.suppression import SemanticSuppressor
        supp = SemanticSuppressor(
            separator_backend="codecsep",
            masking_method="cirm",
        )
        assert supp.separator_backend == "codecsep"
        assert supp.masking_method == "cirm"

    def test_suppressor_rejects_unknown_backend(self):
        from ai.ai_runtime.suppression import SemanticSuppressor
        with pytest.raises(ValueError, match="Unknown separator_backend"):
            SemanticSuppressor(separator_backend="unknown")

    def test_suppressor_rejects_unknown_masking(self):
        from ai.ai_runtime.suppression import SemanticSuppressor
        with pytest.raises(ValueError, match="Unknown masking_method"):
            SemanticSuppressor(masking_method="unknown")

    def test_suppressor_fixed_category_routes_legacy_category_to_class_ids(self):
        from ai.ai_runtime.suppression import SemanticSuppressor
        from ai.ai_runtime.utils.codecsep import FixedCategoryRuntimeCatalog

        captured: dict = {}

        class FakeSeparator:
            def supports_fixed_category(self):
                return True

            def separate_class_id_bundle(self, **kwargs):
                captured.update(kwargs)
                audio = np.asarray(kwargs["audio"], dtype=np.float32)
                removed = np.full_like(audio, 0.25, dtype=np.float32)
                return {
                    "targets": {1: removed},
                    "selected_class_ids": list(kwargs["class_ids"]),
                    "merged_target": removed,
                    "clean_audio": audio - removed,
                    "merge_policy": "wiener_mask",
                }

        suppressor = SemanticSuppressor(separator_backend="codecsep")
        suppressor._codecsep_fixed_catalog = FixedCategoryRuntimeCatalog(
            identity_payload={
                "version": "v1",
                "num_classes": 2,
                "null_id": 2,
                "entries": [
                    {
                        "class_id": 1,
                        "slug": "keyboard_typing",
                        "hive_label": "keyboard typing",
                        "display_name": "keyboard typing",
                        "product_category": "keyboard_typing",
                        "aliases": ["typing"],
                    },
                ],
            },
            mapping_payload={
                "product_categories": [
                    {
                        "product_category": "keyboard_typing",
                        "member_class_ids": [1],
                        "member_slugs": ["keyboard_typing"],
                        "priority_class_ids": [1],
                        "legacy_runtime_categories": ["typing"],
                    },
                ],
            },
            threshold_payload={
                "version": "gate_thresholds_v2",
                "global_default_threshold": 0.5,
                "thresholds": {"keyboard_typing": 0.5},
            },
        )
        suppressor._get_codecsep_separator = lambda **_kwargs: FakeSeparator()

        audio = np.ones(8000, dtype=np.float32)
        clean = suppressor.suppress(
            audio,
            TARGET_SAMPLE_RATE,
            suppress_categories=["typing"],
            codecsep_mode="fixed_category",
        )

        assert captured["class_ids"] == [1]
        assert captured["merge_policy"] == "wiener_mask"
        np.testing.assert_allclose(clean, np.full_like(audio, 0.75))

    def test_fixed_category_runtime_catalog_supports_top_level_legacy_aliases(self):
        from ai.ai_runtime.utils.codecsep import FixedCategoryRuntimeCatalog

        catalog = FixedCategoryRuntimeCatalog(
            identity_payload={
                "version": "v1",
                "num_classes": 2,
                "null_id": 2,
                "entries": [
                    {
                        "class_id": 1,
                        "slug": "keyboard_typing",
                        "hive_label": "keyboard typing",
                        "display_name": "keyboard typing",
                        "product_category": "keyboard_typing",
                        "aliases": ["typing"],
                    },
                    {
                        "class_id": 2,
                        "slug": "siren",
                        "hive_label": "siren",
                        "display_name": "siren",
                        "product_category": "siren",
                        "aliases": [],
                    },
                ],
            },
            mapping_payload={
                "product_categories": [
                    {
                        "product_category": "keyboard_typing",
                        "member_class_ids": [1],
                        "member_slugs": ["keyboard_typing"],
                        "priority_class_ids": [1],
                        "legacy_runtime_categories": [],
                    },
                    {
                        "product_category": "siren",
                        "member_class_ids": [2],
                        "member_slugs": ["siren"],
                        "priority_class_ids": [2],
                        "legacy_runtime_categories": [],
                    },
                ],
                "legacy_category_aliases": {
                    "typing": ["keyboard_typing"],
                    "alerts": ["siren"],
                },
            },
            threshold_payload={
                "version": "gate_thresholds_v2",
                "global_default_threshold": 0.5,
                "thresholds": {"keyboard_typing": 0.5, "siren": 0.6},
            },
        )

        resolved = catalog.resolve_targets(legacy_categories=["typing", "alerts"])

        assert resolved["product_categories"] == ["keyboard_typing", "siren"]
        assert resolved["class_ids"] == [1, 2]
