@echo off
chcp 65001 >nul
title 股票量化交易系统
echo ========================================================
echo   股票量化交易系统 - 一键运行
echo ========================================================
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 检查依赖是否安装
echo [1/3] 检查依赖包...
python -c "import pandas, numpy, matplotlib, requests" 2>nul
if errorlevel 1 (
    echo [提示] 正在安装依赖包...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请手动运行: pip install -r requirements.txt
        pause
        exit /b 1
    )
)
echo       依赖检查通过!

echo.
echo [2/3] 启动量化交易系统...
echo.

REM 运行主程序
python main.py

echo.
echo [3/3] 运行完成!
echo.
pause
