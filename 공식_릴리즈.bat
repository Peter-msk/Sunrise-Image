@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 goto directory_error
echo [INFO] Running official RELEASE_MIN pipeline (signature required).
call "%~dp0EXE_빌드.bat"
set "run_status=%errorlevel%"
endlocal & exit /b %run_status%
:directory_error
echo [FAILED] Cannot access the build script directory.
pause
endlocal & exit /b 1
