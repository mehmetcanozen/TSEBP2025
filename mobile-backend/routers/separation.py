import os
import io
import uuid
import numpy as np
import torch
import torchaudio
import onnxruntime as ort
import soundfile as sf
from fastapi import APIRouter, File, UploadFile, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from core.config import settings

router = APIRouter(prefix="/separation", tags=["Ses Ayrıştırma"])

# Configuration
MODELS_DIR = Path("model_store/15cat")
MODEL_PATH = MODELS_DIR / "frozensep_hive_15cat.onnx"
CHECKPOINT_PATH = MODELS_DIR / "frozensep_hive_15cat.pt"
UPLOAD_DIR = Path("temp_separation")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Model Metadata (Loaded once)
CATEGORIES = []
SAMPLE_RATE = 32000
SEGMENT_SAMPLES = 160000

# Global session to avoid reloading model on every request
ort_session = None

def init_model():
    global ort_session, CATEGORIES, SAMPLE_RATE, SEGMENT_SAMPLES
    
    if not MODEL_PATH.exists():
        print(f"[ERROR] Model file not found: {MODEL_PATH}")
        return

    print(f"[OK] Loading 15-Category Separation Model from {MODEL_PATH}")
    
    # Load metadata from checkpoint
    if CHECKPOINT_PATH.exists():
        try:
            ckpt = torch.load(CHECKPOINT_PATH, map_location='cpu', weights_only=False)
            CATEGORIES = ckpt.get('categories', [])
            SAMPLE_RATE = ckpt.get('sample_rate', 32000)
            print(f"[OK] Loaded metadata: SR={SAMPLE_RATE}, Categories={len(CATEGORIES)}")
        except Exception as e:
            print(f"[WARN] Failed to load metadata from .pt: {e}")
            # Fallback categories if .pt load fails
            CATEGORIES = [
                'speech', 'music', 'dog barking', 'car engine', 'footsteps', 
                'rain', 'wind', 'keyboard typing', 'phone ringing', 'crowd noise', 
                'bird singing', 'water flowing', 'door knocking', 'alarm', 'background noise'
            ]
    
    providers = ['CPUExecutionProvider']
    # Check for GPU if available (optional for CPU-only servers)
    ort_session = ort.InferenceSession(str(MODEL_PATH), providers=providers)

def cleanup_file(filepath: str):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            # print(f"Cleaned up {filepath}")
    except Exception as e:
        print(f"Cleanup error: {e}")

@router.post("/ping")
async def separation_ping():
    return {"message": "Separation router is reachable via POST"}

@router.post("/separate")
async def separate_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target: str = Form("speech")
):
    print(f"[DEBUG] Received separation request for target: {target}")
    if ort_session is None:
        init_model()
        if ort_session is None:
            raise HTTPException(status_code=500, detail="Model is not initialized")

    # 1. Validation
    if target not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid target category. Available: {CATEGORIES}")

    category_idx = CATEGORIES.index(target)
    
    file_id = str(uuid.uuid4())
    input_path = UPLOAD_DIR / f"{file_id}_in.wav"
    output_path = UPLOAD_DIR / f"{file_id}_out.wav"

    # 2. Save Upload
    try:
        content = await file.read()
        with open(input_path, "wb") as f:
            f.write(content)
            
        # 3. Load and Preprocess Audio
        try:
            # We use soundfile instead of torchaudio to avoid TorchCodec/FFmpeg dependency issues
            waveform_np, sr = sf.read(str(input_path))
            
            # soundfile returns (samples, channels) - Convert to (channels, samples)
            if len(waveform_np.shape) == 1:
                # Mono: (samples,) -> (1, samples)
                waveform = torch.from_numpy(waveform_np).float().unsqueeze(0)
            else:
                # Stereo: (samples, channels) -> (channels, samples)
                waveform = torch.from_numpy(waveform_np).float().T
        except Exception as load_e:
            print(f"[ERROR] soundfile load failed: {load_e}")
            raise HTTPException(status_code=500, detail=f"Failed to load audio file: {str(load_e)}")
            
        # Convert to Mono if double channel
        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)
            
        # Resample to model SR
        if sr != SAMPLE_RATE:
            resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=SAMPLE_RATE)
            waveform = resampler(waveform)
            
        # 4. Inference (Chunked Processing for Longer Audio)
        total_samples = waveform.shape[1]
        num_segments = (total_samples + SEGMENT_SAMPLES - 1) // SEGMENT_SAMPLES
        processed_chunks = []
        
        print(f"[Separation] Processing '{target}' | Total samples: {total_samples} | Segments: {num_segments}")

        for i in range(num_segments):
            start = i * SEGMENT_SAMPLES
            end = min(start + SEGMENT_SAMPLES, total_samples)
            chunk = waveform[:, start:end]
            
            # Pad if needed (mandatory for fixed ONNX input shape)
            actual_chunk_len = chunk.shape[1]
            if actual_chunk_len < SEGMENT_SAMPLES:
                pad_len = SEGMENT_SAMPLES - actual_chunk_len
                chunk = torch.nn.functional.pad(chunk, (0, pad_len))
            
            # Prepare for model (Batch, Channel, Samples) -> [1, 1, 160000]
            model_input = chunk.unsqueeze(0).numpy().astype(np.float32)
            
            inputs = {
                "mixture": model_input,
                "category_idx": np.array([category_idx], dtype=np.int64)
            }
            
            # Run model on this segment
            outputs = ort_session.run(None, inputs)
            processed_segment = outputs[0][0][0] # Result shape (160000,)

            # Trim padding from the results of the last segment to maintain exact duration
            if actual_chunk_len < SEGMENT_SAMPLES:
                processed_segment = processed_segment[:actual_chunk_len]
                
            processed_chunks.append(processed_segment)
            print(f"  [OK] Processed segment {i+1}/{num_segments}")

        # Stitch all chunks back together
        separated_audio = np.concatenate(processed_chunks)

        # 5. Save Result
        # We'll save it at its generated sample rate (32kHz)
        sf.write(str(output_path), separated_audio, SAMPLE_RATE)

        # Clean up input file as usual
        background_tasks.add_task(cleanup_file, str(input_path))
        
        # We don't clean up output immediately as the client needs to download it.
        # Use a longer-term cleanup or just leave it for now in temp.
        
        download_url = f"/outputs/{output_path.name}"
        print(f"[Separation] Done. Download URL: {download_url}")

        return {
            "status": "success",
            "url": download_url
        }

    except Exception as e:
        if input_path.exists(): cleanup_file(str(input_path))
        if output_path.exists(): cleanup_file(str(output_path))
        print(f"[ERROR] Separation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Initialize on import
try:
    init_model()
except:
    pass
