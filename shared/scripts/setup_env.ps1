# Semantic Noise Suppression - Unified Environment Setup
# Creates a single .venv at project root for both AI and desktop development.
# Run from project root: c:\SoftwareProjects\TSEBP2025

Write-Host "=== Semantic Noise Mixer - Environment Setup ===" -ForegroundColor Cyan
Write-Host "Target: .venv (shared for AI + desktop)" -ForegroundColor Green
Write-Host ""

# Create virtual environment at project root
$venvPath = ".\.venv"
Write-Host "Creating virtual environment at $venvPath..." -ForegroundColor Yellow

if (Test-Path $venvPath) {
    Write-Host "Virtual environment already exists at $venvPath." -ForegroundColor Yellow
    $choice = Read-Host "Do you want to RECREATE it? (Existing packages will be lost) [y/N]"
    if ($choice -eq 'y' -or $choice -eq 'Y') {
        Write-Host "Removing existing environment..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $venvPath
        python -m venv $venvPath
    } else {
        Write-Host "Reusing existing environment..." -ForegroundColor Green
    }
} else {
    python -m venv $venvPath
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& "$venvPath\Scripts\Activate.ps1"

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install PyTorch with CUDA 12.8 support
Write-Host ""
Write-Host "Installing PyTorch 2.7+ with CUDA 12.8..." -ForegroundColor Yellow
Write-Host "This may take several minutes..." -ForegroundColor Gray
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

# Install desktop stack
Write-Host ""
Write-Host "Installing desktop stack..." -ForegroundColor Yellow
pip install -r desktop\requirements.txt

# Install AI stack (training + runtime)
Write-Host ""
Write-Host "Installing AI stack (training + runtime)..." -ForegroundColor Yellow
pip install -r ai\training\requirements.txt

# Install export tools
Write-Host ""
Write-Host "Installing model export tools..." -ForegroundColor Yellow
pip install "onnx>=1.14.0"
pip install "onnxruntime-gpu>=1.15.0"
pip install "onnx-tf>=1.10.0"

# Verify installations
Write-Host ""
Write-Host "=== Verifying Installation ===" -ForegroundColor Cyan

Write-Host ""
Write-Host "Checking PyTorch CUDA support..." -ForegroundColor Yellow
python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA version: {torch.version.cuda}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

Write-Host ""
Write-Host "Checking TensorFlow..." -ForegroundColor Yellow
python -c "import tensorflow as tf; print(f'TensorFlow version: {tf.__version__}'); print(f'GPU devices: {len(tf.config.list_physical_devices(\"GPU\"))}')"

# Save installed packages
Write-Host ""
Write-Host "Saving requirements to shared/requirements_generated.txt..." -ForegroundColor Yellow
pip freeze > shared\requirements_generated.txt

Write-Host ""
Write-Host "=== Setup Complete! ===" -ForegroundColor Green
Write-Host "Virtual environment: $venvPath" -ForegroundColor Gray
Write-Host "To activate: .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host ""
