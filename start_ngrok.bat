@echo off
title InvoicePro Ngrok Tunnel
cd /d "%~dp0"

echo.
echo  ================================================
echo   InvoicePro Admin - Ngrok HTTPS Tunnel (Port 8766)
echo  ================================================
echo.
echo  Starting Ngrok Tunnel for domain: huddle-revival-outflank.ngrok-free.dev
echo.

ngrok.exe http --domain=huddle-revival-outflank.ngrok-free.dev 8766
if errorlevel 1 (
    echo.
    echo  Domain flag failed or not reserved. Starting default public tunnel on port 8766...
    echo.
    ngrok.exe http 8766
)

pause
