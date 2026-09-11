@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
REM JARVIS HUD Launcher - Electron first (WebContentsView), Chrome fallback
REM Fish Audio voice gateway (single instance, background warmup) - localhost-only 127.0.0.1:8766
echo [JARVIS] Starting voice gateway...
if exist ".venv\Scripts\python.exe" (
    start "" /min ".venv\Scripts\python.exe" start_voice.py
) else (
    start "" /min python start_voice.py 2>nul
    if errorlevel 1 start "" /min python3 start_voice.py 2>nul
)
timeout /t 2 /nobreak >nul 2>&1
if not exist "node_modules\.bin\electron.cmd" (
    if not exist "node_modules\electron\dist\electron.exe" (
        echo [JARVIS] Electron not found at node_modules\.bin\electron.cmd
        echo [JARVIS] Run: npm install   (or npm install electron@31.7.0)
        echo [JARVIS] Falling back to Chrome via jarvis.py ...
        goto :fallback_chrome
    )
)

echo [JARVIS] Launching Electron HUD (WebContentsView - Spidey Tracker embedded)...
echo [JARVIS] Site https://spideytracker.net/intl/in/ will load INSIDE the holographic popup
REM Use npm start if available (handles PATH correctly), else direct electron binary
where npm >nul 2>&1
if %errorlevel%==0 (
    call npm start
    set EXITCODE=%errorlevel%
) else (
    if exist "node_modules\.bin\electron.cmd" (
        call "node_modules\.bin\electron.cmd" . 
        set EXITCODE=%errorlevel%
    ) else (
        "node_modules\electron\dist\electron.exe" .
        set EXITCODE=%errorlevel%
    )
)

if %EXITCODE% neq 0 (
    echo.
    echo [JARVIS] Electron exited with code %EXITCODE%
    echo [JARVIS] Check logs above. Falling back to Chrome...
    timeout /t 2 /nobreak >nul
    goto :fallback_chrome
)
goto :end

:fallback_chrome
echo [JARVIS] Launching Chrome fallback (browser mode - Spidey will show LINK BLOCKED, Electron required for embed)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" jarvis.py
) else (
    python jarvis.py 2>nul
    if errorlevel 1 python3 jarvis.py
)
set EXITCODE=%errorlevel%

:end
if %EXITCODE% neq 0 (
    echo.
    echo J.A.R.V.I.S. exited with error %EXITCODE% - check jarvis_crash.log
    pause
)
endlocal
