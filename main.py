import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from geotime import geocode_locations, create_time_matrix, format_time


def create_data_model(time_matrix, service_times_minutes, total_routes, start_hour, end_hour):
    data = {}
    data['time_matrix'] = time_matrix
    data['service_times'] = service_times_minutes
    data['num_vehicles'] = total_routes
    data['depot'] = 0
    shift_duration_minutes = (end_hour - start_hour) * 60
    data['vehicle_max_time'] = shift_duration_minutes
    return data


def optimize_schedule(file_path, depot_location, num_teams=1, start_hour=8, end_hour=18, lunch_break_hours=1.0):
    """
    Main execution function to read data, build the model, and solve the routing problem.
    Splits tasks into 0.5-hour chunks and enforces a lunch break between 12:00 and 14:00.
    """
    print(f"Loading data from {file_path}...")
    df = pd.read_excel(file_path)
    
    if 'Tempo' not in df.columns:
        df['Tempo'] = 1.0 
        print("Column 'Tempo' missing. Applied default 1 hour for all tasks.")
        
    # Split tasks into smaller chunks (0.5 hours) to allow precise lunch break interruptions
    max_chunk_hours = 0.5
    split_rows = []
    
    for _, row in df.iterrows():
        duration = row['Tempo']
        if pd.isna(duration) or duration <= 0:
            duration = 1.0
            
        client_name = str(row.get('Cliente', 'Unknown'))
        if pd.isna(row.get('Cliente')):
            client_name = "Unknown"
            
        part = 1
        while duration > max_chunk_hours:
            split_row = row.copy()
            split_row['Tempo'] = max_chunk_hours
            split_row['Cliente'] = f"{client_name} (Part {part})"
            split_rows.append(split_row)
            duration -= max_chunk_hours
            part += 1
            
        if duration > 0:
            final_row = row.copy()
            final_row['Tempo'] = duration
            if part > 1:
                final_row['Cliente'] = f"{client_name} (Part {part})"
            else:
                final_row['Cliente'] = client_name
            split_rows.append(final_row)
            
    df = pd.DataFrame(split_rows)
    
    locations = [depot_location] + df['Ubicazione'].tolist()
    durations_hours = df['Tempo'].tolist()
    service_times_minutes = [0] + [int(hours * 60) for hours in durations_hours]
    clients = ["Imeca"] + df['Cliente'].tolist()
    
    print("Geocoding addresses...")
    coordinates = geocode_locations(locations)
    
    print("Calculating travel time matrix...")
    time_matrix = create_time_matrix(coordinates)
    
    # Overestimate max possible days to ensure the solver has enough empty route variables
    max_possible_days = len(df)
    total_routes = num_teams * max_possible_days
    
    data = create_data_model(time_matrix, service_times_minutes, total_routes, start_hour, end_hour)
    
    manager = pywrapcp.RoutingIndexManager(
        len(data['time_matrix']), data['num_vehicles'], data['depot']
    )
    routing = pywrapcp.RoutingModel(manager)

    def time_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return data['time_matrix'][from_node][to_node] + data['service_times'][from_node]

    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
    
    # High fixed cost encourages using as few days as possible
    routing.SetFixedCostOfAllVehicles(10000)

    time = 'Time'
    routing.AddDimension(
        transit_callback_index,
        60, # Slack time to absorb breaks and waits
        data['vehicle_max_time'], 
        False,  
        time
    )
    time_dimension = routing.GetDimensionOrDie(time)

    # Disjunction penalty allows the solver to drop tasks instead of failing completely
    penalty = 1000000
    for node in range(1, len(data['time_matrix'])):
        routing.AddDisjunction([manager.NodeToIndex(node)], penalty)

    # Configure lunch break between 12:00 and 14:00
    # Calculate the relative start time in minutes from the shift start hour
    lunch_window_start_hour = 12
    lunch_window_end_hour = 14
    
    break_start_min = int(max(0, lunch_window_start_hour - start_hour) * 60)
    break_start_max = int(max(0, lunch_window_end_hour - start_hour - lunch_break_hours) * 60)
    lunch_break_minutes = int(lunch_break_hours * 60)
    
    if lunch_break_minutes > 0 and break_start_max >= break_start_min:
        for vehicle_id in range(data['num_vehicles']):
            break_interval = routing.solver().FixedDurationIntervalVar(
                break_start_min, 
                break_start_max, 
                lunch_break_minutes, 
                False, 
                f"Lunch_Break_{vehicle_id}"
            )
            # Passing data['service_times'] allows the break to interrupt a task chunk
            time_dimension.SetBreakIntervalsOfVehicle([break_interval], vehicle_id, data['service_times'])

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.FromSeconds(20)

    print("Solving optimization problem...")
    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        print_solution(data, manager, routing, solution, clients, num_teams, start_hour, lunch_break_minutes)
    else:
        print("No solution found. Check input constraints.")


