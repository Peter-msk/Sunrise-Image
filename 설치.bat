@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo 가상환경(.venv) 생성 없이 바로 EXE_빌드.bat으로 직접 빌드를 시작합니다...
call "%~dp0EXE_빌드.bat"
exit /b %errorlevel%
