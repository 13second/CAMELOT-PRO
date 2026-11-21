@echo off
chcp 65001 >nul
title CAMELOT PRO - One-Click Installer (Windows)
cls
echo ======================================================================
echo  🗡️  CAMELOT PRO — AUTOMATIC INSTALLER (Windows)
echo      Real-Time Audio Telemetry, Vectorscope ^& AI Session Analyzer
echo ======================================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo [1/3] Checking Python 3 installation...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python 3 was not found on your system.
    echo Please install Python 3 from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation!
    pause
    exit /b 1
)

for /f "delims=" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
echo    OK: Found %PY_VER%
echo.

echo [2/3] Installing DSP Python libraries (numpy, scipy, soundfile, pyloudnorm)...
python -m pip install --upgrade pip --quiet
python -m pip install -r "%SCRIPT_DIR%requirements.txt"
echo.

echo [3/3] Preparing Ableton Live User Library folder...
if not exist "%SCRIPT_DIR%MIX ANALYSIS" mkdir "%SCRIPT_DIR%MIX ANALYSIS"

set "ABLETON_USER_LIB=%USERPROFILE%\Documents\Ableton\User Library\Presets\Audio Effects\Max Audio Effect\CAMELOT PRO"
if exist "%USERPROFILE%\Documents\Ableton\User Library" (
    if not exist "%ABLETON_USER_LIB%" mkdir "%ABLETON_USER_LIB%"
    if not exist "%ABLETON_USER_LIB%\MIX ANALYSIS" mkdir "%ABLETON_USER_LIB%\MIX ANALYSIS"
    copy /Y "%SCRIPT_DIR%Camelot_Pro.amxd" "%ABLETON_USER_LIB%\" >nul
    copy /Y "%SCRIPT_DIR%camelot.py" "%ABLETON_USER_LIB%\" >nul
    copy /Y "%SCRIPT_DIR%camelot_live_lite.js" "%ABLETON_USER_LIB%\" >nul
    copy /Y "%SCRIPT_DIR%camelot_pro_m4l.js" "%ABLETON_USER_LIB%\" >nul
    copy /Y "%SCRIPT_DIR%camelot_pro_runner.js" "%ABLETON_USER_LIB%\" >nul
    copy /Y "%SCRIPT_DIR%vectorscope.js" "%ABLETON_USER_LIB%\" >nul
    copy /Y "%SCRIPT_DIR%requirements.txt" "%ABLETON_USER_LIB%\" >nul
    copy /Y "%SCRIPT_DIR%README.txt" "%ABLETON_USER_LIB%\" >nul
    echo    OK: Installed into %ABLETON_USER_LIB%
) else (
    echo    INFO: Copy the entire "CAMELOT PRO" folder into your Ableton User Library:
    echo          User Library\Presets\Audio Effects\Max Audio Effect\CAMELOT PRO
)

echo.
echo ======================================================================
echo  🎉 INSTALLATION COMPLETED SUCCESSFULLY!
echo  Drag 'Camelot_Pro.amxd' onto your Master Track in Ableton Live.
echo ======================================================================
pause

