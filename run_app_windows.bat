@echo off
setlocal
cd /d "%~dp0"
title Lattice
if not exist ".venv\Scripts\python.exe" py -3.13 -m venv .venv
if not exist ".venv\Scripts\python.exe" goto :error
".venv\Scripts\python.exe" ensure_runtime.py
if errorlevel 1 goto :error
set LATTICE_LOCAL_MODE=1
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1
goto :end
:error
echo Setup failed. Check the error above before trying again.
:end
pause
