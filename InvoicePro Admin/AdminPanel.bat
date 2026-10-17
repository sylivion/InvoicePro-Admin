@echo off
title InvoicePro Admin Server
cd /d "%~dp0"
echo.
echo  ======================================================
echo    InvoicePro Admin Server
echo    Starting up, please wait...
echo  ======================================================
echo.
python -u admin_server.py
pause
