@echo off
cd /D "%~dp0"
set "python_script=%~1"
if exist runtime\Scripts\pip.exe goto :run

:setup
echo "setup pip"
call runtime\python.exe runtime\get-pip.py --no-warn-script-location
goto :run

:run
echo Running %python_script%
:: Double-click to execute main.py by default, or drag and drop a .py script to execute it
if "%python_script%" == "" (
    call runtime\python.exe main.py
) else (
    call runtime\python.exe "%python_script%"
)

::pause
exit /b