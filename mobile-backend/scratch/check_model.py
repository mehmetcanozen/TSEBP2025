import torch
import sys
import os

model_path = 'model_store/15cat/frozensep_hive_15cat.pt'

try:
    print(f"Attempting to load JIT model from {model_path}...")
    model = torch.jit.load(model_path, map_location='cpu')
    print("SUCCESS: Model is a TorchScript (JIT) model.")
    # Print some info
    print(f"Model keys: {dir(model)}")
except Exception as jit_e:
    print(f"JIT Load failed: {jit_e}")
    try:
        print("Attempting standard torch.load...")
        checkpoint = torch.load(model_path, map_location='cpu', weights_only=False)
        print("SUCCESS: Model loaded with standard torch.load.")
        if isinstance(checkpoint, dict):
            print(f"Checkpoint keys: {checkpoint.keys()}")
        else:
            print(f"Model type: {type(checkpoint)}")
    except Exception as std_e:
        print(f"Standard Load failed: {std_e}")
