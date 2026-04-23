"""
CodecSep inference model (vendored, inference-only).

Adapted from the CodecSep supplementary material. Training-only paths
(``forward`` with batch dict, SDCodec quantization) are removed.
External dependencies: ``laion_clap`` (CLAP text encoder).
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import math
import os
from pathlib import Path
import sys
from typing import Any, List, Mapping, Optional

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
from torch.nn.utils import weight_norm

from .modules import (
    CodecMixin,
    DACDecoder,
    DACEncoder,
    FiLM,
    Snake1d,
    apply_conditioning_gate,
    apply_film_affine,
    get_film_meta,
)

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)

# Keep CLAP/Transformers on the PyTorch-only path in this workspace.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")


def _resolve_conditioning_num_classes(
    explicit_num_classes: int | None,
    conditioning_cfg: Mapping[str, Any] | None,
) -> int:
    if explicit_num_classes is not None:
        return int(explicit_num_classes)

    cfg = dict(conditioning_cfg or {})
    configured_num_classes = int(cfg.get("num_classes", 0) or 0)
    if configured_num_classes > 0:
        return configured_num_classes

    catalog_path_value = cfg.get("identity_catalog_path")
    if not catalog_path_value:
        return configured_num_classes

    catalog_path = Path(str(catalog_path_value)).expanduser().resolve()
    if not catalog_path.is_file():
        raise FileNotFoundError(f"Fixed-category identity catalog not found: {catalog_path}")

    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if "null_id" in payload:
        return int(payload["null_id"]) + 1
    if "num_classes" in payload:
        return int(payload["num_classes"]) + 1
    raise KeyError(
        "Fixed-category identity catalog must define either 'null_id' or 'num_classes' "
        f"to resolve conditioning.num_classes: {catalog_path}"
    )


class _TextOnlyClapEncoder(nn.Module):
    """Minimal CLAP wrapper for text embeddings without audio data loaders."""

    def __init__(self, model: nn.Module, tokenizer) -> None:
        super().__init__()
        self.model = model
        self._tokenizer = tokenizer

    def tokenizer(self, texts):
        return self._tokenizer(
            texts,
            padding="max_length",
            truncation=True,
            max_length=77,
            return_tensors="pt",
        )

    @torch.no_grad()
    def get_text_embedding(self, texts, use_tensor: bool = False):
        if isinstance(texts, str):
            texts = [texts]
        text_input = self.tokenizer(texts)
        text_embed = self.model.get_text_embedding(text_input)
        if use_tensor:
            return text_embed
        return text_embed.detach().cpu().numpy()


class _NullTextEncoder(nn.Module):
    def get_text_embedding(self, texts, use_tensor: bool = False):
        raise RuntimeError("Text conditioning is disabled when conditioning.mode=class_id.")


# ---------------------------------------------------------------------------
# Positional encoding
# ---------------------------------------------------------------------------

class PositionalEncoding(nn.Module):
    def __init__(self, input_size: int, max_len: int = 2500):
        super().__init__()
        if input_size % 2 != 0:
            raise ValueError(
                f"Cannot use sin/cos positional encoding with odd channels "
                f"(got channels={input_size})"
            )
        self.max_len = max_len
        pe = torch.zeros(max_len, input_size, requires_grad=False)
        positions = torch.arange(0, max_len).unsqueeze(1).float()
        denominator = torch.exp(
            torch.arange(0, input_size, 2).float()
            * -(math.log(10000.0) / input_size)
        )
        pe[:, 0::2] = torch.sin(positions * denominator)
        pe[:, 1::2] = torch.cos(positions * denominator)
        pe = pe.unsqueeze(0)
        self.register_buffer("pe", pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.pe[:, : x.size(1)].clone().detach()


# ---------------------------------------------------------------------------
# FiLM-conditioned Transformer
# ---------------------------------------------------------------------------

class TransformerEncoderLayerFiLM(nn.Module):
    def __init__(self, model_dim: int, num_heads: int, ff_dim: int,
                 batch_first: bool = False, dropout: float = 0.1,
                 has_film: bool = False, conditioning_variant: str = "film"):
        super().__init__()
        self.self_attn = nn.MultiheadAttention(
            embed_dim=model_dim, num_heads=num_heads,
            batch_first=batch_first, dropout=dropout,
        )
        self.norm1 = nn.LayerNorm(model_dim)
        self.norm2 = nn.LayerNorm(model_dim)
        self.ffn = nn.Sequential(
            nn.Linear(model_dim, ff_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(ff_dim, model_dim),
        )
        self.dropout = nn.Dropout(dropout)
        self.has_film = has_film
        self.dim = model_dim
        self.conditioning_variant = str(conditioning_variant).strip().lower() or "film"
        self.film_supports_gates = self.has_film and self.conditioning_variant == "adaln_zero"

    def forward(self, x: torch.Tensor,
                film_dict: dict | None = None) -> torch.Tensor:
        if self.has_film and film_dict is not None:
            g1 = film_dict["gamma1"]
            b1 = film_dict["beta1"]
            g2 = film_dict["gamma2"]
            b2 = film_dict["beta2"]
            gate1 = film_dict.get("gate1")
            gate2 = film_dict.get("gate2")

        if self.has_film and film_dict is not None and self.conditioning_variant == "adaln_zero":
            normed = apply_film_affine(self.norm1(x), g1.permute(0, 2, 1), b1.permute(0, 2, 1))
            attn_output, _ = self.self_attn(normed, normed, normed)
            if gate1 is not None:
                attn_output = apply_conditioning_gate(attn_output, gate1.permute(0, 2, 1))
            x = x + self.dropout(attn_output)

            normed_ffn = apply_film_affine(self.norm2(x), g2.permute(0, 2, 1), b2.permute(0, 2, 1))
            ffn_output = self.ffn(normed_ffn)
            if gate2 is not None:
                ffn_output = apply_conditioning_gate(ffn_output, gate2.permute(0, 2, 1))
            x = x + self.dropout(ffn_output)
            return x

        attn_output, _ = self.self_attn(x, x, x)
        x = x + self.dropout(attn_output)
        x = self.norm1(x)

        if self.has_film and film_dict is not None:
            x = apply_film_affine(x, g1.permute(0, 2, 1), b1.permute(0, 2, 1))

        ffn_output = self.ffn(x)
        x = x + self.dropout(ffn_output)
        x = self.norm2(x)

        if self.has_film and film_dict is not None:
            x = apply_film_affine(x, g2.permute(0, 2, 1), b2.permute(0, 2, 1))

        return x


class TransformerEncoderWithFiLM(nn.Module):
    def __init__(self, num_layers: int, model_dim: int, num_heads: int,
                 ff_dim: int, film_condition_size: int,
                 batch_first: bool = False, dropout: float = 0.1,
                 conditioning_variant: str = "film"):
        super().__init__()
        self.layers = nn.ModuleList([
            TransformerEncoderLayerFiLM(
                model_dim=model_dim, num_heads=num_heads, ff_dim=ff_dim,
                dropout=dropout, has_film=True, batch_first=batch_first,
                conditioning_variant=conditioning_variant,
            )
            for _ in range(num_layers)
        ])

    def forward(self, x: torch.Tensor,
                film_dict: dict | None = None) -> torch.Tensor:
        for i, layer in enumerate(self.layers):
            x = layer(x, film_dict["layers"][f"{i}"] if film_dict else None)
        return x


# ---------------------------------------------------------------------------
# Separator head
# ---------------------------------------------------------------------------

class SimpleSeparator(nn.Module):
    """Channel-reduce -> Transformer -> Channel-expand -> Masker."""

    def __init__(self, num_spks: int, channels: int, block: nn.Module,
                 block_channels: int, has_film: bool = False,
                 conditioning_variant: str = "film"):
        super().__init__()
        self.num_spks = num_spks
        self.channels = channels
        self.ch_down = nn.Conv1d(channels, block_channels, 1, bias=False)
        self.ch_up = nn.Conv1d(block_channels, channels, 1, bias=False)
        self.block = block
        self.masker = weight_norm(
            nn.Conv1d(channels, channels * num_spks, 1, bias=False)
        )
        self.pos_enc = PositionalEncoding(256)
        self.activation = Snake1d(channels)
        self.output = nn.Sequential(
            nn.Conv1d(channels, channels, 1), Snake1d(channels),
        )
        self.dim = channels
        self.has_film = has_film
        self.conditioning_variant = str(conditioning_variant).strip().lower() or "film"
        self.film_supports_gates = False

    def forward(self, x: torch.Tensor,
                film_dict: dict | None = None) -> torch.Tensor:
        x = self.ch_down(x)
        x = x.permute(0, 2, 1)
        x = x + self.pos_enc(x)
        x = self.block(x, film_dict=film_dict["block"] if film_dict else None)
        x = x.permute(0, 2, 1)
        x = self.ch_up(x)

        if self.has_film and film_dict is not None:
            g1, b1 = film_dict["gamma1"], film_dict["beta1"]
            g2, b2 = film_dict["gamma2"], film_dict["beta2"]
            x = x.permute(0, 2, 1)
            x = apply_film_affine(x, g1.permute(0, 2, 1), b1.permute(0, 2, 1))
            x = x.permute(0, 2, 1)

        B, N, L = x.shape
        masks = self.masker(x).view(B * self.num_spks, -1, L)

        if self.has_film and film_dict is not None:
            masks = masks.permute(0, 2, 1)
            masks = apply_film_affine(masks, g2.permute(0, 2, 1), b2.permute(0, 2, 1))
            masks = masks.permute(0, 2, 1)

        x = self.output(masks)
        _, N, L = x.shape
        x = x.view(B, self.num_spks, N, L).transpose(0, 1)
        return x


# ---------------------------------------------------------------------------
# CodecSep main model
# ---------------------------------------------------------------------------

class _LegacyRuntimeCodecSep(nn.Module, CodecMixin):
    """Text-prompted latent-masking source separator.

    Uses a frozen CLAP text encoder for FiLM conditioning and a
    DAC-based encoder/decoder pair. Only the separator and FiLM
    parameters are trainable.
    """

    TRACKS = ("speech", "music", "sfx")

    def __init__(
        self,
        sample_rate: int = 16000,
        latent_dim: int | None = None,
        tracks: List[str] | None = None,
        mode: str = "legacy_3slot",
        residual_mode: str = "latent_complement",
        enc_params: dict | None = None,
        dec_params: dict | None = None,
        transformer_params: dict | None = None,
        separator_params: dict | None = None,
        film_clip: float | None = None,
        normalize_prompt_embeddings: bool = False,
        prompt_embed_eps: float = 1.0e-6,
        enable_semantic_finite_checks: bool = False,
        conditioning: dict | None = None,
        num_classes: int | None = None,
        clap: dict | None = None,
        pretrain: dict | None = None,
    ):
        super().__init__()

        self.sample_rate = sample_rate
        self.tracks = list(tracks) if tracks else list(self.TRACKS)
        self.track2idx = {t: i for i, t in enumerate(self.tracks)}
        self.clap_cfg = dict(clap or {})
        self.conditioning_cfg = dict(conditioning or {})
        self.conditioning_mode = str(self.conditioning_cfg.get("mode", "prompt")).strip().lower() or "prompt"
        self.conditioning_variant = str(self.conditioning_cfg.get("variant", "film")).strip().lower() or "film"
        self.condition_size = int(self.conditioning_cfg.get("condition_size", 512))
        self.num_classes = _resolve_conditioning_num_classes(num_classes, self.conditioning_cfg)
        self.conditioning_zero_for_absent = bool(self.conditioning_cfg.get("zero_for_absent", True))
        self.conditioning_zero_for_null = bool(self.conditioning_cfg.get("use_zero_for_null", False))
        self.mode = str(mode or "legacy_3slot")
        self.residual_mode = str(residual_mode or "latent_complement")
        self.film_clip = film_clip
        self.normalize_prompt_embeddings = bool(normalize_prompt_embeddings)
        self.prompt_embed_eps = float(prompt_embed_eps)
        self.enable_semantic_finite_checks = bool(enable_semantic_finite_checks)
        self.pretrain = dict(pretrain or {})
        self._text_embedding_cache: dict[str, torch.Tensor] = {}

        enc_p = dict(enc_params) if enc_params else {"d_model": 64, "strides": [2, 4, 5, 8]}
        dec_p = dict(dec_params) if dec_params else {"d_model": 1536, "strides": [8, 5, 4, 2]}
        tf_p = dict(transformer_params) if transformer_params else {
            "d_model": 256, "nhead": 8, "dim_feedforward": 1024,
            "num_layers": 16, "dropout": 0.1, "batch_first": True,
        }
        sep_p = dict(separator_params) if separator_params else {
            "channels": 1024, "block_channels": 256,
        }

        if self.conditioning_mode not in {"prompt", "class_id"}:
            raise ValueError(f"Unsupported conditioning mode: {self.conditioning_mode}")
        if self.conditioning_variant not in {"film", "adaln_zero"}:
            raise ValueError(f"Unsupported conditioning variant: {self.conditioning_variant}")
        if self.conditioning_mode == "class_id" and self.num_classes <= 0:
            raise ValueError("conditioning.num_classes must be positive when conditioning.mode=class_id")

        enc_p.pop("name", None)
        dec_p.pop("name", None)
        tf_p.pop("name", None)
        sep_p.pop("name", None)

        if latent_dim is None:
            latent_dim = enc_p["d_model"] * (2 ** len(enc_p["strides"]))
        self.latent_dim = latent_dim
        self.hop_length = int(np.prod(enc_p["strides"]))

        self.encoder = DACEncoder(**enc_p)
        self.decoder = DACDecoder(**dec_p)

        self.transformer_encoder = TransformerEncoderWithFiLM(
            num_layers=tf_p["num_layers"],
            model_dim=tf_p["d_model"],
            num_heads=tf_p["nhead"],
            ff_dim=tf_p["dim_feedforward"],
            film_condition_size=tf_p["d_model"],
            dropout=tf_p.get("dropout", 0.1),
            batch_first=tf_p.get("batch_first", True),
            conditioning_variant=self.conditioning_variant,
        )

        self.class_embedding = None
        if self.conditioning_mode == "prompt":
            self.text_encoder = self._build_text_encoder(self.clap_cfg)
            for param in self.text_encoder.parameters():
                param.requires_grad = False
        else:
            self.text_encoder = _NullTextEncoder()
            self.class_embedding = nn.Embedding(self.num_classes, self.condition_size)
            self._load_class_conditioning_init()

        self.separator = SimpleSeparator(
            num_spks=1, has_film=True,
            block=self.transformer_encoder,
            channels=sep_p["channels"],
            block_channels=sep_p["block_channels"],
            conditioning_variant=self.conditioning_variant,
        )

        film_meta = get_film_meta(self.separator, variant=self.conditioning_variant)
        self.film = FiLM(
            film_meta,
            condition_size=self.condition_size,
            variant=self.conditioning_variant,
            adaln_gate_bias=float(self.conditioning_cfg.get("adaln_gate_bias", 0.01)),
        )
        self.register_buffer("_class_embedding_init", torch.empty(0), persistent=False)
        if self.class_embedding is not None:
            self._class_embedding_init = self.class_embedding.weight.detach().clone()

        self.delay = self.get_delay()

    @property
    def device(self) -> torch.device:
        return next(self.parameters()).device

    @staticmethod
    def _import_clap_factory_modules():
        spec = importlib.util.find_spec("laion_clap")
        if spec is None or not spec.submodule_search_locations:
            raise ImportError(
                "laion_clap is required for CodecSep. Install with: pip install laion-clap"
            )

        laion_clap_dir = Path(next(iter(spec.submodule_search_locations))).resolve()
        clap_module_root = str(laion_clap_dir)
        if clap_module_root not in sys.path:
            sys.path.insert(0, clap_module_root)

        factory_module = importlib.import_module("clap_module.factory")
        return getattr(factory_module, "create_model")

    @classmethod
    def _build_text_encoder(cls, clap_cfg: dict | None):
        from transformers import RobertaTokenizer

        clap_cfg = clap_cfg or {}
        create_model = cls._import_clap_factory_modules()
        enable_fusion = bool(clap_cfg.get("enable_fusion", False))
        amodel = clap_cfg.get("amodel", "HTSAT-tiny")
        text_model = clap_cfg.get("tmodel", "roberta")

        model, _ = create_model(
            amodel,
            text_model,
            precision="fp32",
            device=torch.device("cpu"),
            enable_fusion=enable_fusion,
            fusion_type="aff_2d" if enable_fusion else "None",
        )
        tokenizer = RobertaTokenizer.from_pretrained("roberta-base")
        logger.info(
            "Runtime CodecSep text encoder configured with amodel=%s tmodel=%s",
            amodel,
            text_model,
        )
        return _TextOnlyClapEncoder(model=model, tokenizer=tokenizer)

    def _load_class_conditioning_init(self) -> None:
        if self.class_embedding is None:
            return
        init_path_value = self.conditioning_cfg.get("embedding_init_path")
        if not init_path_value:
            return
        init_path = Path(str(init_path_value)).expanduser().resolve()
        if not init_path.is_file():
            raise FileNotFoundError(f"Class-conditioning init matrix not found: {init_path}")
        if init_path.suffix.lower() == ".json":
            payload = json.loads(init_path.read_text(encoding="utf-8"))
        else:
            payload = torch.load(str(init_path), map_location="cpu", weights_only=False)
        if isinstance(payload, dict):
            matrix = payload.get("embedding", payload.get("matrix", payload.get("weights")))
        else:
            matrix = payload
        if not torch.is_tensor(matrix):
            try:
                matrix = torch.as_tensor(matrix, dtype=torch.float32)
            except Exception as exc:
                raise RuntimeError(f"Unsupported conditioning init payload in {init_path}") from exc
        matrix = matrix.detach().float()
        if tuple(matrix.shape) != tuple(self.class_embedding.weight.shape):
            raise RuntimeError(
                f"Conditioning init matrix shape mismatch: expected {tuple(self.class_embedding.weight.shape)}, "
                f"got {tuple(matrix.shape)}"
            )
        with torch.no_grad():
            self.class_embedding.weight.copy_(matrix)
        logger.info(
            "Runtime CodecSep loaded class-conditioning init matrix from %s shape=%s",
            init_path,
            tuple(matrix.shape),
        )

    @staticmethod
    def _coerce_embedding_override(
        embedding,
        *,
        batch_size: int,
        device: torch.device,
    ) -> torch.Tensor:
        if not torch.is_tensor(embedding):
            embedding = torch.as_tensor(embedding, dtype=torch.float32)
        embedding = embedding.detach().float()
        if embedding.ndim == 1:
            embedding = embedding.unsqueeze(0)
        if embedding.ndim != 2:
            raise ValueError(
                f"Embedding override must be 1-D or 2-D, got shape {tuple(embedding.shape)}."
            )
        if embedding.shape[0] == 1 and batch_size > 1:
            embedding = embedding.expand(batch_size, -1)
        elif embedding.shape[0] != batch_size:
            raise ValueError(
                "Embedding override batch dimension must be 1 or match the audio batch size "
                f"(got {embedding.shape[0]} vs {batch_size})."
            )
        return embedding.to(device=device)

    @staticmethod
    def _normalize_prompt_batch(prompt_input, batch_size: int | None = None) -> list[str]:
        if isinstance(prompt_input, str):
            if batch_size is None:
                return [prompt_input]
            return [prompt_input] * batch_size
        return [str(item) for item in prompt_input]

    @staticmethod
    def _prepare_prompt_embedding(embedding: torch.Tensor) -> torch.Tensor:
        return torch.nan_to_num(
            embedding.float(),
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )

    def _encode_prompt_batch(self, prompt_input, batch_size: int | None = None) -> torch.Tensor:
        prompts = self._normalize_prompt_batch(prompt_input, batch_size=batch_size)
        missing = [prompt for prompt in dict.fromkeys(prompts) if prompt not in self._text_embedding_cache]
        if missing:
            encoded = self.text_encoder.get_text_embedding(missing, use_tensor=True).detach().float().cpu()
            for prompt, embedding in zip(missing, encoded):
                self._text_embedding_cache[prompt] = self._prepare_prompt_embedding(embedding)
        stacked = torch.stack([self._text_embedding_cache[prompt] for prompt in prompts], dim=0)
        return self._prepare_prompt_embedding(stacked).to(self.device)

    def preprocess(self, audio_data: torch.Tensor,
                   sample_rate: int | None = None) -> torch.Tensor:
        if sample_rate is not None:
            assert sample_rate == self.sample_rate
        length = audio_data.shape[-1]
        right_pad = math.ceil(length / self.hop_length) * self.hop_length - length
        return F.pad(audio_data, (0, right_pad))

    def encode(self, audio_data: torch.Tensor) -> torch.Tensor:
        return self.encoder(audio_data)

    def decode(self, z: torch.Tensor) -> torch.Tensor:
        return self.decoder(z)

    @torch.inference_mode()
    def evaluate(
        self,
        input_audio_and_prompt: tuple,
        sample_rate: int | None = None,
        output_tracks: list[str] | None = None,
        embedding_overrides: Mapping[str, torch.Tensor] | None = None,
    ) -> torch.Tensor:
        """Run inference and return separated audio.

        Args:
            input_audio_and_prompt: ``(audio_tensor, prompts)`` where
                ``audio_tensor`` is shape ``(B, 1, T)`` and ``prompts``
                is a list/tuple of prompt lists aligned with ``self.tracks``.
            sample_rate: Must match ``self.sample_rate`` if given.
            output_tracks: Which stems to return (default: all tracks + mix).

        Returns:
            ``Tensor[B, K, T]`` with *K* = ``len(output_tracks)``.
        """
        if output_tracks is None:
            output_tracks = ["mix"] + list(self.tracks)

        input_audio, prompt = input_audio_and_prompt
        if self.conditioning_mode == "class_id":
            if isinstance(prompt, dict):
                class_ids = prompt["target_class_id"]
                target_present = prompt.get("target_present")
                query_mode = prompt.get("query_mode")
            else:
                class_ids = prompt
                target_present = None
                query_mode = None
            return self.evaluate_with_class_ids(
                input_audio,
                torch.as_tensor(class_ids, dtype=torch.long, device=self.device),
                target_present=target_present,
                query_mode=query_mode,
                sample_rate=sample_rate,
            )
        batch_size = int(input_audio.shape[0])
        text_embed = self._build_track_embeddings(
            prompt=prompt,
            batch_size=batch_size,
            embedding_overrides=embedding_overrides,
        )
        return self.evaluate_with_embeddings(
            input_audio,
            text_embed,
            sample_rate=sample_rate,
            output_tracks=output_tracks,
        )

    def _build_track_embeddings(
        self,
        *,
        prompt,
        batch_size: int,
        embedding_overrides: Mapping[str, torch.Tensor] | None = None,
    ) -> dict[str, torch.Tensor]:
        track_embeddings: dict[str, torch.Tensor] = {}
        overrides = dict(embedding_overrides or {})
        for track in self.tracks:
            if track in overrides and overrides[track] is not None:
                track_embeddings[track] = self._coerce_embedding_override(
                    overrides[track],
                    batch_size=batch_size,
                    device=self.device,
                )
                continue
            if isinstance(prompt, Mapping):
                prompt_value = prompt.get(track, track)
            else:
                prompt_value = prompt[self.track2idx[track]]
            track_embeddings[track] = self._encode_prompt_batch(
                prompt_value,
                batch_size=batch_size,
            )
        return track_embeddings

    def _encode_class_ids(
        self,
        class_ids: torch.Tensor,
        *,
        target_present: torch.Tensor | None = None,
        query_mode: list[str] | None = None,
    ) -> torch.Tensor:
        if self.class_embedding is None:
            raise RuntimeError("Class-id conditioning requested but no class embedding table is available.")
        class_ids = class_ids.long().to(self.device)
        embeddings = self.class_embedding(class_ids.clamp(min=0, max=self.num_classes - 1))
        zero_mask = torch.zeros(class_ids.shape[0], dtype=torch.bool, device=self.device)
        if self.conditioning_zero_for_absent and target_present is not None:
            zero_mask |= ~target_present.bool().to(self.device)
        if query_mode is not None:
            for index, mode in enumerate(query_mode):
                normalized_mode = str(mode).strip().lower()
                if normalized_mode == "null":
                    if self.conditioning_zero_for_null:
                        zero_mask[index] = True
                elif normalized_mode != "present" and self.conditioning_zero_for_absent:
                    zero_mask[index] = True
        if zero_mask.ndim < embeddings.ndim:
            zero_mask = zero_mask.unsqueeze(-1)
        return torch.where(zero_mask, torch.zeros_like(embeddings), embeddings)

    def _encode_class_id_batch(
        self,
        class_ids: torch.Tensor,
        *,
        target_present: torch.Tensor | None = None,
        query_mode=None,
    ) -> torch.Tensor:
        query_modes = None
        if query_mode is not None:
            if isinstance(query_mode, str):
                query_modes = [str(query_mode)] * int(class_ids.numel())
            elif torch.is_tensor(query_mode):
                query_modes = [str(item) for item in query_mode.detach().cpu().tolist()]
            else:
                query_modes = [str(item) for item in list(query_mode)]
        return self._encode_class_ids(
            class_ids,
            target_present=target_present,
            query_mode=query_modes,
        )

    @torch.inference_mode()
    def evaluate_with_embeddings(
        self,
        input_audio: torch.Tensor,
        track_embeddings: Mapping[str, torch.Tensor],
        *,
        sample_rate: int | None = None,
        output_tracks: list[str] | None = None,
    ) -> torch.Tensor:
        if output_tracks is None:
            output_tracks = ["mix"] + list(self.tracks)

        film_dicts = {
            track: self.film(track_embeddings[track].to(self.device))
            for track in self.tracks
        }

        bs, _, length = input_audio.shape
        audio_data = self.preprocess(input_audio, sample_rate)
        feats = self.encode(audio_data)

        sep_masks = []
        for track in self.tracks:
            est_mask = self.separator(feats, film_dict=film_dicts[track])
            sep_masks.append(est_mask.squeeze(0))
        est_mask = torch.stack(sep_masks)

        feats_stacked = feats.unsqueeze(0).expand(len(self.tracks), -1, -1, -1)
        recon = feats_stacked * est_mask
        mix_latent = recon.sum(0)

        list_out: list[torch.Tensor] = []
        for track in output_tracks:
            if track == "mix":
                x_out = self.decode(mix_latent)[:, :, :audio_data.shape[-1]]
            else:
                x_out = self.decode(
                    recon[self.track2idx[track]]
                )[:, :, :audio_data.shape[-1]]
            list_out.append(x_out)

        return torch.cat(list_out, dim=1)[..., :length]

    @torch.inference_mode()
    def separate_class_ids(
        self,
        input_audio: torch.Tensor,
        class_ids: torch.Tensor,
        *,
        target_present: torch.Tensor | None = None,
        query_mode: list[str] | None = None,
        sample_rate: int | None = None,
    ) -> torch.Tensor:
        if self.conditioning_mode != "class_id":
            raise RuntimeError("separate_class_ids requires conditioning.mode=class_id")
        class_ids = class_ids.reshape(-1).long().to(self.device)
        if int(class_ids.numel()) == 0:
            raise ValueError("Expected at least one class id for separation.")

        bs, _, length = input_audio.shape
        if bs != 1:
            raise ValueError(f"separate_class_ids currently expects batch size 1, got {bs}")

        audio_data = self.preprocess(input_audio, sample_rate)
        feats = self.encode(audio_data)
        class_embed = self._encode_class_ids(
            class_ids,
            target_present=target_present,
            query_mode=query_mode,
        )
        film_dict = self.film(class_embed)
        expanded_feats = feats.expand(class_ids.shape[0], -1, -1)
        est_mask = self.separator(expanded_feats, film_dict=film_dict).squeeze(0)
        target_feats = expanded_feats * est_mask
        target_audio = self.decode(target_feats)[:, :, :audio_data.shape[-1]]
        return target_audio[..., :length]

    @torch.inference_mode()
    def evaluate_with_class_ids(
        self,
        input_audio: torch.Tensor,
        class_ids: torch.Tensor,
        *,
        target_present: torch.Tensor | None = None,
        query_mode: list[str] | None = None,
        sample_rate: int | None = None,
    ) -> torch.Tensor:
        targets = self.separate_class_ids(
            input_audio,
            class_ids,
            target_present=target_present,
            query_mode=query_mode,
            sample_rate=sample_rate,
        )
        return targets


CodecSep = _LegacyRuntimeCodecSep
