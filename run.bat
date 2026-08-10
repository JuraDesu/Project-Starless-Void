@echo off
setlocal

if not defined ENGINE_DIST if exist "%~dp0engine\sdk\engine-content-config.cmake" set "ENGINE_DIST=%~dp0engine"
if not defined ENGINE_DIST set "ENGINE_DIST=%~dp0..\out\engine"
if not defined GAME_OUTPUT_DIR set "GAME_OUTPUT_DIR=%~dp0out"
if not exist "%GAME_OUTPUT_DIR%\index.html" (
    echo Game deployment not found. Run build.bat first.
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_server.ps1" ^
    -ProjectRoot "%~dp0." ^
    -EngineDist "%ENGINE_DIST%" ^
    -GameOutputDir "%GAME_OUTPUT_DIR%" ^
    -Port 1111
exit /b %ERRORLEVEL%
