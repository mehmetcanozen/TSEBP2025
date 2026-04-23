from __future__ import annotations

import sys
import types
from pathlib import Path

import torch

from ai.export.freeze_codecsep_dnrv2_15cat import (
    ExecuTorchCategoryExportWrapper,
    average_normalized_embeddings,
    build_conditioning_cfg,
    infer_conditioning_variant,
)


def test_infer_conditioning_variant_defaults_to_legacy_film_without_gates():
    assert infer_conditioning_variant({}, {"film.beta1.weight": torch.zeros((4, 8))}) == "film"
    assert infer_conditioning_variant({}, {"film.gate1.weight": torch.zeros((4, 8))}) == "adaln_zero"


def test_build_conditioning_cfg_preserves_condition_size_and_sets_class_count():
    cfg = build_conditioning_cfg(
        {"condition_size": 8},
        {"film.beta1.weight": torch.zeros((4, 8))},
        mode="class_id",
        num_classes=16,
    )
    assert cfg["mode"] == "class_id"
    assert cfg["variant"] == "film"
    assert cfg["condition_size"] == 8
    assert cfg["num_classes"] == 16
    assert cfg["zero_for_absent"] is True
    assert cfg["use_zero_for_null"] is True


def test_average_normalized_embeddings_matches_expected_mean():
    embeddings = torch.tensor(
        [
            [3.0, 0.0],
            [0.0, 4.0],
        ],
        dtype=torch.float32,
    )
    averaged = average_normalized_embeddings(embeddings)
    expected = torch.tensor([0.5, 0.5], dtype=torch.float32)
    assert torch.allclose(averaged, expected, atol=1e-6)


def test_executorch_wrapper_maps_zero_label_vector_to_null_class_id():
    captured: dict[str, torch.Tensor] = {}

    class DummyModel:
        def separate_class_ids(self, mixture, class_ids):
            captured["mixture"] = mixture
            captured["class_ids"] = class_ids
            return mixture

    wrapper = ExecuTorchCategoryExportWrapper(DummyModel(), null_class_id=15)
    mixture = torch.ones((1, 1, 32000), dtype=torch.float32)
    label_vector = torch.zeros((1, 15), dtype=torch.float32)

    output = wrapper(mixture, label_vector)

    assert torch.equal(output, mixture)
    assert torch.equal(captured["class_ids"], torch.tensor([15], dtype=torch.long))


def test_export_onnx_model_disables_mha_fastpath_during_export(monkeypatch):
    if not hasattr(getattr(torch.backends, "mha", None), "set_fastpath_enabled"):
        return

    from ai.export.freeze_codecsep_dnrv2_15cat import export_onnx_model

    observed: dict[str, object] = {}

    def fake_export(model, args, output_path, **kwargs):
        observed["during_export"] = torch.backends.mha.get_fastpath_enabled()

    fake_onnx = types.SimpleNamespace(
        load=lambda path: {"path": str(path)},
        checker=types.SimpleNamespace(check_model=lambda model: observed.setdefault("checked", model)),
    )

    output_path = Path(".pytest_tmp") / "codecsep_fake.onnx"
    monkeypatch.setattr(torch.onnx, "export", fake_export)
    monkeypatch.setitem(sys.modules, "onnx", fake_onnx)

    original = torch.backends.mha.get_fastpath_enabled()
    torch.backends.mha.set_fastpath_enabled(True)
    try:
        export_onnx_model(torch.nn.Identity(), output_path)
    finally:
        torch.backends.mha.set_fastpath_enabled(original)

    assert observed["during_export"] is False
    assert observed["checked"] == {"path": str(output_path)}
    assert torch.backends.mha.get_fastpath_enabled() is original
