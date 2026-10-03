@echo off
setlocal enabledelayedexpansion

set "LATEST="
for /f "delims=" %%F in ('dir /b /o-d "%~dp0SWDM-Setup-*.exe" 2^>nul') do (
    set "LATEST=%~dp0%%F"
    goto :found
)
echo [ERROR] no SWDM-Setup-*.exe found in %~dp0
pause
exit /b 1
:found

set "TMP_EXE=%TEMP%\SWDM-Setup-launch-tmp.exe"

taskkill /IM SWDM.exe >nul 2>&1
timeout /t 2 /nobreak >nul
taskkill /IM SWDM.exe /F >nul 2>&1

copy /Y "%LATEST%" "%TMP_EXE%" >nul 2>&1
if not exist "%TMP_EXE%" (
    echo [ERROR] copy to TEMP failed
    pause
    exit /b 1
)

echo Installing %LATEST% ...
start /wait "" "%TMP_EXE%"

del /F /Q "%TMP_EXE%" >nul 2>&1
endlocal
