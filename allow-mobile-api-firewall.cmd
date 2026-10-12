@echo off
setlocal

rem Run this file once as Administrator if Expo Go cannot reach Django while
rem the phone and laptop are on the same Wi-Fi or personal hotspot.

net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo This file must be run as Administrator.
  echo Right-click allow-mobile-api-firewall.cmd, then choose Run as administrator.
  pause
  exit /b 1
)

netsh advfirewall firewall add rule name=DengueWatchDjangoAPI8000 dir=in action=allow protocol=TCP localport=8000 profile=private,public
if errorlevel 1 (
  echo Windows could not add the firewall rule.
  pause
  exit /b 1
)

echo.
echo Firewall access for the DengueWatch Django API was added successfully.
echo You can now run start-mobile-api.cmd and open the app with Expo Go.
pause
