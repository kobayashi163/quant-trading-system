@echo off
chcp 65001 >nul
title 初始化 Git 仓库并推送到 GitHub
echo ========================================================
echo   Git 仓库初始化工具
echo ========================================================
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 检查 git 是否安装
git --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Git，请先安装 Git。
    echo.
    echo 下载地址: https://git-scm.com/download/win
    echo 安装时选择默认选项即可。
    echo.
    pause
    exit /b 1
)

echo [1/5] 初始化 Git 仓库...
git init
echo.

echo [2/5] 添加所有文件...
git add .
echo.

echo [3/5] 创建首次提交...
git commit -m "初始提交: 股票量化交易系统"
echo.

echo [4/5] 设置主分支...
git branch -M main
echo.

echo ========================================================
echo   Git 仓库初始化完成！
echo ========================================================
echo.
echo 接下来请在 GitHub 上创建远程仓库:
echo.
echo   1. 打开 https://github.com/new
echo   2. 仓库名称填: quant-trading-system
echo   3. 不要勾选 "添加 README"
echo   4. 点击 "Create repository"
echo.
echo 然后回到这里，复制下面的命令运行（替换你的用户名）:
echo.
echo   git remote add origin https://github.com/你的用户名/quant-trading-system.git
echo   git push -u origin main
echo.
echo ========================================================
echo.
pause
