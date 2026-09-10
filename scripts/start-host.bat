@echo off
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"

if not defined VENV_DIR (
  set "VENV_DIR=%ROOT%\.venv"
)

if not defined REMOTE_TOKEN if exist "%ROOT%\.remote_token" (
  set /p REMOTE_TOKEN=<"%ROOT%\.remote_token"
)
if not defined REMOTE_TOKEN (
  set "REMOTE_TOKEN=simplesegredo"
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
  python -m venv "%VENV_DIR%"
  "%VENV_DIR%\Scripts\pip.exe" install -r requirements.txt
)

"%VENV_DIR%\Scripts\python.exe" host.py --host 0.0.0.0 --port 8765 --token "%REMOTE_TOKEN%"
endlocal