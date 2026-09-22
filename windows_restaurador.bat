@echo off
color 0A
title Windows Restaurador - Desfazer Otimizacao
echo ==============================================================
echo 🚑  WINDOWS RESTAURADOR: DESFAZENDO O "JOGO SUJO" 🚑
echo ==============================================================
echo.
echo Isso ira reativar os servicos nativos do Windows que foram 
echo desativados pelo script Amputator (Pesquisa, SysMain, Xbox, etc).
echo.
pause

echo.
echo [1/5] Reativando SysMain (Superfetch)...
sc config "SysMain" start= auto >nul 2>&1
sc start "SysMain" >nul 2>&1

echo [2/5] Reativando Windows Search (Indexador)...
sc config "WSearch" start= delayed-auto >nul 2>&1
sc start "WSearch" >nul 2>&1

echo [3/5] Reativando Telemetria da Microsoft (DiagTrack)...
sc config "DiagTrack" start= auto >nul 2>&1
sc config "dmwappushservice" start= delayed-auto >nul 2>&1

echo [4/5] Restaurando Aplicativos em Segundo Plano Globais...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications" /v GlobalUserDisabled /f >nul 2>&1
reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy" /v LetAppsRunInBackground /f >nul 2>&1

echo [5/5] Restaurando Cortana e servicos do Xbox Live...
sc config "XblAuthManager" start= demand >nul 2>&1
sc config "XblGameSave" start= demand >nul 2>&1
sc config "XboxNetApiSvc" start= demand >nul 2>&1
reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Search" /v AllowCortana /f >nul 2>&1

echo.
echo ==============================================================
echo 💖  RESTAURACAO CONCLUIDA!
echo O seu Windows voltou as configuracoes originais de fabrica.
echo A pesquisa, o Xbox e os apps de fundo vao voltar a funcionar.
echo ==============================================================
echo.
echo REINICIE SEU COMPUTADOR para que os processos voltem a rodar
echo perfeitamente.
echo.
pause
