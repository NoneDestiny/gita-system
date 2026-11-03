@echo off
chcp 65001 > nul
echo ===================================================
echo           Iniciando Servidor GITA System
echo ===================================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] No se encontro el entorno virtual en venv.
    pause
    exit /b 1
)

echo Aplicando migraciones de la base de datos...
"venv\Scripts\python.exe" manage.py migrate
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [AVISO] Fallo la conexion a la base de datos o la aplicacion de migraciones.
    echo Verifica tu archivo .env
    echo.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo Servidor en ejecucion:
echo   - Login Principal:    http://127.0.0.1:8000/login/
echo   - Panel Administrador: http://127.0.0.1:8000/admin/
echo.
echo Credenciales de administrador creadas:
echo   Usuario / Cedula: 30346898  (o admin)
echo   Clave:            admin123
echo ===================================================
echo.

start http://127.0.0.1:8000/login/
"venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000

pause
