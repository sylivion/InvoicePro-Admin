@echo off
title InvoicePro Admin Server
cd /d "%~dp0"
echo.
echo  Starting InvoicePro Admin Server...
echo  This window must stay open.
echo.
python admin_server.py
pause
