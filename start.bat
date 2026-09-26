@echo off

set "BACKEND=C:\Financial-Dossier\Financial-Analysis\backend"
set "FRONTEND=C:\Financial-Dossier\Financial-Analysis\frontend"

set "DEBUG_AGENT=true"

set EDGAR_IDENTITY=nm nmurugs@gmail.com

if not defined EDGAR_IDENTITY (
    echo WARNING: EDGAR_IDENTITY is not set. SEC/EdgarTools financial calls will fail.
    echo Set it before running this script, for example:
    echo   set EDGAR_IDENTITY=Your Name your.email@example.com
)
set "PATH=C:\Users\n_mur\AppData\Roaming\npm;%PATH%"

cd /d "%BACKEND%"

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create Python virtual environment.
        pause
        exit /b 1
    )
)

echo Installing/updating backend Python dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install backend Python dependencies.
    pause
    exit /b 1
)

cd /d "%FRONTEND%"

if not exist node_modules (
    echo Installing frontend dependencies...
    npm install
    if errorlevel 1 (
        echo Failed to install frontend dependencies.
        pause
        exit /b 1
    )
)

start "FastAPI" cmd /k "cd /d "%BACKEND%" && set DEBUG_AGENT=true && set PATH=C:\Users\n_mur\AppData\Roaming\npm;%%PATH%% && .venv\Scripts\python.exe -m uvicorn app.main:app --reload"

start "Next.js" cmd /k "cd /d "%FRONTEND%" && npm run dev"
