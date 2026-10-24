@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist "dist\SunriseImage\SunriseImage.exe" (
    start "" "dist\SunriseImage\SunriseImage.exe"
    exit /b 0
)
where python >nul 2>nul
if not errorlevel 1 goto run_python
where py >nul 2>nul
if not errorlevel 1 goto run_py
echo [오류] 실행할 Python 또는 빌드된 SunriseImage.exe가 없습니다. EXE_빌드.bat을 실행하세요.
pause
exit /b 1

:run_python
python app_entry.py
goto check_python
:run_py
py -3 app_entry.py
:check_python
set "run_status=%errorlevel%"
if not "%run_status%"=="0" pause
exit /b %run_status%
