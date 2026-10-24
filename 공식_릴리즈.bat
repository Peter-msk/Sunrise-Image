@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
py -3.12 -u build_windows.py --profile RELEASE_MIN
if errorlevel 1 goto failed
echo Signed package complete. Review Windows_결과\WINDOWS_BUILD_RESULT.json
pause
exit /b 0
:failed
echo Release failed. Review Windows_결과\WINDOWS_BUILD_RESULT.json
pause
exit /b 1
