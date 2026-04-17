"""
Vendored CodecSep modules (inference-only).

Adapted from SDCodec (https://github.com/XiaoyuBIE1994/SDCodec)
and the CodecSep supplementary material. Only components required
for CodecSep inference are retained; training-only layers, quantizers,
and transformer-attention encoder/decoder variants are omitted.
"""

from __future__ import annotations

import math

import torch
from torch import nn
from torch.nn.utils.parametrizations import weight_norm


# ---------------------------------------------------------------------------
# Primitive layers
# ---------------------------------------------------------------------------

def WNConv1d(*args, **kwargs):
    act = kwargs.pop("act", False)
    conv = weight_norm(nn.Conv1d(*args, **kwargs))
    if act:
        return nn.Sequential(conv, nn.LeakyReLU(0.1))
    return conv


def WNConvTranspose1d(*args, **kwargs):
    return weight_norm(nn.ConvTranspose1d(*args, **kwargs))


@torch.jit.script
def snake(x: torch.Tensor, alpha: torch.Tensor) -> torch.Tensor:
    shape = x.shape
    x = x.reshape(shape[0], shape[1], -1)
    x = x + (alpha + 1e-9).reciprocal() * torch.sin(alpha * x).pow(2)
    x = x.reshape(shape)
    return x


class Snake1d(nn.Module):
    def __init__(self, channels: int):
        super().__init__()
        self.alpha = nn.Parameter(torch.ones(1, channels, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return snake(x, self.alpha)


# ---------------------------------------------------------------------------
# FiLM conditioning
# ---------------------------------------------------------------------------

def _init_layer(layer: nn.Module) -> None:
    nn.init.xavier_uniform_(layer.weight)
    if hasattr(layer, "bias") and layer.bias is not None:
        layer.bias.data.fill_(0.0)


def apply_film_affine(x: torch.Tensor, gamma: torch.Tensor, beta: torch.Tensor) -> torch.Tensor:
    gamma = torch.nan_to_num(gamma, nan=0.0, posinf=0.0, neginf=0.0)
    beta = torch.nan_to_num(beta, nan=0.0, posinf=0.0, neginf=0.0)
    return (1.0 + gamma) * x + beta


def apply_conditioning_gate(x: torch.Tensor, gate: torch.Tensor) -> torch.Tensor:
    gate = torch.nan_to_num(gate, nan=0.0, posinf=0.0, neginf=0.0)
    return gate * x


def _supports_conditioning_gates(module: nn.Module, variant: str) -> bool:
    if str(variant).strip().lower() != "adaln_zero":
        return False
    return bool(getattr(module, "film_supports_gates", False))


def get_film_meta(module: nn.Module, *, variant: str = "film") -> dict:
    film_meta: dict = {}
    if hasattr(module, "has_film"):
        if module.has_film:
            film_meta["gamma1"] = module.dim
            film_meta["beta1"] = module.dim
            film_meta["gamma2"] = module.dim
            film_meta["beta2"] = module.dim
            if _supports_conditioning_gates(module, variant):
                film_meta["gate1"] = module.dim
                film_meta["gate2"] = module.dim
        else:
            film_meta["gamma1"] = 0
            film_meta["beta1"] = 0
            film_meta["gamma2"] = 0
            film_meta["beta2"] = 0
            if _supports_conditioning_gates(module, variant):
                film_meta["gate1"] = 0
                film_meta["gate2"] = 0
    for child_name, child_module in module.named_children():
        child_meta = get_film_meta(child_module, variant=variant)
        if child_meta:
            film_meta[child_name] = child_meta
    return film_meta


class FiLM(nn.Module):
    def __init__(
        self,
        film_meta: dict,
        condition_size: int,
        *,
        variant: str = "film",
        adaln_gate_bias: float = 0.01,
    ):
        super().__init__()
        self.condition_size = condition_size
        self.variant = str(variant).strip().lower() or "film"
        self.adaln_gate_bias = float(adaln_gate_bias)
        self.modules_dict: dict
        self.modules_dict, _ = self._create_film_modules(film_meta, [])

    def _create_film_modules(self, film_meta: dict, ancestor_names: list):
        modules: dict = {}
        for module_name, value in film_meta.items():
            if isinstance(value, int):
                ancestor_names.append(module_name)
                unique_name = "->".join(ancestor_names)
                layer = nn.Linear(self.condition_size, value)
                lower_name = unique_name.lower()
                if self.variant == "adaln_zero":
                    nn.init.zeros_(layer.weight)
                    if layer.bias is not None:
                        nn.init.constant_(layer.bias, self.adaln_gate_bias if "gate" in lower_name else 0.0)
                elif "gamma" in lower_name:
                    nn.init.zeros_(layer.weight)
                    if layer.bias is not None:
                        nn.init.zeros_(layer.bias)
                else:
                    _init_layer(layer)
                self.add_module(name=unique_name, module=layer)
                modules[module_name] = layer
            elif isinstance(value, dict):
                ancestor_names.append(module_name)
                modules[module_name], _ = self._create_film_modules(value, ancestor_names)
            ancestor_names.pop()
        return modules, ancestor_names

    def forward(self, conditions: torch.Tensor) -> dict:
        return self._calc(conditions, self.modules_dict)

    def _calc(self, conditions: torch.Tensor, modules: dict) -> dict:
        film_data: dict = {}
        for name, mod in modules.items():
            if isinstance(mod, nn.Module):
                film_data[name] = mod(conditions)[:, :, None]
            elif isinstance(mod, dict):
                film_data[name] = self._calc(conditions, mod)
        return film_data


# ---------------------------------------------------------------------------
# DAC encoder / decoder building blocks
# ---------------------------------------------------------------------------

class ResidualUnit(nn.Module):
    def __init__(self, dim: int = 16, dilation: int = 1, has_film: bool = False):
        super().__init__()
        k = 7
        pad = ((k - 1) * dilation) // 2
        self.block = nn.Sequential(
            Snake1d(dim),
            WNConv1d(dim, dim, kernel_size=k, dilation=dilation, padding=pad),
            Snake1d(dim),
            WNConv1d(dim, dim, kernel_size=1),
        )
        self.has_film = has_film
        self.dim = dim
        self.film_supports_gates = False

    def forward(self, x: torch.Tensor, film_dict: dict | None = None) -> torch.Tensor:
        if self.has_film and film_dict is not None:
            g1 = film_dict["gamma1"]
            b1 = film_dict["beta1"]
            g2 = film_dict["gamma2"]
            b2 = film_dict["beta2"]
            y = self.block[0](apply_film_affine(x, g1, b1))
            y = self.block[1](y)
            y = self.block[2](apply_film_affine(y, g2, b2))
            y = self.block[3](y)
        else:
            y = self.block(x)
        pad = (x.shape[-1] - y.shape[-1]) // 2
        if pad > 0:
            x = x[..., pad:-pad]
        return x + y


class EncoderBlock(nn.Module):
    def __init__(self, dim: int = 16, stride: int = 1, has_film: bool = False):
        super().__init__()
        self.block = nn.Sequential(
            ResidualUnit(dim // 2, dilation=1, has_film=has_film),
            ResidualUnit(dim // 2, dilation=3, has_film=has_film),
            ResidualUnit(dim // 2, dilation=9, has_film=has_film),
            Snake1d(dim // 2),
            WNConv1d(dim // 2, dim, kernel_size=2 * stride, stride=stride,
                     padding=math.ceil(stride / 2)),
        )
        self.has_film_ = has_film

    def forward(self, x: torch.Tensor, film_dict: dict | None = None) -> torch.Tensor:
        if not self.has_film_:
            return self.block(x)
        for i in range(3):
            x = self.block[i](x, film_dict["block"][f"{i}"])
        x = self.block[3](x)
        x = self.block[4](x)
        return x


class DecoderBlock(nn.Module):
    def __init__(self, input_dim: int = 16, output_dim: int = 8, stride: int = 1):
        super().__init__()
        self.block = nn.Sequential(
            Snake1d(input_dim),
            WNConvTranspose1d(input_dim, output_dim, kernel_size=2 * stride,
                              stride=stride, padding=math.floor(stride / 2)),
            ResidualUnit(output_dim, dilation=1),
            ResidualUnit(output_dim, dilation=3),
            ResidualUnit(output_dim, dilation=9),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class DACEncoder(nn.Module):
    def __init__(self, d_model: int = 64, strides: list | None = None,
                 d_latent: int = 1024, has_film: bool = False):
        super().__init__()
        if strides is None:
            strides = [2, 4, 8, 8]
        layers: list[nn.Module] = [WNConv1d(1, d_model, kernel_size=7, padding=3)]
        for stride in strides:
            d_model *= 2
            layers.append(EncoderBlock(d_model, stride=stride, has_film=has_film))
        layers += [Snake1d(d_model), WNConv1d(d_model, d_latent, kernel_size=3, padding=1)]
        self.block = nn.Sequential(*layers)
        self.enc_dim = d_model
        self.has_film_ = has_film

    def forward(self, x: torch.Tensor, film_dict: dict | None = None) -> torch.Tensor:
        if not self.has_film_:
            return self.block(x)
        x = self.block[0](x)
        n = len(self.block)
        for i in range(1, n - 2):
            x = self.block[i](x, film_dict["block"][f"{i}"])
        x = self.block[-2](x)
        x = self.block[-1](x)
        return x


class DACDecoder(nn.Module):
    def __init__(self, d_model: int = 1536, strides: list | None = None,
                 d_latent: int = 1024, d_out: int = 1):
        super().__init__()
        if strides is None:
            strides = [8, 8, 4, 2]
        layers: list[nn.Module] = [WNConv1d(d_latent, d_model, kernel_size=7, padding=3)]
        for stride in strides:
            layers.append(DecoderBlock(d_model, d_model // 2, stride))
            d_model = d_model // 2
        layers += [Snake1d(d_model), WNConv1d(d_model, d_out, kernel_size=7, padding=3), nn.Tanh()]
        self.model = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model(x)


class CodecMixin:
    """Delay / output-length calculation from DAC, used by CodecSep."""

    def get_delay(self) -> int:
        l_out = self.get_output_length(0)
        L: float = l_out
        layers = [lay for lay in self.modules()
                  if isinstance(lay, (nn.Conv1d, nn.ConvTranspose1d))]
        for layer in reversed(layers):
            d, k, s = layer.dilation[0], layer.kernel_size[0], layer.stride[0]
            if isinstance(layer, nn.ConvTranspose1d):
                L = ((L - d * (k - 1) - 1) / s) + 1
            elif isinstance(layer, nn.Conv1d):
                L = (L - 1) * s + d * (k - 1) + 1
            L = math.ceil(L)
        return (int(L) - l_out) // 2

    def get_output_length(self, input_length: int) -> int:
        L: float = input_length
        for layer in self.modules():
            if isinstance(layer, (nn.Conv1d, nn.ConvTranspose1d)):
                d, k, s = layer.dilation[0], layer.kernel_size[0], layer.stride[0]
                if isinstance(layer, nn.Conv1d):
                    L = ((L - d * (k - 1) - 1) / s) + 1
                elif isinstance(layer, nn.ConvTranspose1d):
                    L = (L - 1) * s + d * (k - 1) + 1
                L = math.floor(L)
        return int(L)
