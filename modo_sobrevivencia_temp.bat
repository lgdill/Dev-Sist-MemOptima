@echo off
title MODO SOBREVIVENCIA (1GB RAM) - Temporario
echo =====================================================
echo    MODO SOBREVIVENCIA ATIVADO - (MEMORIA EXTREMA)
echo =====================================================
echo.
echo AVISO: Isso matara a interface do Windows e varios
echo servicos para liberar o maximo de RAM possivel.
echo.
echo TUDO VOLTARA AO NORMAL QUANDO VOCE REINICIAR O PC!
echo.
pause

:: Verificar Administrador
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Por favor, feche e execute como Administrador!
    pause
    exit /b 1
)

echo.
echo [1/3] Parando Servicos Pesados (Apenas por esta sessao)...
:: Windows Update e Telemetria
net stop wuauserv /y >nul 2>&1
net stop DiagTrack /y >nul 2>&1
net stop DoSvc /y >nul 2>&1
net stop BITS /y >nul 2>&1

:: Pesquisa e Superfetch (SysMain)
net stop WSearch /y >nul 2>&1
net stop SysMain /y >nul 2>&1

:: Impressora e Temas Visuais
net stop Spooler /y >nul 2>&1
net stop Themes /y >nul 2>&1

:: Servicos Xbox e Extras
net stop XboxGipSvc /y >nul 2>&1
net stop XblAuthManager /y >nul 2>&1
net stop XblGameSave /y >nul 2>&1
net stop XboxNetApiSvc /y >nul 2>&1

echo OK: Servicos pausados.

echo.
echo [2/3] Abrindo o Gerenciador de Tarefas (Sua nova "Area de Trabalho")...
start taskmgr.exe

echo.
echo [3/3] Opcao Nuclear: Matando o Windows Explorer (Interface)...
echo A sua tela ficara preta/vazia. 
echo Para abrir programas, use o Gerenciador de Tarefas: 
echo "Arquivo -> Executar nova tarefa" (Ex: chrome.exe, cmd.exe)
echo.
echo Para voltar ao normal, basta REINICIAR O COMPUTADOR!
echo.
timeout /t 10

:: Mata a interface do Windows
taskkill /F /IM explorer.exe

exit
