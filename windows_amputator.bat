@echo off
color 0C
title Windows Amputator - Otimizacao Extrema de RAM
echo ==============================================================
echo ☢️  WINDOWS AMPUTATOR: JOGANDO SUJO PARA REDUZIR A RAM BASE ☢️
echo ==============================================================
echo.
echo AVISO: Isso ira desativar servicos nativos do Windows.
echo Pressione CTRL+C agora se quiser cancelar.
echo.
pause

echo.
echo [1/5] Desativando SysMain (Superfetch)...
sc stop "SysMain" >nul 2>&1
sc config "SysMain" start= disabled >nul 2>&1

echo [2/5] Desativando Windows Search (Indexador)...
sc stop "WSearch" >nul 2>&1
sc config "WSearch" start= disabled >nul 2>&1

echo [3/5] Desativando Telemetria da Microsoft (DiagTrack)...
sc stop "DiagTrack" >nul 2>&1
sc config "DiagTrack" start= disabled >nul 2>&1
sc stop "dmwappushservice" >nul 2>&1
sc config "dmwappushservice" start= disabled >nul 2>&1

echo [4/5] Desativando Aplicativos em Segundo Plano Globais...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications" /v GlobalUserDisabled /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy" /v LetAppsRunInBackground /t REG_DWORD /d 2 /f >nul 2>&1

echo [5/5] Matando Cortana e servicos do Xbox Live...
sc stop "XblAuthManager" >nul 2>&1
sc config "XblAuthManager" start= disabled >nul 2>&1
sc stop "XblGameSave" >nul 2>&1
sc config "XblGameSave" start= disabled >nul 2>&1
sc stop "XboxNetApiSvc" >nul 2>&1
sc config "XboxNetApiSvc" start= disabled >nul 2>&1
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Search" /v AllowCortana /t REG_DWORD /d 0 /f >nul 2>&1

echo.
echo ==============================================================
echo ✅  AMPUTACAO CONCLUIDA!
echo Os servicos que gastam memoria escondidos foram exterminados.
echo ==============================================================
echo.
echo REINICIE SEU COMPUTADOR para que o Windows abandone esses 
echo processos de vez. Ao voltar, rode o MemOptima v3 ULTIMATE.
echo.
pause
