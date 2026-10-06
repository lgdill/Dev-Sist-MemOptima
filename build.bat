@echo off
title MemOptima v3.2 ULTIMATE — Build .EXE
color 0A

echo.
echo  ================================================
echo   MemOptima v3.2 ULTIMATE — Compilando para .EXE
echo  ================================================
echo.

:: Instala dependencias
echo [1/3] Instalando dependencias...
pip install pystray Pillow psutil pyinstaller --quiet

echo.
echo [2/3] Compilando com PyInstaller...
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
  --add-data "shared;shared" ^
  memoptima.py

echo.
echo [3/3] Pronto!
echo.
if exist "dist\MemOptima.exe" (
    echo  [OK] dist\MemOptima.exe gerado com sucesso!
    echo.
    echo  Para rodar como admin (recomendado):
    echo  Clique direito em MemOptima.exe - Executar como Administrador
    echo.
    echo  NOTA: O vram_compressor.py deve estar na mesma pasta do .exe
    echo        para que o botao "Compressor RAM" funcione corretamente.
) else (
    echo  [ERRO] Falha ao gerar o .exe. Verifique os logs acima.
)

echo.
pause
