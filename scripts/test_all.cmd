@echo off
setlocal
set "ROOT=%~dp0.."
set "PYTHONPATH=%ROOT%\src"
"%ROOT%\.paperflow\.venv\Scripts\python.exe" -m pytest %*
exit /b %ERRORLEVEL%
