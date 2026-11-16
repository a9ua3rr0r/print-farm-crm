@echo off
chcp 65001 >nul
title PrintFarm 3D - Система управления студией 3D-печати
color 0B

echo.
echo ====================================================================
echo    PrintFarm 3D - Система управления студией 3D-печати
echo ====================================================================
echo.

cd /d "%~dp0"

echo [1/3] Проверка службы PostgreSQL...
sc query postgresql-x64-17 | find "RUNNING" >nul 2>&1
if errorlevel 1 (
    echo     Запуск службы PostgreSQL...
    net start postgresql-x64-17 >nul 2>&1
    timeout /t 2 /nobreak >nul
)

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

"%PYTHON_EXE%" -c "from db import get_db_connection; c = get_db_connection(); c.close(); print('[OK] База данных подключена успешно')" 2>nul
if errorlevel 1 (
    echo     [!] Инициализация базы данных...
    "%PYTHON_EXE%" db.py
) else (
    echo     [OK] База данных PostgreSQL готова к работе.
)

echo.
echo [2/3] Подготовка веб-сервера...
echo     Адрес системы: http://localhost:5003
echo     Логин: admin  /  Пароль: 12345
echo.

echo [3/3] Открытие браузера и запуск сервера...
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:5003"

echo.
echo ====================================================================
echo    Сервер запущен! Окно браузера откроется автоматически.
echo    Для остановки сервера просто закройте это окно [или Ctrl+C].
echo ====================================================================
echo.

"%PYTHON_EXE%" app.py

if errorlevel 1 (
    echo.
    echo [!] Сервер был остановлен. Нажмите любую клавишу для выхода...
    pause >nul
)
