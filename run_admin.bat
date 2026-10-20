@echo off
:: Relança o MemOptima com privilégios de Administrador
:: Isso ativa a Layer 3: NtSetSystemInformation (flush sistema)

cd /d "%~dp0"

:: 1. Se já existir o executável compilado (.EXE), lança direto sem console
if exist "dist\MemOptima.exe" (
    PowerShell -NoProfile -Command "Start-Process 'dist\MemOptima.exe' -Verb RunAs -WorkingDirectory '%~dp0' -WindowStyle Hidden"
    exit /b 0
)

:: 2. Em modo script, usa pythonw.exe para NÃO manter a janela preta do CMD aberta
set "PYTHON_EXE=pythonw"
if exist ".venv\Scripts\pythonw.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\pythonw.exe"
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
)

PowerShell -NoProfile -Command "Start-Process '%PYTHON_EXE%' -ArgumentList 'memoptima.py' -Verb RunAs -WorkingDirectory '%~dp0' -WindowStyle Hidden"
exit /b 0
