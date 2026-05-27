@echo off
title MECOM HMI System
color 0A

cd /d "%~dp0"
echo [Modbus Worker] starting...
start /b python modbus_worker.py
echo [API Server] starting...
start /b python api_server.py
timeout /t 3 /nobreak > NUL
echo.
echo Opening dashboard at http://localhost:8501
streamlit run app.py
pause
