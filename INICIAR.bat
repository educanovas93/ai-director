@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0" || goto :error

rem Buscar Python 3.11 o superior sin modificar la instalacion global.
set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)
if not defined PYTHON_CMD (
    echo ERROR: Se necesita Python 3.11 o superior. Instalalo y vuelve a abrir INICIAR.bat.
    goto :error
)

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual .venv...
    %PYTHON_CMD% -m venv ".venv"
    if errorlevel 1 goto :error
)
set "VENV_PY=.venv\Scripts\python.exe"
"%VENV_PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 (
    echo ERROR: El entorno .venv no funciona o usa Python anterior a 3.11.
    echo Elimina .venv manualmente y vuelve a abrir INICIAR.bat.
    goto :error
)

rem pip comprueba requisitos y solo instala lo que falte o no sea compatible.
echo Comprobando e instalando dependencias si es necesario...
"%VENV_PY%" -m pip install --disable-pip-version-check -r "requirements.txt"
if errorlevel 1 goto :error

echo Abriendo Algunos Indios AI Director en este equipo...
"%VENV_PY%" -m backend.main
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo No se pudo iniciar Algunos Indios AI Director. Revisa el error anterior.
pause
exit /b 1
