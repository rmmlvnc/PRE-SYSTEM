@echo off
setlocal

rem Start the Django API so Expo Go on a phone can reach it on port 8000.
rem This script is located in the Django project folder.

set "PROJECT_DIR=%~dp0"
set "PYTHON=%PROJECT_DIR%django-env\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=%PROJECT_DIR%..\django-env\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=%USERPROFILE%\django-env\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo Django virtual-environment Python was not found:
  echo %PYTHON%
  echo Checked these locations:
  echo %PROJECT_DIR%django-env\Scripts\python.exe
  echo %PROJECT_DIR%..\django-env\Scripts\python.exe
  echo %USERPROFILE%\django-env\Scripts\python.exe
  pause
  exit /b 1
)

echo.
echo Starting the DengueWatch API for Expo Go...
echo Keep this window open while using the mobile app.
echo 0.0.0.0 is the listening address only; do not open it in a browser.
echo.
"%PYTHON%" manage.py runserver 0.0.0.0:8000
