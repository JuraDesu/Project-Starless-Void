@echo off
setlocal

set "PYTHON_CMD=%PYTHON%"
if not defined PYTHON_CMD set "PYTHON_CMD=python"
"%PYTHON_CMD%" "%~dp0engine\sdk\tools\setup_emsdk.py" %*
exit /b %ERRORLEVEL%
