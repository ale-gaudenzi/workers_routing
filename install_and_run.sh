#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Function to automatically install missing dependencies based on OS
install_dependencies() {
    echo "Attempting to install missing dependencies..."
    if command -v apt-get &> /dev/null; then
        echo "Debian/Ubuntu system detected. Requesting sudo privileges..."
        sudo apt-get update
        sudo apt-get install -y git python3 python3-venv python3-pip
    elif command -v dnf &> /dev/null; then
        echo "Fedora/RHEL system detected. Requesting sudo privileges..."
        sudo dnf install -y git python3 python3-pip
    elif command -v pacman &> /dev/null; then
        echo "Arch system detected. Requesting sudo privileges..."
        sudo pacman -Sy --noconfirm git python python-pip
    elif command -v brew &> /dev/null; then
        echo "macOS/Homebrew system detected..."
        brew install git python3
    else
        echo "Error: Supported package manager not found (apt, dnf, pacman, brew)."
        echo "Please install Git and Python3 manually."
        exit 1
    fi
}

MISSING_DEPS=0

# Check if Git is installed
if ! command -v git &> /dev/null; then
    echo "Git is missing."
    MISSING_DEPS=1
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python3 is missing."
    MISSING_DEPS=1
fi

# Install dependencies if any are missing
if [ "$MISSING_DEPS" -eq 1 ]; then
    install_dependencies
fi

REPO_URL="https://github.com/ale-gaudenzi/workers_routing.git"
DIR_NAME="workers_routing"

# Clone the repository if it does not exist locally
if [ ! -d "$DIR_NAME" ]; then
    echo "Cloning repository..."
    git clone "$REPO_URL"
else
    echo "Directory already exists. Skipping clone."
fi

cd "$DIR_NAME" || exit

# Create a virtual environment if it does not exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate the virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
if [ -f "requirements.txt" ]; then
    echo "Installing requirements..."
    python3 -m pip install --upgrade pip &> /dev/null
    pip install -r requirements.txt
fi

# Run the main application
echo "Starting the application..."
python3 main.py