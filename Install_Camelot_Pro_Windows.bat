@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title CAMELOT PRO - One-Click Installer (Windows)
cls
echo ======================================================================
echo  CAMELOT PRO -- AUTOMATIC INSTALLER (Windows)
echo  Real-Time Audio Telemetry, Vectorscope ^& AI Session Analyzer
echo ======================================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%" || exit /b 1

echo [1/4] Checking Python 3 installation...
set "PY_CMD="
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=python"
) else (
    py -3 --version >nul 2>&1
    if !errorlevel! equ 0 (
        set "PY_CMD=py -3"
    )
)

if "%PY_CMD%"=="" (
    echo [ERROR] Python 3 was not found on your system.
    echo Please install Python 3 from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation!
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%i in ('%PY_CMD% --version 2^>^&1') do set "PY_VER=%%i"
echo    OK: Found %PY_VER% (via %PY_CMD%)
echo.

echo [2/4] Installing DSP Python libraries (numpy, scipy, soundfile, pyloudnorm)...
%PY_CMD% -m pip install --upgrade pip --quiet >nul 2>&1
%PY_CMD% -m pip install -r "%SCRIPT_DIR%requirements.txt"
if %errorlevel% neq 0 (
    echo    Standard pip install failed, retrying with --user...
    %PY_CMD% -m pip install --user -r "%SCRIPT_DIR%requirements.txt"
)

echo.
echo [3/4] Verifying DSP Python libraries...
%PY_CMD% -c "import numpy, scipy, soundfile, pyloudnorm; assert hasattr(pyloudnorm.Meter(48000), 'loudness_range')" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Failed to verify required Python DSP libraries (numpy, scipy, soundfile, pyloudnorm ^>= 0.2.0).
    echo Please check your internet connection or run manually:
    echo    %PY_CMD% -m pip install --upgrade numpy scipy soundfile pyloudnorm
    echo.
    pause
    exit /b 1
)
echo    OK: All DSP libraries are installed and verified!
echo.

echo [4/4] Preparing Ableton Live User Library folder...
if not exist "%SCRIPT_DIR%MIX ANALYSIS" mkdir "%SCRIPT_DIR%MIX ANALYSIS"

echo "%SCRIPT_DIR%" | findstr /I /C:"Max Audio Effect" >nul
if %errorlevel% equ 0 (
    echo    OK: CAMELOT PRO is already inside your Ableton Max Audio Effect folder:
    echo        %SCRIPT_DIR%
    goto :DONE
)

set "ABLETON_USER_LIB=%USERPROFILE%\Documents\Ableton\User Library\Presets\Audio Effects\Max Audio Effect\CAMELOT PRO"
if exist "%USERPROFILE%\Documents\Ableton\User Library" (
    if not exist "%ABLETON_USER_LIB%" mkdir "%ABLETON_USER_LIB%"
    if not exist "%ABLETON_USER_LIB%\MIX ANALYSIS" mkdir "%ABLETON_USER_LIB%\MIX ANALYSIS"
    set "COPY_ERR=0"
    for %%F in (
        "Camelot_Pro.amxd"
        "camelot.py"
        "camelot_live_lite.js"
        "camelot_pro_m4l.js"
        "camelot_pro_runner.js"
        "vectorscope.js"
        "Camelot_Pro_Icon.png"
        "Camelot_Pro_Icon_128.png"
        "Camelot_Pro_Icon.ico"
        "requirements.txt"
        "README.txt"
    ) do (
        copy /Y "%SCRIPT_DIR%%%~F" "%ABLETON_USER_LIB%\" >nul
        if errorlevel 1 (
            echo    [ERROR] Failed to copy %%~F
            set "COPY_ERR=1"
        )
    )
    if "!COPY_ERR!"=="1" (
        echo [ERROR] Some files could not be copied. Close Ableton Live and retry.
        pause
        exit /b 1
    )
    if exist "%ABLETON_USER_LIB%\Camelot_Pro_Icon.ico" (
        (
            echo [.ShellClassInfo]
            echo IconResource=Camelot_Pro_Icon.ico,0
        ) > "%ABLETON_USER_LIB%\desktop.ini"
        attrib +h +s "%ABLETON_USER_LIB%\desktop.ini" >nul 2>&1
        attrib +r "%ABLETON_USER_LIB%" >nul 2>&1
    )
    echo    OK: Installed into %ABLETON_USER_LIB%
) else (
    echo    INFO: Standard User Library not found at "%USERPROFILE%\Documents\Ableton\User Library".
    echo    Copy the entire "CAMELOT PRO" folder into your Ableton User Library:
    echo          User Library\Presets\Audio Effects\Max Audio Effect\CAMELOT PRO
)

:DONE
echo.
echo ======================================================================
echo  INSTALLATION COMPLETED SUCCESSFULLY!
echo  Drag 'Camelot_Pro.amxd' onto your Master Track in Ableton Live.
echo ======================================================================
echo.
pause
exit /b 0
