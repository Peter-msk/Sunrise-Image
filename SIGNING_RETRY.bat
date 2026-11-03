@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 goto failed

rem Resume only the PREVIOUS successful EXE when the failure was signing.
rem No PyInstaller, pip, venv, certificate reuse or global Python changes.
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3.12 -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)" >nul 2>nul
if errorlevel 1 goto try_python
py -3.12 -u build_windows.py --profile RELEASE_MIN --resume-signing
goto done

:try_python
where python >nul 2>nul
if errorlevel 1 goto no_python
python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)" >nul 2>nul
if errorlevel 1 goto no_python
python -u build_windows.py --profile RELEASE_MIN --resume-signing
goto done

:no_python
echo [FAILED] Python 3.12 x64 required; no Python install or global change performed.
pause
endlocal & exit /b 1

:done
if errorlevel 1 goto failed
echo [PASS] Existing staged Windows EXE signed and ZIP packaged without recompiling.
echo [ZIP] release\Sunrise_Image.zip
pause
endlocal & exit /b 0

:failed
echo [FAILED] Check Windows_결과\WINDOWS_BUILD_RESULT.json and 04_signing.log.
echo Previous builds and existing certificates were not removed.
pause
endlocal & exit /b 1
