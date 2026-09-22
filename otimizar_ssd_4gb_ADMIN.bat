@echo off
echo =====================================================
echo  MemOptima - Otimizacao de SSD e Trava de Swap (4GB)
echo =====================================================

:: Verificar se eh admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Execute este arquivo como Administrador!
    echo Clique com botao direito -^> "Executar como administrador"
    pause
    exit /b 1
)

echo [1/3] Ativando TRIM para o SSD (Evita perda de velocidade)...
fsutil behavior set DisableDeleteNotify 0
echo OK: TRIM ativado.

echo.
echo [2/3] Desativando gerenciamento automatico do pagefile...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$cs = Get-WmiObject Win32_ComputerSystem; $cs.AutomaticManagedPagefile = $false; $cs.Put(); Write-Host 'OK: AutomaticManagedPagefile = False'"

echo.
echo [3/3] Fixando pagefile.sys no C: em exatos 4096 MB (4 GB)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "
$pagefiles = Get-WmiObject Win32_PageFileSetting
if ($pagefiles) {
    foreach ($pf in $pagefiles) {
        $pf.Delete()
    }
}
Set-WmiInstance -Class Win32_PageFileSetting -Arguments @{Name='C:\pagefile.sys'; InitialSize=4096; MaximumSize=4096} | Out-Null
Write-Host 'OK: Pagefile travado em 4 GB (Evita fragmentacao no SSD)'
"

echo.
echo =====================================================
echo  PRONTO! Reinicie o computador para aplicar.
echo  Apos reiniciar, o Windows estara travado em 4GB
echo  de memoria virtual e o SSD estara otimizado.
echo =====================================================
echo.
pause
