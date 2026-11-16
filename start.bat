@echo off
chcp 65001 >nul
title PrintFarm 3D — Система управления студией 3D-печати
color 0B

echo.
echo ====================================================================
echo    🖨️  PrintFarm 3D — Система управления студией 3D-печати
echo ====================================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: 1. Проверка и запуск службы PostgreSQL
echo [1/3] Проверка базы данных PostgreSQL...
sc query postgresql-x64-17 | find "RUNNING" >nul 2>&1
if %errorlevel% neq 0 (
    echo     Запуск службы PostgreSQL (postgresql-x64-17)...
    net start postgresql-x64-17 >nul 2>&1
    timeout /t 2 /nobreak >nul
)

:: Поиск Python окружения
set "PYTHON_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

:: Проверка доступности БД через Python
"%PYTHON_EXE%" -c "import sys; sys.path.insert(0, r'%SCRIPT_DIR%'); from db import get_db_connection; c = get_db_connection(); c.close(); print('    [OK] База данных PostgreSQL подключена успешно')" 2>nul
if %errorlevel% neq 0 (
    echo     [!] База данных еще не инициализирована. Инициализируем...
    "%PYTHON_EXE%" "%SCRIPT_DIR%db.py"
) else (
    echo     [OK] Подключение к PostgreSQL стабильно.
)

echo.
echo [2/3] Подготовка веб-сервера...
echo     Адрес: http://localhost:5003
echo     Логин администратора: admin  /  пароль: 12345
echo.

:: 2. Фоновый запуск открытия браузера через 2 секунды (когда Flask поднимется)
echo [3/3] Запуск браузера и сервера...
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:5003"

echo.
echo ====================================================================
echo    Сервер успешно запущен! Окно браузера откроется автоматически.
echo    Для остановки сервера закройте это окно или нажмите Ctrl + C.
echo ====================================================================
echo.

"%PYTHON_EXE%" "%SCRIPT_DIR%app.py"

if %errorlevel% neq 0 (
    echo.
    echo [!] Произошла ошибка при выполнении. Нажмите любую клавишу для выхода...
    pause >nul
)
