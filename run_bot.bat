@echo off
chcp 65001 > nul
title 逢甲選課退選即時提醒 LINE 機器人

echo ======================================================
echo   逢甲選課退選即時提醒 LINE 機器人啟動程序
echo ======================================================
echo.

if not exist ".env" (
    echo [警告] 找不到 .env 檔案，正在從 .env.example 建立...
    copy .env.example .env
    echo 請先在 .env 檔案中填入您的 LINE_CHANNEL_SECRET 與 LINE_CHANNEL_ACCESS_TOKEN！
    pause
    exit /b
)

echo 正在啟動 FastAPI Webhook 伺服器...
python bot.py

pause
