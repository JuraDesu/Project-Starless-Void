@echo off
setlocal

set "PYTHON_CMD=%PYTHON%"
if not defined PYTHON_CMD set "PYTHON_CMD=python"
"%PYTHON_CMD%" "%~dp0engine\sdk\tools\run_content_project.py" --project "%~dp0."
exit /b %ERRORLEVEL%
