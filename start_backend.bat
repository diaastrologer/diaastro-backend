@echo off
title DiaAstro Backend
echo.
echo ============================================
echo   DiaAstro AI Backend - Starting...
echo ============================================
echo.

:: Navigate to the backend folder (edit this path if needed)
cd /d "%~dp0"

:: Check if venv exists, create if not
if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Could not create virtual environment.
        echo Make sure Python 3.9+ is installed and on PATH.
        pause
        exit /b 1
    )
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Install/upgrade dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet

:: Start Flask
echo.
echo Starting Flask server on http://localhost:5000
echo Press Ctrl+C to stop.
echo.
python app.py

pause
