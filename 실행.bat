@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 goto directory_error
if exist "dist\SunriseImage\SunriseImage.exe" goto run_exe
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3.12 -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)" >nul 2>nul
if errorlevel 1 goto try_python
py -3.12 app_entry.py
goto check_result
:try_python
where python >nul 2>nul
if errorlevel 1 goto no_python
python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)" >nul 2>nul
if errorlevel 1 goto no_python
python app_entry.py
goto check_result
:run_exe
start "" "dist\SunriseImage\SunriseImage.exe"
endlocal & exit /b 0
:check_result
set "run_status=%errorlevel%"
if not "%run_status%"=="0" pause
endlocal & exit /b %run_status%
:no_python
echo [FAILED] No built EXE and Python 3.12 x64 unavailable.
pause
endlocal & exit /b 1
:directory_error
echo [FAILED] Cannot access the application directory.
pause
endlocal & exit /b 1
