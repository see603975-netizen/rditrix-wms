@echo off
chcp 65001 >nul
title Update Rditrix WMS
cd /d "%~dp0"
git pull
echo.
echo ================= 更新完成 =================
pause
