import math
import requests
import time
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderTimedOut, GeocoderRateLimited


def geocode_locations(locations, region_suffix=", Italy"):
    """
    Converts a list of location strings into latitude and longitude coordinates.
    Includes a retry mechanism and an extended sleep interval to strictly 
    comply with Nominatim usage policies and recover from HTTP 429 blocks.
    """
    # A custom user_agent helps avoid generic blocks by the Nominatim server
    geolocator = Nominatim(user_agent="imeca_routing_custom_script_1.0")
    coordinates = []
    
    for loc in locations:
        query = f"{loc}{region_suffix}"
        max_retries = 3
        success = False
        
        for attempt in range(max_retries):
            try:
                location = geolocator.geocode(query, timeout=15)
                if location:
                    coordinates.append((location.latitude, location.longitude))
                else:
                    print(f"Warning: Could not geocode {loc}. Defaulting to origin.")
                    coordinates.append((0.0, 0.0))
                success = True
                break
            except GeocoderRateLimited:
                wait_time = (attempt + 1) * 3  
                print(f"Rate limit hit for {loc}. Waiting {wait_time} seconds before retrying...")
                time.sleep(wait_time)
            except GeocoderTimedOut:
                print(f"Timeout for {loc}. Retrying...")
                time.sleep(2)
        
        if not success:
            print(f"Failed to geocode {loc} after {max_retries} attempts. Defaulting to origin.")
            coordinates.append((0.0, 0.0))
            
        time.sleep(1.1)
            
    return coordinates


def create_time_matrix(coordinates, average_speed_kmh=50):
    """
    Generates a time matrix (in minutes) using the OSRM public Distance Matrix API.
    This provides realistic driving times for road networks instead of straight lines.
    Includes a fallback to the Haversine formula if the API request fails.
    """
    matrix_size = len(coordinates)
    time_matrix = [[0] * matrix_size for _ in range(matrix_size)]
    
    # OSRM expects coordinates in longitude,latitude format separated by semicolons
    coord_strings = [f"{lon},{lat}" for lat, lon in coordinates]
    coordinates_param = ";".join(coord_strings)
    
    # Query the OSRM table endpoint for the driving profile
    url = f"http://router.project-osrm.org/table/v1/driving/{coordinates_param}?annotations=duration"
    
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if "durations" in data:
                for i in range(matrix_size):
                    for j in range(matrix_size):
                        duration_sec = data["durations"][i][j]
                        if duration_sec is not None:
                            # Convert seconds to minutes
                            time_matrix[i][j] = int(duration_sec / 60.0)
                return time_matrix
        else:
            print(f"OSRM API returned status {response.status_code}. Using fallback.")
    except requests.exceptions.RequestException as e:
        print(f"OSRM API request failed ({e}). Using fallback.")
        
    # Fallback to Haversine approximation if API is unavailable
    for i in range(matrix_size):
        for j in range(matrix_size):
            if i != j:
                lat1, lon1 = coordinates[i]
                lat2, lon2 = coordinates[j]
                if (lat1, lon1) != (0.0, 0.0) and (lat2, lon2) != (0.0, 0.0):
                    R = 6371.0
                    dlat = math.radians(lat2 - lat1)
                    dlon = math.radians(lon2 - lon1)
                    a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
                         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
                         math.sin(dlon / 2) * math.sin(dlon / 2))
                    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                    dist_km = R * c
                    time_matrix[i][j] = int((dist_km / average_speed_kmh) * 60)
                    
    return time_matrix


def format_time(start_hour, elapsed_minutes):
    total_minutes = int(start_hour * 60 + elapsed_minutes)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"
