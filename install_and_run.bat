@echo off
setlocal

REM Flag to track if a new installation occurred
set RESTART_REQUIRED=0

REM Check if Git is installed
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo Git not found. Attempting automatic installation via winget...
    winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements --silent
    set RESTART_REQUIRED=1
)

REM Check if Python is installed
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Attempting automatic installation via winget...
    winget install --id Python.Python.3.11 -e --source winget --accept-package-agreements --accept-source-agreements --silent
    set RESTART_REQUIRED=1
)

REM If installations were performed, the PATH variable needs to be refreshed
if %RESTART_REQUIRED%==1 (
    echo.
    echo System dependencies have been installed.
    echo The script must be restarted to load the new environment variables.
    echo Please press any key to exit, then double-click this script again.
    pause >nul
    exit /b
)

REM Define repository URL and target directory
set REPO_URL=https://github.com/ale-gaudenzi/workers_routing.git
set DIR_NAME=workers_routing

REM Clone the repository if it does not exist locally
if not exist %DIR_NAME% (
    echo Cloning repository...
    git clone %REPO_URL%
) else (
    echo Directory already exists. Skipping clone.
)

cd %DIR_NAME%

REM Create a virtual environment if it does not exist
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate the virtual environment
echo Activating virtual environment...
call venv\Scripts\activate

REM Install dependencies
if exist requirements.txt (
    echo Installing requirements...
    python -m pip install --upgrade pip >nul 2>&1
    pip install -r requirements.txt
)

REM Run the main application
echo Starting the application...
python main.py

REM Keep the window open after execution
pause