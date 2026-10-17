@echo off
chcp 65001 >nul
title Rain Check — Servidor e Agendador 21h
echo ========================================================
echo   RAIN CHECK — Previsao de Chuva e Alerta Diario as 21h
echo ========================================================
echo.
echo Iniciando servidor em http://localhost:5000 ...
echo.
.\.venv\Scripts\python.exe app.py
pause
