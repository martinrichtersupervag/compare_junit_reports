@echo off
setlocal

if "%~1"=="" (
    python "%~dp0compare_junit_reports.py" --explain-parallel --html
) else (
    python "%~dp0compare_junit_reports.py" --explain-parallel --html --directory "%~1"
)

exit /b %ERRORLEVEL%