@echo off
SETLOCAL EnableDelayedExpansion

TITLE Claims Agent - One Click Start

echo ===================================================
echo      Warranty Claims Agent - Startup Script
echo ===================================================
echo.

:: 1. Check Python
where python >nul 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found in PATH.
    echo Please install Python 3.10+ and ensure "Add to PATH" is checked.
    pause
    exit /b 1
)

:: 2. Setup Configuration
IF NOT EXIST ".env" (
    echo [SETUP] .env not found. Creating from default...
    copy ".env.example" ".env" >nul
    echo [SETUP] Created .env file.
)

:: 3. Setup Dependencies
echo [SETUP] Checking dependencies...
pip install -r requirements.txt >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [INFO] Installing missing dependencies...
    pip install -r requirements.txt
) ELSE (
    echo [OK] Dependencies ready.
)

:: 4. Check Vector Database
IF NOT EXIST "outbox\chroma_db" (
    echo [SETUP] Initializing Vector Database...
    python index_db.py
) ELSE (
    echo [OK] Vector Database found.
)

:: 5. AI Provider Check
echo.
echo [CHECK] Checking AI Provider...
where ollama >nul 2>nul
IF %ERRORLEVEL% EQU 0 (
    echo [OK] Found Ollama - Local LLM. Using local resources.
) ELSE (
    echo [INFO] Ollama not found.
    echo        Seamlessly falling back to Cloud APIs - Groq or Gemini - as configured in .env.
)

:: 6. Run Application
echo.
echo [START] Launching Claims Agent...
echo.

python -m streamlit run ui/streamlit_app.py

pause
