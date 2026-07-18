@echo off
setlocal
set "ROOT=%~dp0"
if exist "%ROOT%.paperflow\src\paperflow\__init__.py" (
  set "PYTHONPATH=%ROOT%.paperflow\src;%PYTHONPATH%"
) else (
  set "PYTHONPATH=%ROOT%src;%PYTHONPATH%"
)
if exist "%ROOT%.paperflow\.venv\Scripts\python.exe" (
  "%ROOT%.paperflow\.venv\Scripts\python.exe" -m paperflow.cli %*
) else (
  py -3 -m paperflow.cli %*
)
exit /b %ERRORLEVEL%
