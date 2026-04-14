#!/usr/bin/env python3
"""
PyTorch modelini ONNX formatına dönüştür.
Kullanım: python scripts/convert_to_onnx.py --model model.pt --output model.onnx --input_len 16000
"""
import argparse
import torch


def convert(model_path: str, output_path: str, input_len: int, model_class=None):
    """
    model_class: Kendi model sınıfını buraya geçir.
    Örneğin:
        from myproject.model import AudioSeparator
        convert("model.pt", "model.onnx", 16000, AudioSeparator)
    """
    print(f"📂 Model yükleniyor: {model_path}")

    if model_class:
        model = model_class()
        model.load_state_dict(torch.load(model_path, map_location="cpu"))
    else:
        # Direkt state dict değil, tam model kaydedilmişse
        model = torch.load(model_path, map_location="cpu")

    model.eval()

    # Örnek input — modelinizin beklediği shape'e göre düzenle
    dummy_input = torch.randn(1, 1, input_len)  # [batch, channel, samples]

    print(f"⚙️  ONNX'e dönüştürülüyor → {output_path}")
    torch.onnx.export(
        model,
        dummy_input,
        output_path,
        opset_version=17,
        input_names=["audio_input"],
        output_names=["audio_output"],
        dynamic_axes={
            "audio_input":  {0: "batch", 2: "audio_length"},
            "audio_output": {0: "batch", 2: "audio_length"},
        },
        export_params=True,
    )
    print("✅ Dönüştürme tamamlandı!")

    # Doğrulama
    try:
        import onnx
        onnx_model = onnx.load(output_path)
        onnx.checker.check_model(onnx_model)
        print("✅ ONNX model geçerli")
    except ImportError:
        print("⚠️  onnx paketi yok, doğrulama atlandı (pip install onnx)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model",     required=True,  help="model.pt yolu")
    parser.add_argument("--output",    required=True,  help="model.onnx çıkış yolu")
    parser.add_argument("--input_len", default=16000,  type=int, help="Örnek ses uzunluğu (sample)")
    args = parser.parse_args()

    convert(args.model, args.output, args.input_len)