def print_solution(data, manager, routing, solution, clients, num_teams, start_hour, lunch_break_minutes):
    """
    Outputs the optimized routing solution as a CSV file and console string,
    merging contiguous tasks and adding an empty row between different days.
    """
    import csv
    
    time_dimension = routing.GetDimensionOrDie('Time')
    
    # ... (parte iniziale di controllo dropped_nodes identica alla precedente) ...
    dropped_nodes = []
    for node in range(routing.Size()):
        if routing.IsStart(node) or routing.IsEnd(node):
            continue
        if solution.Value(routing.NextVar(node)) == node:
            dropped_nodes.append(clients[manager.IndexToNode(node)])
            
    if dropped_nodes:
        print("\nWARNING: The following tasks could not be scheduled:")
        for dropped in dropped_nodes:
            print(f"  - {dropped}")
        print("\n")

    team_day_counters = {team: 1 for team in range(1, num_teams + 1)}
    
    csv_rows = []
    csv_rows.append(["Day", "Team", "Cliente", "Arrivo", "Partenza", "Durata Lavoro Effettivo (min)", "Note"])

    last_day = 1
    
    for vehicle_id in range(data['num_vehicles']):
        index = routing.Start(vehicle_id)
        if routing.IsEnd(solution.Value(routing.NextVar(index))):
            continue
            
        team_index = (vehicle_id % num_teams) + 1
        current_day = team_day_counters[team_index]
        team_day_counters[team_index] += 1

        # LOGICA RIGA VUOTA: se il giorno è cambiato rispetto al precedente, aggiunge una riga vuota
        if current_day > last_day:
            csv_rows.append(["", "", "", "", "", "", ""])
            last_day = current_day
            
        route_nodes = []
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            time_var = time_dimension.CumulVar(index)
            arrival = solution.Min(time_var)
            duration = data['service_times'][node_index]
            client_raw = clients[node_index]
            base_client = client_raw.split(" (Part ")[0] if " (Part " in client_raw else client_raw
            route_nodes.append({'node_index': node_index, 'client': base_client, 'arrival': arrival, 'duration': duration})
            index = solution.Value(routing.NextVar(index))
            
        # Add final depot return
        node_index = manager.IndexToNode(index)
        time_var = time_dimension.CumulVar(index)
        route_nodes.append({'node_index': node_index, 'client': clients[node_index], 'arrival': solution.Min(time_var), 'duration': 0})
        
        # Merge contiguous chunks
        grouped = []
        curr = None
        for node in route_nodes:
            if curr is None:
                curr = {'client': node['client'], 'arrival': node['arrival'], 'duration': node['duration'], 'end_time': node['arrival'] + node['duration'], 'node_index_first': node['node_index'], 'node_index_last': node['node_index']}
            elif node['client'] == curr['client'] and node['client'] != "Imeca":
                curr['duration'] += node['duration']
                curr['end_time'] = node['arrival'] + node['duration']
                curr['node_index_last'] = node['node_index']
            else:
                grouped.append(curr)
                curr = {'client': node['client'], 'arrival': node['arrival'], 'duration': node['duration'], 'end_time': node['arrival'] + node['duration'], 'node_index_first': node['node_index'], 'node_index_last': node['node_index']}
        if curr: grouped.append(curr)
            
        for i, g in enumerate(grouped):
            note = f"Pausa inclusa ({g['end_time'] - g['arrival'] - g['duration']} min)" if (g['end_time'] - g['arrival']) > g['duration'] else ""
            csv_rows.append([str(current_day), str(team_index), g['client'], format_time(start_hour, g['arrival']), format_time(start_hour, g['end_time']), str(g['duration']), note])
            if i < len(grouped) - 1:
                next_g = grouped[i+1]
                gap = next_g['arrival'] - g['end_time'] - data['time_matrix'][g['node_index_last']][next_g['node_index_first']]
                if lunch_break_minutes > 0 and gap >= lunch_break_minutes:
                    csv_rows.append([str(current_day), str(team_index), "Pausa Pranzo", format_time(start_hour, g['end_time']), format_time(start_hour, g['end_time'] + gap), str(gap), ""])
                    
    output_filename = "schedule_output.csv"
    with open(output_filename, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerows(csv_rows)
        
    print(f"\nOptimization complete. CSV saved to {output_filename}.")



def run_gui():

    def browse_file():
        # Added .xlsm for macro-enabled workbooks and .xls for legacy formats
        filename = filedialog.askopenfilename(filetypes=[
            ("Excel files", "*.xlsx *.xlsm *.xls"),
            ("All files", "*.*")
        ])
        entry_file.delete(0, tk.END)
        entry_file.insert(0, filename)

    def start_optimization():
        try:
            file_path = entry_file.get()
            depot = entry_depot.get()
            teams = int(entry_teams.get())
            start = int(entry_start.get())
            end = int(entry_end.get())
            lunch = float(entry_lunch.get())
            
            # Richiama la funzione principale
            optimize_schedule(file_path, depot, teams, start, end, lunch)
            messagebox.showinfo("Successo", "Ottimizzazione completata! Controlla 'schedule_output.csv'")
        except Exception as e:
            messagebox.showerror("Errore", f"Si è verificato un errore: {e}")

    root = tk.Tk()
    root.title("Imeca Routing Optimizer")

    # Layout GUI
    tk.Label(root, text="File Excel:").grid(row=0, column=0, padx=5, pady=5)
    entry_file = tk.Entry(root, width=40)
    entry_file.grid(row=0, column=1, padx=5, pady=5)
    tk.Button(root, text="Sfoglia", command=browse_file).grid(row=0, column=2, padx=5, pady=5)

    tk.Label(root, text="Ubicazione Deposito:").grid(row=1, column=0, padx=5, pady=5)
    entry_depot = tk.Entry(root)
    entry_depot.insert(0, "Ceto")
    entry_depot.grid(row=1, column=1, padx=5, pady=5, sticky="w")

    tk.Label(root, text="Numero Squadre:").grid(row=2, column=0, padx=5, pady=5)
    entry_teams = tk.Entry(root)
    entry_teams.insert(0, "1")
    entry_teams.grid(row=2, column=1, padx=5, pady=5, sticky="w")

    tk.Label(root, text="Ora Inizio (es. 8):").grid(row=3, column=0, padx=5, pady=5)
    entry_start = tk.Entry(root)
    entry_start.insert(0, "8")
    entry_start.grid(row=3, column=1, padx=5, pady=5, sticky="w")

    tk.Label(root, text="Ora Fine (es. 18):").grid(row=4, column=0, padx=5, pady=5)
    entry_end = tk.Entry(root)
    entry_end.insert(0, "18")
    entry_end.grid(row=4, column=1, padx=5, pady=5, sticky="w")

    tk.Label(root, text="Ore Pranzo (es. 1.0):").grid(row=5, column=0, padx=5, pady=5)
    entry_lunch = tk.Entry(root)
    entry_lunch.insert(0, "1.0")
    entry_lunch.grid(row=5, column=1, padx=5, pady=5, sticky="w")

    tk.Button(root, text="Avvia Ottimizzazione", command=start_optimization, bg="green", fg="white").grid(row=6, column=1, pady=20)

    root.mainloop()


if __name__ == '__main__':
    run_gui()
