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
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_ComputerSystem | Set-CimInstance -Property @{AutomaticManagedPagefile=$false}; Write-Host 'OK: AutomaticManagedPagefile = False'"

echo.
echo [3/4] Fixando pagefile.sys no C: em exatos 4096 MB (4 GB)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_PageFileSetting | Remove-CimInstance; New-CimInstance -ClassName Win32_PageFileSetting -Property @{Name='C:\pagefile.sys'; InitialSize=4096; MaximumSize=4096} | Out-Null; Write-Host 'OK: Pagefile travado em 4 GB (Evita fragmentacao no SSD)'"

echo [4/4] Agendando restauracao automatica para a proxima reinicializacao...
schtasks /create /tn "MemOptimaRestore" /tr "powershell.exe -WindowStyle Hidden -NoProfile -Command 'Get-CimInstance Win32_ComputerSystem | Set-CimInstance -Property @{AutomaticManagedPagefile=$true}; Unregister-ScheduledTask -TaskName MemOptimaRestore -Confirm:$false'" /sc onstart /ru SYSTEM /rl HIGHEST /f >nul 2>&1
echo OK: O limite de 4GB sera revertido automaticamente apos esta sessao (temporario).

echo.
echo =====================================================
echo  PRONTO! Reinicie o computador para aplicar.
echo  Apos reiniciar, o Windows estara travado em 4GB
echo  apenas durante AQUELA sessao. Na proxima vez que 
echo  reiniciar, voltara ao normal automaticamente!
echo =====================================================
echo.
pause
