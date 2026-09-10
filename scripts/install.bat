@echo off
setlocal
set "INSTALL_DIR=%ProgramFiles%\SimpleRemote"
if not "%~1"=="" set "INSTALL_DIR=%~1"

powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0install.ps1" -InstallDir "%INSTALL_DIR%"
endlocal