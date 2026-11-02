@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 goto directory_error
if not exist "dist\SunriseImage\SunriseImage.exe" goto no_exe
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3.12 -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)" >nul 2>nul
if errorlevel 1 goto try_python
py -3.12 -u build_windows.py --package-only --profile RELEASE_MIN
goto check_result
:try_python
where python >nul 2>nul
if errorlevel 1 goto no_python
python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)" >nul 2>nul
if errorlevel 1 goto no_python
python -u build_windows.py --package-only --profile RELEASE_MIN
goto check_result
:check_result
if errorlevel 1 goto failed
echo [PASS] Signed Sunrise Image package: release\Sunrise_Image.zip
pause
endlocal & exit /b 0
:no_exe
echo [FAILED] Build dist\SunriseImage\SunriseImage.exe before packaging.
pause
endlocal & exit /b 1
:no_python
echo [FAILED] Python 3.12 x64 is required for packaging.
pause
endlocal & exit /b 1
:directory_error
echo [FAILED] Cannot access the build script directory.
pause
endlocal & exit /b 1
:failed
echo [FAILED] Packaging failed. Check Windows_결과\WINDOWS_BUILD_RESULT.json.
pause
endlocal & exit /b 1
