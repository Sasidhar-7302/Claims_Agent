$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python not found in PATH. Please install Python 3.10+ and ensure it is on PATH."
    exit 1
}
& python -m streamlit run ui/streamlit_app.py
