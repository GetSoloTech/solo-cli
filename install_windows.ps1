<# 
Solo Server – Windows Installer
Command to run the installer:
  powershell -ExecutionPolicy Bypass -File .\install_windows.ps1
#>

# --- Ensure user-local Python bin directory is in PATH (for uv, pipx etc) ---
$UserPath = [System.Environment]::GetEnvironmentVariable('Path', 'User')
$BinPath = "$env:USERPROFILE\.local\bin"
$PathWasChanged = $false
if ($UserPath -notlike "*$BinPath*") {
    [System.Environment]::SetEnvironmentVariable('Path', "$UserPath;$BinPath", 'User')
    # Also add to the current process PATH so this script can use tools immediately
    if ($env:Path -notlike "*$BinPath*") { $env:Path = "$env:Path;$BinPath" }
    Write-Host "`n✔️  Added $BinPath to your user PATH and this session's PATH." -ForegroundColor Green
    $PathWasChanged = $true
} else {
    Write-Host "`n$BinPath already in your user PATH." -ForegroundColor Yellow
}

# Continue without exiting; this session has PATH updated. You may still need to
# restart future terminals for the persistent user PATH to be picked up.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "`n=== Solo Server – Windows Installation ===`n" -ForegroundColor Cyan

function Have($cmd) { $null -ne (Get-Command $cmd -ErrorAction SilentlyContinue) }

# --- 0) Pre-flight: where are we? --------------------------------------------
if (-not (Test-Path ".git")) {
  Write-Warning "This doesn't look like the repo root ('.git' not found). Continuing anyway..."
}

# --- 1) Ensure Python 3.12 is available -------------------------------------
$wantPy = "3.12"
Write-Host "Checking for Python $wantPy..." -ForegroundColor Cyan
$hasPy = $false
try {
  & py -$wantPy --version | Out-Null
  if ($LASTEXITCODE -eq 0) { $hasPy = $true }
} catch { }

if (-not $hasPy) {
  Write-Host "Python $wantPy not found via 'py' launcher. Attempting install with winget..." -ForegroundColor Yellow
  if (-not (Have winget)) {
    throw "winget is not available. Install Python $wantPy manually from https://www.python.org/downloads/windows/ then re-run."
  }
  winget install --id Python.Python.3.12 -e --source winget --accept-source-agreements --accept-package-agreements
  Write-Host "Re-checking Python $wantPy..." -ForegroundColor Yellow
  & py -$wantPy --version | Out-Host
}

# --- 2) Ensure uv is installed ----------------------------------------------
Write-Host "Checking for 'uv'..." -ForegroundColor Cyan
if (-not (Have uv)) {
  Write-Host "Installing uv..." -ForegroundColor Yellow

# irm https://astral.sh/uv/install.ps1 | iex
  $script = Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1'
  Invoke-Expression $script

  if (-not (Have uv)) {
    throw "uv installation appears to have failed. Close/reopen PowerShell and try again."
  }
}
uv --version | Out-Host

# --- 3) Create (or reuse) the venv ------------------------------------------
$venv = "solo_venv"  # matches Mac docs
if (Test-Path ".\$venv") {
  Write-Host "Virtual environment '$venv' already exists. Reusing it." -ForegroundColor Yellow
} else {
  Write-Host "Creating virtual environment '$venv' with Python $wantPy..." -ForegroundColor Cyan
  uv venv $venv --python $wantPy
}

# --- 4) Optional: seed .env from example -------------------------------------
if ((Test-Path ".\.env") -eq $false -and (Test-Path ".\.env.example")) {
  Copy-Item ".\.env.example" ".\.env"
  Write-Host "Created .env from .env.example (edit as needed)." -ForegroundColor DarkCyan
}

# --- 5) Set env vars for mujoco (if your project needs them) -----------------
# Adjust as needed; harmless if not used.
$env:MUJOCO_PATH = ""
$env:MUJOCO_GL   = "osmesa"

# --- 6) Activate & install in editable mode with fallback --------------------
Write-Host "Activating venv and installing project (editable)..." -ForegroundColor Cyan
$activate = ".\$venv\Scripts\Activate.ps1"
if (-not (Test-Path $activate)) { throw "Activate script not found at $activate" }

# Tip: one subshell so we don't permanently modify this window's PATH
$installBlock=@'
& "$env:ACTIVATE"
try {
  uv pip install -e .
} catch {
  Write-Host "Primary install failed. Trying fallback path..." -ForegroundColor Yellow
  uv pip install typer GPUtil psutil requests rich huggingface_hub pydantic transformers accelerate num2words
  uv pip install lerobot --no-deps
  uv pip install torch torchvision torchaudio
  uv pip install gymnasium
  uv pip install opencv-python
  uv pip install pillow
  uv pip install -e .
}
'@

$env:ACTIVATE = (Resolve-Path $activate).Path
powershell -NoProfile -ExecutionPolicy Bypass -Command $installBlock

Write-Host ""
Write-Host "✅ Installation completed."
Write-Host "To start using it in this shell, run:"
Write-Host "  .\$venv\Scripts\Activate.ps1"
Write-Host "Then verify:"
Write-Host "  python --version  (should be $wantPy.x)"
Write-Host "  pip list"
Write-Host ""
Write-Host "  solo --help"
Write-Host ""

