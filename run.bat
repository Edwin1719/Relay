@echo off
chcp 65001 >nul
set PYTHONUTF8=1
title Relay Launcher
cd /d "%~dp0"

mode con: cols=72 lines=22

echo.
echo   ##################################################
echo   #                                                #
echo   #         ^* RELAY   LAUNCHER                     #
echo   #     Asistente personal de IA                    #
echo   #                                                #
echo   ##################################################
echo.
echo   Iniciando servicios...
echo.

:: ── Buscar Python (Anaconda/Miniconda primero, luego PATH) ──
set PYTHON_CMD=

:: 1. Entorno conda activo
if not "%CONDA_PREFIX%"=="" (
    if exist "%CONDA_PREFIX%\python.exe" (
        set PYTHON_CMD=%CONDA_PREFIX%\python.exe
        goto :found_python
    )
)

:: 2. Instalaciones comunes de Anaconda/Miniconda
if exist "%USERPROFILE%\anaconda3\python.exe" set "PYTHON_CMD=%USERPROFILE%\anaconda3\python.exe"
if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Continuum\anaconda3\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Continuum\anaconda3\python.exe"
if not defined PYTHON_CMD if exist "%USERPROFILE%\miniconda3\python.exe" set "PYTHON_CMD=%USERPROFILE%\miniconda3\python.exe"
if defined PYTHON_CMD goto :found_python

:: 3. Python del PATH (evita el stub de Microsoft Store)
for /f "tokens=*" %%i in ('where python 2^>nul') do (
    set "PYTHON_CMD=%%i"
    goto :check_python
)
goto :search_python

:check_python
"%PYTHON_CMD%" --version >nul 2>&1
if %errorlevel% equ 0 goto :found_python

:search_python
:: 4. Rutas comunes de Python
if exist "C:\Python312\python.exe" set "PYTHON_CMD=C:\Python312\python.exe"
if not defined PYTHON_CMD if exist "C:\Python311\python.exe" set "PYTHON_CMD=C:\Python311\python.exe"
if not defined PYTHON_CMD if exist "C:\Program Files\Python312\python.exe" set "PYTHON_CMD=C:\Program Files\Python312\python.exe"
if defined PYTHON_CMD goto :found_python

:: No se encontro Python
cls
echo.
echo   ERROR: No se encontro Python.
echo.
echo   Asegurate de que Anaconda o Python este instalado.
echo.
echo   Descargalo desde: https://www.python.org/downloads/
echo.
pause
exit /b 1

:found_python
:: ── Verificar Node.js ──
where node >nul 2>&1
if %errorlevel% neq 0 (
    cls
    echo.
    echo   ERROR: Node.js no esta instalado o no esta en el PATH.
    echo.
    echo   Descargalo desde: https://nodejs.org/
    echo.
    pause
    exit /b 1
)

echo   Usando: %PYTHON_CMD%

:: ── Verificar/instalar dependencias Python ──
echo   [1/4] Verificando dependencias Python...
"%PYTHON_CMD%" -c "import fastapi, uvicorn, slowapi, ddgs, mcp" >nul 2>&1
if errorlevel 1 (
    echo   Instalando dependencias...
    "%PYTHON_CMD%" -m pip install -r backend\requirements.txt
    "%PYTHON_CMD%" -c "import fastapi, uvicorn, slowapi, ddgs, mcp" >nul 2>&1
    if errorlevel 1 (
        cls
        echo.
        echo   ERROR: no se pudieron instalar las dependencias de Python.
        echo   Revisa la salida de pip de arriba.
        echo.
        pause
        exit /b 1
    )
)

echo   [2/4] Verificando dependencias Node...
if not exist "frontend\node_modules" (
    call npm install --prefix frontend >nul 2>&1
)

:: ── Matar procesos previos ──
echo   [3/4] Limpiando procesos anteriores...
taskkill /f /t /fi "WINDOWTITLE eq Relay" 2>nul >nul
taskkill /f /t /fi "WINDOWTITLE eq vite*" 2>nul >nul

:: ── Lanzar run.py en ventana propia ──
echo   [4/4] Iniciando Relay...
echo.
echo   NOTA: Se abrira una ventana nueva con los logs.
echo   Para cerrar, presiona Ctrl+C en esa ventana
echo   o presiona cualquier tecla AQUI.
echo.
start "Relay" cmd /k ""%PYTHON_CMD%" run.py"

:: run.py abre el navegador cuando el frontend está listo
timeout /t 8 /nobreak >nul

echo.
echo   ##################################################
echo   #             RELAY   CORRIENDO                 #
echo   #                                                #
echo   #     Frontend: http://localhost:5173            #
echo   #     Backend:  http://127.0.0.1:8000            #
echo   #     API Docs: http://127.0.0.1:8000/docs       #
echo   #                                                #
echo   #     Para detener:                              #
echo   #      - Ctrl+C en ventana Relay                #
echo   #      - O presiona cualquier tecla AQUI         #
echo   #                                                #
echo   ##################################################
echo.
pause >nul

:: ── Detener ──
echo.
echo   Deteniendo servicios...
taskkill /f /t /fi "WINDOWTITLE eq Relay" 2>nul >nul
taskkill /f /t /fi "WINDOWTITLE eq vite*" 2>nul >nul

cls
echo.
echo   Servicios detenidos. Gracias por usar Relay.
timeout /t 2 /nobreak >nul
