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

echo [1/4] Поиск и запуск службы PostgreSQL...
sc query postgresql-x64-17 | find "RUNNING" >nul 2>&1
if errorlevel 1 net start postgresql-x64-17 >nul 2>&1

sc query postgresql-x64-16 | find "RUNNING" >nul 2>&1
if errorlevel 1 net start postgresql-x64-16 >nul 2>&1

sc query postgresql-x64-15 | find "RUNNING" >nul 2>&1
if errorlevel 1 net start postgresql-x64-15 >nul 2>&1

sc query postgresql | find "RUNNING" >nul 2>&1
if errorlevel 1 net start postgresql >nul 2>&1

set "PYTHON_EXE=.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo [2/4] Проверка библиотек Python...
"%PYTHON_EXE%" -c "import flask, psycopg2, openpyxl" >nul 2>&1
if errorlevel 1 (
    echo     [i] Установка недостающих библиотек из requirements.txt...
    "%PYTHON_EXE%" -m pip install -r requirements.txt
) else (
    echo     [OK] Все библиотеки установлены.
)

echo [3/4] Проверка подключения к базе данных...
"%PYTHON_EXE%" -c "from db import get_db_connection; c = get_db_connection(); c.close(); print('    [OK] База данных подключена успешно')" 2>nul
if errorlevel 1 (
    echo     [!] Инициализация таблиц и демо-данных...
    "%PYTHON_EXE%" db.py
) else (
    echo     [OK] База данных PostgreSQL готова к работе.
)

echo.
echo [4/4] Запуск веб-сервера...
echo     Адрес системы: http://localhost:5003
echo     Логин: admin  /  Пароль: 12345
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:5003"

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
