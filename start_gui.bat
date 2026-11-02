@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM 1. 优先极速启动已编译的高性能独立程序 (毫秒级秒开，无黑框)
if exist "dist\FFmpegStudio\FFmpegStudio.exe" (
    start "" "dist\FFmpegStudio\FFmpegStudio.exe"
    exit /b 0
)

REM 2. 回退模式：使用 pythonw 启动无控制台窗口模式
start "" pythonw gui_main.py
if errorlevel 1 (
    echo [错误] pythonw 启动异常，尝试以控制台模式输出错误日志...
    python gui_main.py
    pause
)
