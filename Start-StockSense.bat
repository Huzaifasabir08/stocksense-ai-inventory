@echo off
cd /d "%~dp0"
call "%~dp0AI Inventory for a shoping mall\Start-StockSense.bat"
exit /b %errorlevel%
