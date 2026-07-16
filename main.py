import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import time
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from geopy.distance import geodesic
from datetime import datetime, timedelta
import os

def geocode_location(address):
    geolocator = Nominatim(user_agent="worker_scheduler_v6")
    try:
        # Enforce delay to respect API rate limits
        time.sleep(1.2)
        location = geolocator.geocode(address, timeout=10)
        if location:
            return location.latitude, location.longitude
        return None, None
    except GeocoderTimedOut:
        return None, None

def format_duration(td):
    total_minutes = int(td.total_seconds() // 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    
    if hours > 0 and minutes > 0:
        return f"{hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h"
    else:
        return f"{minutes}m"

def simulate_event(current_time, duration, lunch_taken, lunch_start_limit, lunch_dur):
    # Calculates the final time and lunch status for any duration without logging it
    t = current_time
    l_taken = lunch_taken
    
    if duration.total_seconds() == 0:
        return t, l_taken
        
    # If the simulation starts at or after lunch time and lunch hasn't been taken
    if not l_taken and t >= lunch_start_limit:
        t += lunch_dur
        l_taken = True
        
    # If the event crosses the lunch start limit
    if not l_taken and t < lunch_start_limit and (t + duration > lunch_start_limit):
        t += duration + lunch_dur
        l_taken = True
    else:
        t += duration
        
    return t, l_taken

def execute_event(schedule, event_name, location, duration, current_time, lunch_taken, lunch_start_limit, lunch_dur, current_day):
    # Logs the event to the schedule array, splitting it automatically if it crosses lunch
    remaining = duration
    if remaining.total_seconds() == 0:
        return current_time, lunch_taken
        
    # If we are already at or past lunch time and haven't taken it, log lunch immediately
    if not lunch_taken and current_time >= lunch_start_limit:
        lunch_end = current_time + lunch_dur
        schedule.append({
            "Day": current_day,
            "Cliente": "LUNCH BREAK",
            "Ubicazione": "N/A",
            "Start Time": current_time.strftime("%H:%M"),
            "End Time": lunch_end.strftime("%H:%M"),
            "Duration": format_duration(lunch_dur)
        })
        current_time = lunch_end
        lunch_taken = True

    while remaining.total_seconds() > 0:
        if not lunch_taken and current_time < lunch_start_limit and (current_time + remaining > lunch_start_limit):
            # Event crosses lunch break limit
            chunk = lunch_start_limit - current_time
            if chunk.total_seconds() > 0:
                label = f"{event_name} (Part 1)"
                schedule.append({
                    "Day": current_day,
                    "Cliente": label,
                    "Ubicazione": location,
                    "Start Time": current_time.strftime("%H:%M"),
                    "End Time": lunch_start_limit.strftime("%H:%M"),
                    "Duration": format_duration(chunk)
                })
                remaining -= chunk
                current_time = lunch_start_limit

            # Insert lunch
            lunch_end = current_time + lunch_dur
            schedule.append({
                "Day": current_day,
                "Cliente": "LUNCH BREAK",
                "Ubicazione": "N/A",
                "Start Time": current_time.strftime("%H:%M"),
                "End Time": lunch_end.strftime("%H:%M"),
                "Duration": format_duration(lunch_dur)
            })
            current_time = lunch_end
            lunch_taken = True
        else:
            # Log the remaining chunk of the event
            label = f"{event_name} (Part 2)" if duration != remaining else event_name
            end_t = current_time + remaining
            schedule.append({
                "Day": current_day,
                "Cliente": label,
                "Ubicazione": location,
                "Start Time": current_time.strftime("%H:%M"),
                "End Time": end_t.strftime("%H:%M"),
                "Duration": format_duration(remaining)
            })
            current_time = end_t
            remaining = timedelta(0)
            
    return current_time, lunch_taken

def process_schedule(file_path, depot, start_time_str, end_time_str, lunch_duration_hours, root):
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to read file: {e}")
        return
    
    required_columns = {'Ubicazione', 'Tempo', 'Cliente'}
    if not required_columns.issubset(df.columns):
        messagebox.showerror("Error", f"Missing columns. Required: {required_columns}")
        return

    try:
        start_time_base = datetime.strptime(start_time_str, "%H:%M")
        end_time_base = datetime.strptime(end_time_str, "%H:%M")
    except ValueError:
        messagebox.showerror("Error", "Invalid time format. Use HH:MM.")
        return

    depot_lat, depot_lon = geocode_location(depot)
    if depot_lat is None:
        messagebox.showerror("Error", "Failed to geocode depot location.")
        return

    # Cache unique addresses to minimize API calls
    unique_addresses = df['Ubicazione'].unique()
    address_cache = {}
    
    for addr in unique_addresses:
        lat, lon = geocode_location(addr)
        if lat is not None and lon is not None:
            address_cache[addr] = (lat, lon)
        root.update()

    unassigned_tasks = {}
    for index, row in df.iterrows():
        addr = row['Ubicazione']
        if addr in address_cache:
            unassigned_tasks[index] = {
                'cliente': row['Cliente'],
                'ubicazione': addr,
                'duration': timedelta(hours=float(row['Tempo'])),
                'lat': address_cache[addr][0],
                'lon': address_cache[addr][1]
            }

    schedule = []
    skipped_tasks = []
    current_day = 1
    
    base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    current_time = base_date + timedelta(hours=start_time_base.hour, minutes=start_time_base.minute)
    end_limit = base_date + timedelta(hours=end_time_base.hour, minutes=end_time_base.minute) + timedelta(minutes=30)
    lunch_start_limit = base_date + timedelta(hours=12)
    lunch_dur = timedelta(hours=lunch_duration_hours)
    
    current_lat, current_lon = depot_lat, depot_lon
    lunch_taken = False
    
    empty_row = {
        "Day": "",
        "Cliente": "",
        "Ubicazione": "",
        "Start Time": "",
        "End Time": "",
        "Duration": ""
    }
    
    schedule.append({
        "Day": current_day,
        "Cliente": "DEPOT START", 
        "Ubicazione": depot,
        "Start Time": current_time.strftime("%H:%M"),
        "End Time": current_time.strftime("%H:%M"),
        "Duration": format_duration(timedelta(0))
    })

    while unassigned_tasks:
        best_task_key = None
        min_dist = float('inf')
        
        # Identify the closest valid task
        for key, task in unassigned_tasks.items():
            dist_to_task = geodesic((current_lat, current_lon), (task['lat'], task['lon'])).kilometers
            travel_to_task = timedelta(hours=dist_to_task / 50.0)
            
            dist_to_depot = geodesic((task['lat'], task['lon']), (depot_lat, depot_lon)).kilometers
            travel_to_depot = timedelta(hours=dist_to_depot / 50.0)
            
            # Simulate timeline to ensure task and return journey fits in the workday
            sim_time, sim_lunch = simulate_event(current_time, travel_to_task, lunch_taken, lunch_start_limit, lunch_dur)
            sim_time, sim_lunch = simulate_event(sim_time, task['duration'], sim_lunch, lunch_start_limit, lunch_dur)
            sim_time, sim_lunch = simulate_event(sim_time, travel_to_depot, sim_lunch, lunch_start_limit, lunch_dur)
            
            if sim_time <= end_limit:
                if dist_to_task < min_dist:
                    min_dist = dist_to_task
                    best_task_key = key
                    
        # If no tasks fit, close the day
        if best_task_key is None:
            day_start_time = base_date + timedelta(hours=start_time_base.hour, minutes=start_time_base.minute)
            if current_time == day_start_time:
                # The remaining task is too long to fit into any single workday
                longest_key = max(unassigned_tasks, key=lambda k: unassigned_tasks[k]['duration'])
                skipped_tasks.append(unassigned_tasks.pop(longest_key)['cliente'])
                continue

            # Log return to depot
            if (current_lat, current_lon) != (depot_lat, depot_lon):
                dist = geodesic((current_lat, current_lon), (depot_lat, depot_lon)).kilometers
                travel_time = timedelta(hours=dist / 50.0)
                current_time, lunch_taken = execute_event(
                    schedule, "RETURN TO DEPOT", depot, travel_time, 
                    current_time, lunch_taken, lunch_start_limit, lunch_dur, current_day
                )
            
            schedule.append(empty_row)
            
            # Reset parameters for the next working day
            current_day += 1
            base_date += timedelta(days=1)
            current_time = base_date + timedelta(hours=start_time_base.hour, minutes=start_time_base.minute)
            end_limit = base_date + timedelta(hours=end_time_base.hour, minutes=end_time_base.minute) + timedelta(minutes=30)
            lunch_start_limit = base_date + timedelta(hours=12)
            current_lat, current_lon = depot_lat, depot_lon
            lunch_taken = False
            
            schedule.append({
                "Day": current_day,
                "Cliente": "DEPOT START", 
                "Ubicazione": depot,
                "Start Time": current_time.strftime("%H:%M"),
                "End Time": current_time.strftime("%H:%M"),
                "Duration": format_duration(timedelta(0))
            })
            continue
            
        task = unassigned_tasks.pop(best_task_key)
        
        # Execute Travel to Task
        if (current_lat, current_lon) != (task['lat'], task['lon']):
            dist_km = geodesic((current_lat, current_lon), (task['lat'], task['lon'])).kilometers
            travel_dur = timedelta(hours=dist_km / 50.0)
            current_time, lunch_taken = execute_event(
                schedule, "TRAVEL", f"To: {task['ubicazione']}", travel_dur, 
                current_time, lunch_taken, lunch_start_limit, lunch_dur, current_day
            )
            current_lat, current_lon = task['lat'], task['lon']
            
        # Execute Task Operations
        current_time, lunch_taken = execute_event(
            schedule, task['cliente'], task['ubicazione'], task['duration'], 
            current_time, lunch_taken, lunch_start_limit, lunch_dur, current_day
        )

    # Conclude the final day with a return to the depot
    if (current_lat, current_lon) != (depot_lat, depot_lon):
        dist = geodesic((current_lat, current_lon), (depot_lat, depot_lon)).kilometers
        travel_time = timedelta(hours=dist / 50.0)
        execute_event(
            schedule, "RETURN TO DEPOT", depot, travel_time, 
            current_time, lunch_taken, lunch_start_limit, lunch_dur, current_day
        )

    # Export output
    out_df = pd.DataFrame(schedule)
    base_name = os.path.splitext(file_path)[0]
    out_path = f"{base_name}_scheduled.xlsx"
    out_df.to_excel(out_path, index=False)
    
    status_msg = f"Schedule created successfully.\nOutput saved to:\n{out_path}"
    if skipped_tasks:
        status_msg += f"\n\nWARNING: Skipped tasks due to exceeding daily limits:\n{', '.join(skipped_tasks)}"
        messagebox.showwarning("Warning", status_msg)
    else:
        messagebox.showinfo("Success", status_msg)

def run_app():
    root = tk.Tk()
    root.title("Worker Task Scheduler")
    root.geometry("450x350")
    root.resizable(False, False)
    
    tk.Label(root, text="Depot Location (Starting Point):").pack(pady=(15, 2))
    depot_entry = tk.Entry(root, width=50)
    depot_entry.pack()
    
    tk.Label(root, text="Start Time (HH:MM):").pack(pady=(10, 2))
    start_entry = tk.Entry(root, width=20)
    start_entry.insert(0, "08:00")
    start_entry.pack()
    
    tk.Label(root, text="End Time (HH:MM):").pack(pady=(10, 2))
    end_entry = tk.Entry(root, width=20)
    end_entry.insert(0, "18:00")
    end_entry.pack()
    
    tk.Label(root, text="Lunch Duration (Hours):").pack(pady=(10, 2))
    lunch_entry = tk.Entry(root, width=20)
    lunch_entry.insert(0, "1.0")
    lunch_entry.pack()
    
    def on_submit():
        if not depot_entry.get().strip():
            messagebox.showerror("Error", "Please enter a Depot Location.")
            return

        file_path = filedialog.askopenfilename(
            title="Select Input Excel File",
            filetypes=[("Excel files", "*.xlsx *.xls")]
        )
        
        if file_path:
            try:
                lunch_duration = float(lunch_entry.get())
            except ValueError:
                messagebox.showerror("Error", "Lunch duration must be a number.")
                return
            
            submit_btn.config(state="disabled", text="Processing...")
            root.update()

            process_schedule(
                file_path, 
                depot_entry.get().strip(), 
                start_entry.get().strip(), 
                end_entry.get().strip(), 
                lunch_duration,
                root
            )
            
            submit_btn.config(state="normal", text="Select Excel File and Generate")

    submit_btn = tk.Button(root, text="Select Excel File and Generate", command=on_submit, height=2)
    submit_btn.pack(pady=20)
    
    root.mainloop()

if __name__ == "__main__":
    run_app()