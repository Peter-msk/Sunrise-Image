@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist "dist\SunriseImage\SunriseImage.exe" goto noexe
where python >nul 2>nul
if not errorlevel 1 (
    python -u build_windows.py --package-only --profile RELEASE_MIN
    goto check_result
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -u build_windows.py --package-only --profile RELEASE_MIN
    goto check_result
)
echo [오류] 시스템에서 Python을 찾을 수 없습니다.
pause
exit /b 1

:check_result
if errorlevel 1 goto failed
echo 그룹서명 적용 패키지 완료. release\Sunrise_Image.zip을 확인하세요.
pause
exit /b 0

:noexe
echo 기존 dist\SunriseImage\SunriseImage.exe가 필요합니다. EXE_빌드.bat을 먼저 실행하세요.
pause
exit /b 1

:failed
echo 배포 마무리 실패. Windows_결과\WINDOWS_BUILD_RESULT.json과 관련 로그를 확인하세요.
pause
exit /b 1
