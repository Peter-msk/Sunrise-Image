@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 goto directory_error

rem Windows 10/11 x64, Python 3.12 x64; no venv or global pip changes.
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3.12 -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)" >nul 2>nul
if errorlevel 1 goto try_python
py -3.12 -u build_windows.py --profile RELEASE_MIN
goto check_result

:try_python
where python >nul 2>nul
if errorlevel 1 goto no_python
python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)" >nul 2>nul
if errorlevel 1 goto no_python
python -u build_windows.py --profile RELEASE_MIN
goto check_result

:check_result
if errorlevel 1 goto failed
echo.
echo [PASS] Sunrise Group signed build pipeline completed.
echo [EXE] dist\SunriseImage\SunriseImage.exe
echo [ZIP] release\Sunrise_Image.zip
pause
endlocal & exit /b 0

:no_python
echo.
echo [FAILED] Python 3.12 x64 is required. Install it and enable the py launcher or PATH.
pause
endlocal & exit /b 1

:directory_error
echo [FAILED] Cannot access the build script directory.
pause
endlocal & exit /b 1

:failed
echo.
echo [FAILED] Sunrise Image build pipeline failed.
echo [RESULT] Windows_결과\WINDOWS_BUILD_RESULT.json
echo [DEPS] Windows_결과\01_dependencies.log
echo [BUILD] Windows_결과\02_pyinstaller.log
echo [RUNTIME] Windows_결과\03_runtime.log
echo [SIGN] Windows_결과\04_signing.log
pause
endlocal & exit /b 1
