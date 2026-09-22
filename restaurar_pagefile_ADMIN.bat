@echo off
echo =====================================================
echo  MemOptima - Restaurando Pagefile (Admin necessario)
echo =====================================================

:: Verificar se eh admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Execute este arquivo como Administrador!
    echo Clique com botao direito -^> "Executar como administrador"
    pause
    exit /b 1
)

echo [1/2] Restaurando gerenciamento automatico do pagefile...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_ComputerSystem | Set-CimInstance -Property @{AutomaticManagedPagefile=$true}; Write-Host 'OK: AutomaticManagedPagefile = True'"

echo [2/2] Configurando pagefile padrao no C: (caso necessario)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "
$existing = Get-CimInstance Win32_PageFileSetting
if (-not $existing) {
    New-CimInstance -ClassName Win32_PageFileSetting -Property @{Name='C:\pagefile.sys'; InitialSize=0; MaximumSize=0} | Out-Null
    Write-Host 'OK: PageFileSetting criado (gerenciado automaticamente)'
} else {
    Write-Host 'OK: PageFileSetting ja existe'
}
"

echo.
echo =====================================================
echo  PRONTO! Reinicie o computador para aplicar.
echo  O pagefile.sys sera recriado automaticamente.
echo =====================================================
echo.
pause
