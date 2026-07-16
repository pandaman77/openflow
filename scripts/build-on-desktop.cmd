@echo off
rem OpenFlow build script for the desktop build machine.
rem Run from the repo root: scripts\build-on-desktop.cmd [check|build]

setlocal
set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
set "MODE=%~1"
if "%MODE%"=="" set "MODE=check"

cd /d "%~dp0\..\apps\desktop"

if not exist node_modules (
    echo === npm install ===
    call npm install --no-audit --no-fund || exit /b 1
)

echo === frontend build ===
call npm run build || exit /b 1

cd src-tauri

if "%MODE%"=="check" (
    echo === cargo check ===
    cargo check 2>&1
    exit /b %ERRORLEVEL%
)

echo === tauri build ===
cd ..
call npx tauri build || exit /b 1
echo BUILD_DONE
