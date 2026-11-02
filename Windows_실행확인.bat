@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 goto directory_error
if not exist "dist\SunriseImage\SunriseImage.exe" goto no_exe
if not exist "Windows_결과" mkdir "Windows_결과"
if errorlevel 1 goto directory_error
start /wait "" "dist\SunriseImage\SunriseImage.exe" --smoke-test --report "%~dp0Windows_결과\WINDOWS_RUNTIME_CHECK.json"
if errorlevel 1 goto failed
echo [PASS] Runtime smoke test. Check Windows_결과\WINDOWS_RUNTIME_CHECK.json.
start "" "dist\SunriseImage\SunriseImage.exe"
endlocal & exit /b 0
:no_exe
echo [FAILED] Missing EXE; use EXE_빌드.bat first.
pause
endlocal & exit /b 1
:directory_error
echo [FAILED] Cannot access runtime folder.
pause
endlocal & exit /b 1
:failed
echo [FAILED] Windows runtime smoke test failed.
pause
endlocal & exit /b 1
