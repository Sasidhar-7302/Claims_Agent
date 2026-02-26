$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python not found in PATH. Please install Python 3.10+ and ensure it is on PATH."
    exit 1
}

if (-not (Test-Path ".env")) {
    Write-Host "[SETUP] .env not found. Creating from .env.example..."
    Copy-Item ".env.example" ".env"
}

Write-Host "[SETUP] Installing dependencies (if needed)..."
python -m pip install -r requirements.txt | Out-Null

if (-not (Test-Path "outbox/chroma_db")) {
    Write-Host "[SETUP] Building initial policy index..."
    $env:EMBEDDING_MODE = "hash"
    python index_db.py
}

Write-Host "[START] Launching Streamlit app..."
python -m streamlit run ui/streamlit_app.py
