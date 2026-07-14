# Workers Routing Optimizer

This project optimizes field-service / delivery routing and scheduling using **Google OR-Tools**.  
Workflow: read tasks from an **Excel** file, geocode addresses with **Nominatim (geopy)**, generate a travel time matrix using **OSRM Table API** (with a Haversine fallback), solve the routing/scheduling problem for multiple teams, and export the final plan to a **CSV** file. A **Tkinter GUI** is included.

## Installation (step-by-step)

1) Open the terminal and clone the repo
```
git clone https://github.com/ale-gaudenzi/workers_routing.git
cd workers_routing
```
2) Create and activate a virtual environment

Windows (PowerShell):
```
python -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS / Linux:
```
python3 -m venv .venv
source .venv/bin/activate
```
3) Install dependencies
```
pip install -U pip
pip install pandas ortools geopy requests openpyxl
```
If Tkinter is missing on Linux (Debian/Ubuntu):
```
sudo apt-get update
sudo apt-get install -y python3-tk
```

## Excel input format

main.py reads a .xlsx file with at least these columns:

- Ubicazione (required): task address/location
- Cliente (used for labeling in output; if missing it is set to "Unknown")
- Tempo (optional): task duration in hours  
  If the column is missing or a value is invalid/empty, a default of 1.0 hour is applied.

Note: the code splits tasks into 0.5-hour chunks to better handle interruptions (e.g., lunch break).

## Usage

```
python main.py
```

In the GUI you can set:
- the Excel file
- depot location (a location/address string, e.g., Ceto)
- number of teams
- start/end work hours (e.g., 8–18)
- lunch break duration (hours, e.g., 1.0)

Generated output:
- schedule_output.csv


## Output: schedule_output.csv

The CSV is written as:
- filename: schedule_output.csv
- encoding: utf-8
- delimiter: ;

Columns:
- Day
- Team
- Cliente
- Arrivo
- Partenza
- Durata Lavoro Effettivo (min)
- Note

If some tasks cannot be assigned, they are reported in the console as dropped tasks.

## Repository contents

- main.py — OR-Tools optimization, constraints (work hours, service times, lunch break), CSV export, Tkinter GUI
- geotime.py — address geocoding (Nominatim) + travel time matrix (OSRM) with Haversine fallback + time formatting utility

## Requirements

- Python 3 (recommended 3.9+)
- Python dependencies used in the code:
  - pandas
  - ortools
  - geopy
  - requests
  - tkinter (standard library; on some Linux distros it must be installed separately)
- To read .xlsx with pandas you often also need:
  - openpyxl

## Notes on geocoding and travel-time matrix

- Geocoding: geopy.Nominatim with a custom user-agent and retries for rate limiting/timeouts.
- OSRM: uses the public endpoint router.project-osrm.org (Table API, driving profile).
- Fallback: if OSRM fails, it estimates travel times using Haversine distance and an average speed (default 50 km/h).

