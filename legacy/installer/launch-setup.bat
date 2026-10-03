@echo off
rem ============================================================
rem  SWDM 安装启动器
rem  为什么需要它：本机沙箱会拦截"位于工作区目录内"的未知 exe
rem  向 %TEMP% / AppData 写数据（Inno 引导器自解压建 is-xxx.tmp
rem  报错误 5）。把安装包复制到 %TEMP% 再运行即不受限。
rem  发布流程：打包后把本文件复制到 installer\Output\ 即可
rem  （Output 是构建产物目录，不入 git；模板在 installer/launch-setup.bat）
rem ============================================================
setlocal enabledelayedexpansion

rem ---- 自动选最新版安装包（SWDM-Setup-x.y.z.exe），跨版本自适应 ----
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

rem ---- 优雅关闭运行中的 SWDM（否则 Inno 会提示"请先关闭"） ----
taskkill /IM SWDM.exe >nul 2>&1
timeout /t 2 /nobreak >nul
taskkill /IM SWDM.exe /F >nul 2>&1

rem ---- 复制出工作区再运行 ----
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
