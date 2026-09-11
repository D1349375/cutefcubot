@echo off
chcp 65001 > nul
title Cloudflare Tunnel 免費外網通道產生器

echo ======================================================
echo   正在為您的桌機建立免費 HTTPS 通道 (Port 8000)...
echo ======================================================
echo.
echo 稍候終端機中會出現一串以 https:// 開頭、.trycloudflare.com 結尾的網址。
echo 例如：https://xxxxx.trycloudflare.com
echo.
echo 請把該網址加上 /callback 填入 LINE 後台的 Webhook 網址欄位！
echo (例如：https://xxxxx.trycloudflare.com/callback)
echo ======================================================
echo.

"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8000
pause
