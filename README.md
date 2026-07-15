# Workers Routing

This repository contains the `workers_routing` application. The installation and setup processes can be fully automated using the provided scripts, which will check for system dependencies (Git, Python), install them if missing, clone the repository, set up a virtual environment, install Python requirements, and execute the main application.

## Quick Start (Automated Setup)


### Windows

Open PowerShell and run the following command to download and execute the batch script:

```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/ale-gaudenzi/workers_routing/main/install_and_run.bat" -OutFile "install_and_run.bat"; .\install_and_run.bat
```

*Note: If the script installs Git or Python via winget, it will prompt you to press any key to exit. After the window closes, run `install_and_run.bat` a second time to load the new environment variables and proceed with the application setup.*

### Linux / macOS

```bash
curl -O [https://raw.githubusercontent.com/ale-gaudenzi/workers_routing/main/install_and_run.sh](https://raw.githubusercontent.com/ale-gaudenzi/workers_routing/main/install_and_run.sh) && chmod +x install_and_run.sh && ./install_and_run.sh

```

*Note: The script may prompt you for your `sudo` password to install system dependencies (Git, Python) using your OS package manager (apt, dnf, pacman, or brew).*

