@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
echo ================================================================
echo  Sunrise Image - GitHub public source upload
echo  Target: https://github.com/Peter-msk/Sunrise-Image
echo  WARNING: uploaded files will be publicly visible.
echo ================================================================
where git >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Git for Windows is not installed or not in PATH.
  echo Install Git for Windows and rerun this script.
  pause
  exit /b 1
)
if not exist ".git" (
  git init -b main
  if errorlevel 1 goto :failed
)
for /f "delims=" %%R in ('git remote get-url origin 2^>nul') do set "REMOTE=%%R"
if not defined REMOTE (
  git remote add origin "https://github.com/Peter-msk/Sunrise-Image.git"
  if errorlevel 1 goto :failed
) else (
  echo %REMOTE% | findstr /I /C:"github.com/Peter-msk/Sunrise-Image" >nul
  if errorlevel 1 (
    echo [ERROR] The existing origin points to another repository: %REMOTE%
    pause
    exit /b 1
  )
)
for /f "delims=" %%N in ('git config user.name') do set "AUTHOR_NAME=%%N"
for /f "delims=" %%E in ('git config user.email') do set "AUTHOR_EMAIL=%%E"
if not defined AUTHOR_NAME (
  echo [ERROR] Configure your Git author name: git config --global user.name "YOUR_NAME"
  pause
  exit /b 1
)
if not defined AUTHOR_EMAIL (
  echo [ERROR] Configure your Git author email: git config --global user.email "YOUR_EMAIL"
  pause
  exit /b 1
)
git add -A
if errorlevel 1 goto :failed
echo.
echo [FILES TO BE PUBLISHED]
git status --short
echo.
choice /C YN /M "Publish all listed files to the PUBLIC Sunrise-Image repository"
if errorlevel 2 (
  echo Cancelled. Nothing was pushed.
  exit /b 0
)
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Publish Sunrise Image source and documentation"
  if errorlevel 1 goto :failed
)
git branch -M main
if errorlevel 1 goto :failed
git pull --rebase origin main
if errorlevel 1 goto :failed
git push -u origin main
if errorlevel 1 goto :failed
echo.
echo [SUCCESS] Published to https://github.com/Peter-msk/Sunrise-Image
pause
exit /b 0
:failed
echo.
echo [ERROR] Git could not finish the operation. Review the error above.
pause
exit /b 1
