@echo off
title Rditrix WMS Lite V6.9
cd /d "%~dp0"

set PY=
python --version >nul 2>nul && set PY=python
if not defined PY (
    py -3 --version >nul 2>nul && set PY=py -3
)
if not defined PY (
    echo [ERROR] Python not found.
    echo Install from https://www.python.org/downloads/
    echo IMPORTANT: check "Add python.exe to PATH" during install.
    pause
    exit /b
)

%PY% -c "import ttkbootstrap" >nul 2>nul
if errorlevel 1 (
    echo First run: installing ttkbootstrap...
    %PY% -m pip install ttkbootstrap
)

%PY% main.py
if errorlevel 1 (
    echo.
    echo [ERROR] The program exited with an error. See message above.
    pause
)
