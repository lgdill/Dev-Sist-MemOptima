@echo off
title MemOptima v3.3 — Build .EXE
color 0A

echo.
echo  ================================================
echo   MemOptima v3.3 — Compilando para .EXE
echo  ================================================
echo.

:: Instala dependencias
echo [1/4] Instalando dependencias...
pip install pystray Pillow psutil pyinstaller --quiet

echo.
echo [2/4] Limpando builds anteriores...
if exist "dist\MemOptima.exe" del /f /q "dist\MemOptima.exe"
if exist "build"              rmdir /s /q "build"

echo.
echo [3/4] Compilando com PyInstaller...
pyinstaller ^
  --onefile ^
  --windowed ^
  --noconsole ^
  --name "MemOptima" ^
  --icon=NONE ^
  --hidden-import=pystray._win32 ^
  --hidden-import=PIL ^
  --hidden-import=PIL.Image ^
  --hidden-import=PIL.ImageDraw ^
  --hidden-import=vram_compressor ^
  --add-data "shared;shared" ^
  --add-data "vram_compressor.py;." ^
  --add-data "config.example.json;." ^
  memoptima.py

echo.
echo [4/4] Verificando resultado...
echo.
if exist "dist\MemOptima.exe" (
    echo  [OK] dist\MemOptima.exe gerado com sucesso!
    echo.
    echo  Conteudo do dist\:
    dir /b "dist\"
    echo.
    echo  Para rodar como admin (recomendado):
    echo  Clique direito em MemOptima.exe - Executar como Administrador
    echo.
    echo  NOTA: O vram_compressor.py foi incluido automaticamente no .exe
    echo        via --add-data. Nenhuma copia manual necessaria.
) else (
    echo  [ERRO] Falha ao gerar o .exe. Verifique os logs acima.
)

echo.
pause
