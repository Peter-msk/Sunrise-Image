@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist "dist\SunriseImage\SunriseImage.exe" goto missing
if not exist "Windows_결과" mkdir "Windows_결과"
start /wait "" "dist\SunriseImage\SunriseImage.exe" --smoke-test --report "%~dp0Windows_결과\WINDOWS_RUNTIME_CHECK.json"
if errorlevel 1 goto failed
echo 실행 확인 완료. Windows_결과 폴더에 JSON과 화면 캡처가 저장되었습니다.
start "" "dist\SunriseImage\SunriseImage.exe"
exit /b 0
:missing
echo EXE_빌드.bat으로 빌드한 뒤 실행하세요.
pause
exit /b 1
:failed
echo 실행 확인 실패. Windows_결과 폴더의 JSON을 확인하세요.
pause
exit /b 1
