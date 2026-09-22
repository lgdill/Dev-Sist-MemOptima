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
powershell -NoProfile -ExecutionPolicy Bypass -Command "$cs = Get-WmiObject Win32_ComputerSystem; $cs.AutomaticManagedPagefile = $true; $cs.Put(); Write-Host 'OK: AutomaticManagedPagefile = True'"

echo [2/2] Configurando pagefile padrao no C: (caso necessario)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "
$existing = Get-WmiObject Win32_PageFileSetting
if (-not $existing) {
    Set-WmiInstance -Class Win32_PageFileSetting -Arguments @{Name='C:\pagefile.sys'; InitialSize=0; MaximumSize=0}
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
