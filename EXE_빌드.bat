@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Prefer the project's documented Python 3.12 when available. No venv created.
where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 -c "import sys; assert sys.maxsize > 2**32" >nul 2>nul
    if not errorlevel 1 (
        py -3.12 -u build_windows.py --profile RELEASE_MIN
        goto check_result
    )
)
where python >nul 2>nul
if not errorlevel 1 (
    python -u build_windows.py --profile RELEASE_MIN
    goto check_result
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -u build_windows.py --profile RELEASE_MIN
    goto check_result
)
echo [오류] 시스템에서 Python을 찾을 수 없습니다. 64비트 Python(PATH 추가)을 설치하세요.
pause
exit /b 1

:check_result
if errorlevel 1 goto failed
echo.
echo [완료] Sunrise Group 서명 적용 빌드가 완료되었습니다!
echo - 실행 파일: dist\SunriseImage\SunriseImage.exe
echo - 배포 압축본: release\Sunrise_Image.zip
pause
exit /b 0

:failed
echo.
echo [실패] 빌드 또는 실행 확인 실패.
echo - 실제 PyInstaller 오류가 위에 표시됩니다.
echo - 상세 로그: Windows_결과\02_pyinstaller.log
echo - 결과 요약: Windows_결과\WINDOWS_BUILD_RESULT.json
pause
exit /b 1
