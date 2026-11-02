@echo off
chcp 65001 >nul
cd /d "%~dp0"
title FFmpeg Multi-Tool Studio
python gui_main.py
if errorlevel 1 (
    echo.
    echo 程序异常退出，请查看上方错误信息。
    pause
)
