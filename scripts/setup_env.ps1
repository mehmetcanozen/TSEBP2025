# Semantic Noise Suppression Environment Setup
# For Intel Core Ultra 7 265K + RTX 5070 12GB + 64GB RAM @ 6800MHz

# STEP 1: Create virtual environment
# Run from project root: c:\SoftwareProjects\TSEBP2025

Write-Host "=== Semantic Noise Mixer - Environment Setup ===" -ForegroundColor Cyan
Write-Host "Hardware: Intel Core Ultra 7 265K, RTX 5070 12GB VRAM" -ForegroundColor Green
Write-Host ""

# Create virtual environment
$venvPath = ".\desktop\.venv"
Write-Host "Creating virtual environment at $venvPath..." -ForegroundColor Yellow

if (Test-Path $venvPath) {
    Write-Host "Virtual environment already exists. Removing..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venvPath
}

python -m venv $venvPath

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& "$venvPath\Scripts\Activate.ps1"

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install PyTorch with CUDA 12.8 support (RTX 5070 Blackwell architecture)
Write-Host ""
Write-Host "Installing PyTorch 2.7+ with CUDA 12.8..." -ForegroundColor Yellow
Write-Host "This may take several minutes..." -ForegroundColor Gray
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

# Install audio processing dependencies
Write-Host ""
Write-Host "Installing audio processing libraries..." -ForegroundColor Yellow
pip install numpy>=1.24.0
pip install scipy>=1.10.0
pip install soundfile>=0.12.0
pip install sounddevice>=0.4.6
pip install PyAudio>=0.2.13
pip install librosa>=0.10.0

# Install TensorFlow (for YAMNet)
Write-Host ""
Write-Host "Installing TensorFlow and TensorFlow Hub..." -ForegroundColor Yellow
pip install tensorflow>=2.13.0
pip install tensorflow-hub>=0.16.0

# Install export dependencies
Write-Host ""
Write-Host "Installing model export tools..." -ForegroundColor Yellow
pip install onnx>=1.14.0
pip install onnxruntime-gpu>=1.15.0
pip install onnx-tf>=1.10.0

# Install audio quality metrics
Write-Host ""
Write-Host "Installing audio quality metrics (PESQ, STOI)..." -ForegroundColor Yellow
pip install pesq>=0.0.4
pip install pystoi>=0.3.3

# Install utility dependencies
Write-Host ""
Write-Host "Installing utility libraries..." -ForegroundColor Yellow
pip install pyyaml>=6.0
pip install jsonschema>=4.17.0
pip install platformdirs>=3.5.0
pip install psutil>=5.9.0
pip install tqdm>=4.65.0
pip install pytest>=7.3.0

# Verify installations
Write-Host ""
Write-Host "=== Verifying Installation ===" -ForegroundColor Cyan

# Check PyTorch CUDA availability
Write-Host ""
Write-Host "Checking PyTorch CUDA support..." -ForegroundColor Yellow
python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA version: {torch.version.cuda}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"

# Check TensorFlow
Write-Host ""
Write-Host "Checking TensorFlow..." -ForegroundColor Yellow
python -c "import tensorflow as tf; print(f'TensorFlow version: {tf.__version__}'); print(f'GPU devices: {len(tf.config.list_physical_devices(\"GPU\"))}')"

# Save installed packages
Write-Host ""
Write-Host "Saving requirements to desktop/requirements_generated.txt..." -ForegroundColor Yellow
pip freeze > desktop\requirements_generated.txt

Write-Host ""
Write-Host "=== Setup Complete! ===" -ForegroundColor Green
Write-Host "Virtual environment: $venvPath" -ForegroundColor Gray
Write-Host "To activate: .\desktop\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host ""
