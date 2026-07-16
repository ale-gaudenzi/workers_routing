@echo off
REM =======================================================
REM Setup and Execution Script for Worker Task Scheduler
REM =======================================================

REM Check if Git is installed
git --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Error: Git is not installed or not added to system PATH.
    echo Please install Git and run this script again.
    pause
    exit /b
)

REM Check if the repository directory already exists
IF NOT EXIST "workers_routing" (
    echo Repository not found. Cloning repository...
    git clone https://github.com/ale-gaudenzi/workers_routing.git
    IF %ERRORLEVEL% NEQ 0 (
        echo Error: Failed to clone the repository.
        pause
        exit /b
    )
    cd workers_routing
) ELSE (
    echo Repository found. Navigating and pulling latest changes...
    cd workers_routing
    git pull
    IF %ERRORLEVEL% NEQ 0 (
        echo Error: Failed to pull the latest changes.
        pause
        exit /b
    )
)

REM Check if Python is installed
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Error: Python is not installed or not added to system PATH.
    echo Please install Python and run this script again.
    pause
    exit /b
)

REM Create a virtual environment if it does not exist
IF NOT EXIST "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate the virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Upgrade pip to the latest version
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install required dependencies
echo Installing required dependencies...
pip install pandas openpyxl geopy

REM Run the main application
echo Starting the application...
python main.py

pause