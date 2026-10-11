@echo off
rem Double-click to choose a backup from your data folder, or drop a backup .zip onto this file.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Restore-Studio.ps1" -Backup "%~1"
pause
