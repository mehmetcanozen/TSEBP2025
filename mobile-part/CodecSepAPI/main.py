import os
import io
import time
import uuid
import wave
import numpy as np
import soundfile as sf
import torchaudio
from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks
from fastapi.responses import FileResponse
import uvicorn

app = FastAPI(title="CodecSep API")

UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ==========================================
# PLACEHOLDER: Model Loading
# ==========================================
# When the user provides the actual codecsep_code folder, 
# they can import the model classes here and load the ckpt_model_final.pth
print("Initializing CodecSep API Server...")
# model = load_codecsep_model("path/to/ckpt_model_final.pth")
# ==========================================

def cleanup_file(filepath: str):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"Cleaned up {filepath}")
    except Exception as e:
        print(f"Cleanup error: {e}")

@app.get("/")
def read_root():
    return {"status": "CodecSep API is running"}

@app.post("/separate")
async def process_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target: str = Form("mix") # e.g. typing, speech, music, noise
):
    """
    Receives an audio file from the mobile app, runs inference, and returns the cleaned audio.
    """
    start_time = time.time()
    
    # 1. Save uploaded file to disk temporarily
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}_input.wav")
    output_path = os.path.join(UPLOAD_DIR, f"{file_id}_output.wav")
    
    content = await file.read()
    with open(input_path, "wb") as f:
        f.write(content)
        
    print(f"Received file: {file.filename}, target: {target}")

    try:
        # 2. Load the audio file
        # wav, sr = torchaudio.load(input_path)
        
        # ==========================================
        # PLACEHOLDER: INFERENCE LOGIC
        # ==========================================
        # Replace this sleep block with actual model inference:
        # e.g., clean_wav = model.separate(wav, target)
        # For now, we simulate processing time and just return the original audio
        # or apply a dummy filter so the user can verify the pipeline works.
        print(f"Processing target '{target}' via placeholder pipeline...")
        await asyncio.sleep(1.5) # Simulate processing delay
        
        # Dummy behavior: copy input to output (representing the cleaned audio)
        import shutil
        shutil.copy2(input_path, output_path)
        # ==========================================
        
        process_time = time.time() - start_time
        print(f"Processing complete in {process_time:.2f}s")
        
        # 3. Schedule cleanup of temp files after response is sent
        background_tasks.add_task(cleanup_file, input_path)
        # Depending on how FileResponse works, we might need a delayed cleanup for the output, 
        # but Starlette handles FileResponse cleanup if we don't hold references to it.
        # Actually, FileResponse doesn't auto-delete by default, so we use a background task with a slight delay if needed, 
        # but standard BackgroundTasks run *after* sending the response.
        background_tasks.add_task(cleanup_file, output_path)
        
        return FileResponse(
            path=output_path,
            filename=f"clean_{file.filename}",
            media_type="audio/wav"
        )
        
    except Exception as e:
        cleanup_file(input_path)
        cleanup_file(output_path)
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
