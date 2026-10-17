@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if not errorlevel 1 (
    python -u build_windows.py
    goto check_result
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -u build_windows.py
    goto check_result
)
echo [오류] 시스템에서 Python을 찾을 수 없습니다. 64비트 Python(PATH 추가)을 설치하세요.
pause
exit /b 1

:check_result
if errorlevel 1 goto failed
echo.
echo [완료] 가상환경 없이 Windows EXE 직접 빌드가 완료되었습니다!
echo - 실행 파일: dist\SunriseImage\SunriseImage.exe
echo - 배포 압축본: release\Sunrise_Image_WINDOWS_x64.zip
pause
exit /b 0

:failed
echo.
echo [실패] 빌드 또는 실행 확인 실패. Windows_결과 폴더의 로그를 확인하세요.
pause
exit /b 1
