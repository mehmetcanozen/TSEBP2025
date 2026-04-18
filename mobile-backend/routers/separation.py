import os
import uuid
from pathlib import Path

import numpy as np
import onnxruntime as ort
import soundfile as sf
import torch
import torchaudio
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from core.mobile_model_bundle import load_packaged_model

router = APIRouter(prefix="/separation", tags=["Ses AyrÄ±ÅŸtÄ±rma"])


def _resolve_runtime_spec():
    model = load_packaged_model()
    if "desktop" in model.platforms:
        platform = model.platform("desktop")
        return model, platform, model.artifact_path("desktop")
    if "android" in model.platforms and model.platform("android").runtime_kind.startswith("onnx"):
        platform = model.platform("android")
        return model, platform, model.artifact_path("android")
    raise RuntimeError("No ONNX-capable packaged model is available for server-side separation")


MODEL_SPEC, MODEL_PLATFORM, MODEL_PATH = _resolve_runtime_spec()
UPLOAD_DIR = Path("temp_separation")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

CATEGORIES = [str(category["id"]) for category in MODEL_SPEC.categories]
SAMPLE_RATE = int(MODEL_PLATFORM.sample_rate)
SEGMENT_SECONDS = float(MODEL_PLATFORM.segment_seconds or 5.0)
CHUNK_SAMPLES = int(MODEL_PLATFORM.chunk_samples or round(SAMPLE_RATE * SEGMENT_SECONDS))
STATE_TENSORS = MODEL_PLATFORM.state_tensors or {}
RUNTIME_KIND = MODEL_PLATFORM.runtime_kind

ort_session = None


def init_model():
    global ort_session

    if not MODEL_PATH.exists():
        print(f"[ERROR] Model file not found: {MODEL_PATH}")
        return

    print(f"[OK] Loading packaged separation model from {MODEL_PATH}")
    ort_session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])


def cleanup_file(filepath: str):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as exc:
        print(f"Cleanup error: {exc}")


def _run_audiosep_category(waveform: torch.Tensor, category_index: int) -> np.ndarray:
    total_samples = waveform.shape[1]
    num_segments = (total_samples + CHUNK_SAMPLES - 1) // CHUNK_SAMPLES
    processed_chunks: list[np.ndarray] = []

    for index in range(num_segments):
        start = index * CHUNK_SAMPLES
        end = min(start + CHUNK_SAMPLES, total_samples)
        chunk = waveform[:, start:end]
        actual_chunk_len = chunk.shape[1]
        if actual_chunk_len < CHUNK_SAMPLES:
            chunk = torch.nn.functional.pad(chunk, (0, CHUNK_SAMPLES - actual_chunk_len))

        model_input = chunk.unsqueeze(0).numpy().astype(np.float32)
        outputs = ort_session.run(
            None,
            {
                "mixture": model_input,
                "category_idx": np.array([category_index], dtype=np.int64),
            },
        )
        processed_segment = outputs[0][0][0]
        if actual_chunk_len < CHUNK_SAMPLES:
            processed_segment = processed_segment[:actual_chunk_len]
        processed_chunks.append(processed_segment)

    return np.concatenate(processed_chunks) if processed_chunks else np.zeros(0, dtype=np.float32)


def _zero_state(name: str) -> np.ndarray:
    shape = STATE_TENSORS.get(name)
    if not shape:
        raise RuntimeError(f"State tensor '{name}' is missing from the packaged model metadata")
    return np.zeros(shape, dtype=np.float32)


def _run_waveformer_category(waveform: torch.Tensor, category_index: int) -> np.ndarray:
    total_samples = waveform.shape[1]
    label_vector = np.zeros((1, len(CATEGORIES)), dtype=np.float32)
    label_vector[0, category_index] = 1.0
    enc_buf = _zero_state("enc_buf")
    dec_buf = _zero_state("dec_buf")
    out_buf = _zero_state("out_buf")
    processed_chunks: list[np.ndarray] = []

    start = 0
    while start < total_samples:
        end = min(start + CHUNK_SAMPLES, total_samples)
        chunk = waveform[0, start:end].numpy().astype(np.float32)
        actual_chunk_len = chunk.shape[0]
        padded = np.zeros(CHUNK_SAMPLES, dtype=np.float32)
        padded[:actual_chunk_len] = chunk[:actual_chunk_len]
        stereo = np.stack([padded, padded], axis=0)[None, :, :]

        outputs = ort_session.run(
            None,
            {
                "mixture": stereo,
                "label_vector": label_vector,
                "enc_buf": enc_buf,
                "dec_buf": dec_buf,
                "out_buf": out_buf,
            },
        )
        target_chunk = outputs[0][0]
        enc_buf = outputs[1]
        dec_buf = outputs[2]
        out_buf = outputs[3]
        processed_chunks.append(target_chunk.mean(axis=0)[:actual_chunk_len])
        start = end

    return np.concatenate(processed_chunks) if processed_chunks else np.zeros(0, dtype=np.float32)


@router.post("/ping")
async def separation_ping():
    return {"message": "Separation router is reachable via POST"}


@router.post("/separate")
async def separate_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target: str = Form("speech"),
):
    print(f"[DEBUG] Received separation request for target: {target}")
    if ort_session is None:
        init_model()
        if ort_session is None:
            raise HTTPException(status_code=500, detail="Model is not initialized")

    if target not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid target category. Available: {CATEGORIES}")

    category_idx = CATEGORIES.index(target)
    file_id = str(uuid.uuid4())
    input_path = UPLOAD_DIR / f"{file_id}_in.wav"
    output_path = UPLOAD_DIR / f"{file_id}_out.wav"

    try:
        content = await file.read()
        with open(input_path, "wb") as handle:
            handle.write(content)

        try:
            waveform_np, sr = sf.read(str(input_path))
            if len(waveform_np.shape) == 1:
                waveform = torch.from_numpy(waveform_np).float().unsqueeze(0)
            else:
                waveform = torch.from_numpy(waveform_np).float().T
        except Exception as exc:
            print(f"[ERROR] soundfile load failed: {exc}")
            raise HTTPException(status_code=500, detail=f"Failed to load audio file: {exc}") from exc

        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)

        if sr != SAMPLE_RATE:
            resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=SAMPLE_RATE)
            waveform = resampler(waveform)

        if RUNTIME_KIND == "onnx_streaming_target_extractor":
            separated_audio = _run_waveformer_category(waveform, category_idx)
        else:
            separated_audio = _run_audiosep_category(waveform, category_idx)

        sf.write(str(output_path), separated_audio, SAMPLE_RATE)
        background_tasks.add_task(cleanup_file, str(input_path))

        return {
            "status": "success",
            "url": f"/outputs/{output_path.name}",
            "model_id": MODEL_SPEC.model_id,
        }
    except HTTPException:
        if input_path.exists():
            cleanup_file(str(input_path))
        if output_path.exists():
            cleanup_file(str(output_path))
        raise
    except Exception as exc:
        if input_path.exists():
            cleanup_file(str(input_path))
        if output_path.exists():
            cleanup_file(str(output_path))
        print(f"[ERROR] Separation failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


try:
    init_model()
except Exception:
    pass
