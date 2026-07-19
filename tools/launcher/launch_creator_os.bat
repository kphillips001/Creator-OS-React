@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_creator_os.ps1"
exit /b %errorlevel%
