@echo off
:: Relança o MemOptima com privilégios de Administrador
:: Isso ativa a Layer 3: NtSetSystemInformation (flush sistema)

set PYTHON_EXE=python
if exist "%~dp0.venv\Scripts\python.exe" (
    set PYTHON_EXE="%~dp0.venv\Scripts\python.exe"
)

PowerShell -Command "Start-Process '%PYTHON_EXE%' -ArgumentList 'memoptima.py' -Verb RunAs -WorkingDirectory '%~dp0'"
