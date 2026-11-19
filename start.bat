@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PROJECT_DIR=%~dp0"
set "ENV_DIR=%PROJECT_DIR%.venv"
set "ENV_PY=%ENV_DIR%\Scripts\python.exe"

rem Reuse the project environment only when it belongs to a working Python install.
if exist "%ENV_PY%" (
    "%ENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if not errorlevel 1 goto check_dependencies
    echo The existing .venv is not usable on this computer.
    set "ENV_DIR=%PROJECT_DIR%.venv-laptop"
    set "ENV_PY=%ENV_DIR%\Scripts\python.exe"
)

if exist "%ENV_PY%" (
    "%ENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if not errorlevel 1 goto check_dependencies
    echo The .venv-laptop environment is also not usable.
    goto setup_error
)

rem Find an installed Python 3.10+ and create a fresh per-laptop environment.
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if not errorlevel 1 (
        echo Creating a Python environment for this laptop...
        py -3 -m venv "%ENV_DIR%"
        if errorlevel 1 goto setup_error
        goto check_dependencies
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
    if not errorlevel 1 (
        echo Creating a Python environment for this laptop...
        python -m venv "%ENV_DIR%"
        if errorlevel 1 goto setup_error
        goto check_dependencies
    )
)

echo.
echo Python 3.10 or newer was not found.
echo Install Python from https://www.python.org/downloads/windows/
echo During installation, enable "Add python.exe to PATH", then run start.bat again.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:check_dependencies
"%ENV_PY%" -c "import fastapi, uvicorn, pydantic, multipart, pwdlib, argon2, pypdf, dotenv, tzdata" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages. This may take a few minutes on first launch...
    "%ENV_PY%" -m pip install -r "%PROJECT_DIR%requirements.txt"
    if errorlevel 1 goto setup_error
)

if /i "%~1"=="--create-admin" goto create_admin

echo.
echo Starting CareerAdapt AI. Keep this window open while using the website.
echo The browser will open the login page at http://127.0.0.1:8000/login when ready.
"%ENV_PY%" "%PROJECT_DIR%run.py"
set "APP_EXIT_CODE=%ERRORLEVEL%"
if not "%APP_EXIT_CODE%"=="0" (
    echo.
    echo The server stopped with an error. Read the messages above for details.
    pause
)
exit /b %APP_EXIT_CODE%

:create_admin
echo.
echo Create an administrator account. The password will not be displayed.
"%ENV_PY%" -m backend.create_admin
if errorlevel 1 (
    echo.
    echo Could not create the administrator account.
    pause
    exit /b 1
)
pause
exit /b 0

:setup_error
echo.
echo Could not prepare the Python environment or install dependencies.
echo Check the error above, confirm internet access, then run start.bat again.
pause
exit /b 1
