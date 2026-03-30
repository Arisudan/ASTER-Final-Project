@echo off
setlocal enabledelayedexpansion

adb disconnect >nul 2>&1
adb tcpip 5555 >nul 2>&1
timeout /t 3 /nobreak >nul

set "DEVICE_IP="
for /f "tokens=2 delims= " %%A in ('adb shell ip addr show wlan0 2^>nul ^| findstr /R /C:"inet "') do (
    set "RAW_IP=%%A"
    for /f "tokens=1 delims=/" %%B in ("!RAW_IP!") do set "DEVICE_IP=%%B"
)

if defined DEVICE_IP (
    echo Connecting to !DEVICE_IP!:5555
    adb connect !DEVICE_IP!:5555 >nul 2>&1
) else (
    echo Auto-detection failed, using static fallback.
    set "DEVICE_IP=192.0.0.4"
    set "ADB_PORT=5555"
    adb kill-server >nul 2>&1
    adb start-server >nul 2>&1
    adb connect !DEVICE_IP!:!ADB_PORT! >nul 2>&1
)

endlocal
