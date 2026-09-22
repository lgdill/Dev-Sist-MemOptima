@echo off
echo ===================================================
echo Restaurando a Memoria Virtual para o padrao do Sistema...
echo ===================================================

:: Verifica se esta executando como Administrador
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Privilegios de Administrador confirmados.
) else (
    echo Solicitando privilegios de administrador...
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    del "%temp%\getadmin.vbs"
    exit /B
)

echo.
echo Restaurando configuracoes de memoria virtual (Pagefile)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_ComputerSystem | Set-CimInstance -Property @{AutomaticManagedPagefile=$true}"

echo.
echo ===================================================
echo CONCLUIDO! A memoria virtual foi definida para ser
echo gerenciada pelo sistema.
echo.
echo POR FAVOR, REINICIE O COMPUTADOR PARA APLICAR AS MUDANCAS.
echo ===================================================
pause
