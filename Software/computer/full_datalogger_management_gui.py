import tkinter as tk
from tkinter import messagebox, filedialog,ttk
import json
import subprocess
import tempfile
import os
import re
from datetime import datetime
import sys

def update_computer_time():
    """Update the computer time display"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    computer_time_label.config(text=f"Computer Time:\n{current_time}")
    # Schedule next update in 1000ms (1 second)
    root.after(1000, update_computer_time)

def soft_reset_device():
    result = subprocess.run('python -m mpremote soft-reset', capture_output=True, text=True, timeout=10, shell=True)
    #result = subprocess.run([sys.executable, '-m', 'mpremote', 'soft-reset'], capture_output=True, text=True, timeout=20, shell=True)
    if ("no device found" in result.stdout) or ("no device found" in result.stderr) :
        # we need to check in stdout and stderr since 
        # on unix it is stdout and on windows in stderr
        print("No device found")
        root.after(1000, soft_reset_device)
    else:
        print(result.stdout)
        print(result.stderr)
        print("Device soft reset ready to work")

def get_device_time():
    """Get and display the time from the device"""
    result = subprocess.run('python -m mpremote run read_rtc_time.py', 
                          capture_output=True, text=True, timeout=10, shell=True)
    
    if ("no device found" in result.stdout) or ("no device found" in result.stderr):
        device_time_output.config(text="Device Time:\nNo device found")
    elif result.returncode == 0:
        # Extract numbers from the output string
        numbers = re.findall(r'\d+', result.stdout.strip())
        
        if len(numbers) >= 3:
            # Last number = seconds, second to last = minutes, third to last = hours
            seconds = int(numbers[-1])
            minutes = int(numbers[-2])
            hours = int(numbers[-3])
            
            # Format as HH:MM:SS
            formatted_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            device_time_output.config(text=f"Device Time:\n{formatted_time}")
        else:
            # If we can't extract 3 numbers, show raw output
            device_time_output.config(text=f"Device Time:\n{result.stdout.strip()}")
    else:
        device_time_output.config(text=f"Device Time:\n{result.stdout.strip()}")

def get_battery_voltage():
    """Get and display the time from the device"""
    result = subprocess.run('python -m mpremote run read_batt_volt.py', 
                          capture_output=True, text=True, timeout=10, shell=True)
    
    if ("no device found" in result.stdout) or ("no device found" in result.stderr):
        batt_volt_output.config(text="Battery voltage:\nNo device found")
    elif result.returncode == 0:
        # Extract numbers from the output string
        numbers = re.findall(r'\d+', result.stdout.strip())
        # If we can't extract 3 numbers, show raw output
        batt_volt_output.config(text=f"Battery voltage:\n{numbers} V")
    else:
        batt_volt_output.config(text=f"Battery voltage:\n{result.stdout.strip()}")

def get_sd_files():
    """Get list of files on the device SD card"""
    result = subprocess.run('mpremote connect auto run read_sd.py fs ls sd/', 
                          capture_output=True, text=True, timeout=15, shell=True)
    
    if ("no device found" in result.stdout) or ("no device found" in result.stderr):
        sd_files_listbox.delete(0, tk.END)
        sd_files_listbox.insert(0, "No device found")
        download_btn.config(state="disabled")
    elif result.returncode == 0:
        # Parse the file list from stdout
        files = []
        lines = result.stdout.strip().split('\n')
        for line in lines:
            line = line.strip()
            #line = line.split()
            #filesize = line[0]
            #line = line[1]
            if line and not line.startswith('ls :') and line != ':sd/':
                # Remove directory prefix if present
                if line.startswith('sd/'):
                    line = line[3:]
                files.append(line)
        
        # Clear and populate the listbox
        sd_files_listbox.delete(0, tk.END)
        if files:
            for file in files:
                sd_files_listbox.insert(tk.END, file)
            download_btn.config(state="normal")
        else:
            sd_files_listbox.insert(0, "No files found on SD card")
            download_btn.config(state="disabled")
    else:
        sd_files_listbox.delete(0, tk.END)
        sd_files_listbox.insert(0, "Error reading SD card")
        download_btn.config(state="disabled")

def download_selected_files():
    """Download selected files from device SD card"""
    selected_indices = sd_files_listbox.curselection()
    
    if not selected_indices:
        messagebox.showwarning("No Selection", "Please select one or more files to download.")
        return
    
    # Create data directory if it doesn't exist
    data_dir = "data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    downloaded_files = []
    failed_files = []
    
    for index in selected_indices:
        filename = sd_files_listbox.get(index)
        
        # Skip error messages
        if filename in ["No device found", "No files found on SD card", "Error reading SD card"]:
            continue
        print(filename)
        filename = filename.split()[1] # get only the filename and not the size
        try:
            # Download file using mpremote
            result = subprocess.run(f'python -m mpremote run read_sd.py cp :sd/{filename} data/{filename}',capture_output=True, text=True,timeout=30, shell=True)
            
            print(result.stdout)

            if result.returncode == 0:
                downloaded_files.append(filename)
            else:
                failed_files.append(f"{filename}: {result.stdout.strip()}")
                
        except Exception as e:
            print(e)
            failed_files.append(f"{filename}: {str(e)}")
    
    # Show results
    if downloaded_files and not failed_files:
        messagebox.showinfo("Download Complete", 
            f"Successfully downloaded {len(downloaded_files)} file(s) to 'data' directory:\n" + 
            "\n".join(downloaded_files))
    elif downloaded_files and failed_files:
        messagebox.showwarning("Partial Download", 
            f"Downloaded {len(downloaded_files)} file(s):\n" + "\n".join(downloaded_files) + 
            f"\n\nFailed {len(failed_files)} file(s):\n" + "\n".join(failed_files))
    elif failed_files:
        messagebox.showerror("Download Failed", 
            f"Failed to download {len(failed_files)} file(s):\n" + "\n".join(failed_files))

def set_device_time():
    """Set the time on the device"""
    # Run first command: mpremote rtc --set
    result1 = subprocess.run('python -m mpremote rtc --set', 
                           capture_output=True, text=True, timeout=10, shell=True)
    
    if ("no device found" in result1.stdout) or ("no device found" in result1.stderr):
        set_time_output.config(text="Set Time Result:\nNo device found")
        return
    elif result1.returncode != 0:
        set_time_output.config(text=f"Set Time Result:\n{result1.stdout.strip()}")
        return
    
    # Run second command: mpremote run set_rtc_time.py
    result2 = subprocess.run('python -m mpremote run set_rtc_time.py', 
                           capture_output=True, text=True, timeout=10, shell=True)
    
    if ("no device found" in result2.stdout) or ("no device found" in result2.stderr):
        set_time_output.config(text="Set Time Result:\nNo device found")
    elif result2.returncode == 0:
        set_time_output.config(text="Set Time Result:\nDevice time was set")
    else:
        set_time_output.config(text=f"Set Time Result:\n{result2.stdout.strip()}")

def check_device_connection():
    """Check if a device is connected using mpremote"""
    result = subprocess.run('python -m mpremote exec "print(\"connected\")"', 
                          capture_output=True, text=True, timeout=5, shell=True)
    if ("no device found" in result.stdout) or ("no device found" in result.stderr):
        return False
    return result.returncode == 0 and "connected" in result.stdout


# Create main window
root = tk.Tk()
root.title("Datalogger management tool")
root.geometry("500x500")

right_side = tk.Frame(root)
left_side = tk.Frame(root)

left_side.grid(row=0, column=0)
right_side.grid(row=0, column=2)

# RIGHT SIDE - Time Management Section
# Computer time display
computer_time_label = tk.Label(left_side, text="Computer Time:\nLoading...", 
                              font=("Arial", 10, "bold"), justify="center",
                              relief="sunken", bd=2, pady=5)
computer_time_label.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

# Device time section
get_time_btn = tk.Button(left_side, text="Get Device Time", command=get_device_time,
                        bg="lightcyan", font=("Arial", 9, "bold"))
get_time_btn.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

device_time_output = tk.Label(left_side, text="Device Time:\nClick button to check", 
                             font=("Arial", 9), justify="center",
                             relief="sunken", bd=1, pady=5, wraplength=150)
device_time_output.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

# Set device time section
set_time_btn = tk.Button(left_side, text="Set Device Time", command=set_device_time,
                        bg="lightcoral", font=("Arial", 9, "bold"))
set_time_btn.grid(row=3, column=0, padx=10, pady=5, sticky="ew")

set_time_output = tk.Label(left_side, text="Set Time Result:\nClick button to set time", 
                          font=("Arial", 9), justify="center",
                          relief="sunken", bd=1, pady=5, wraplength=150)
set_time_output.grid(row=4, column=0, padx=10, pady=5, sticky="ew")

separator = ttk.Separator(left_side, orient='horizontal')
# Place the separator in a new row (row 1)
# Use 'columnspan' to make it span across both columns (0 and 1)
# Use 'sticky="ew"' to stretch it horizontally to fill the allocated space
separator.grid(row=5, column=0, sticky="ew", pady=10) # Add some vertical padding for spacing

# Battery voltage section
get_batt_volt_btn = tk.Button(left_side, text="Get Battery voltage", command=get_battery_voltage,
                        bg="green", font=("Arial", 9, "bold"))
get_batt_volt_btn.grid(row=6, column=0, padx=10, pady=15, sticky="ew")

batt_volt_output = tk.Label(left_side, text="Battery voltage:\nClick button to check", 
                             font=("Arial", 9), justify="center",
                             relief="sunken", bd=1, pady=5, wraplength=150)
batt_volt_output.grid(row=7, column=0, padx=10, pady=5, sticky="ew")

#Add vertical separator
separator = tk.Frame(root, width=2, bg="gray")
separator.grid(row=0, column=1, rowspan=15, sticky="ns", padx=2)

# SD Card File Management Section
tk.Label(right_side, text="SD Card Files", font=("Arial", 10, "bold")).grid(row=1, column=0, padx=1, pady=(15,5))

get_files_btn = tk.Button(right_side, text="Get SD Card Files", command=get_sd_files,
                         bg="lightsteelblue", font=("Arial", 9, "bold"))
get_files_btn.grid(row=2, column=0, padx=5, pady=5, sticky="ew")

# Listbox for file selection
sd_files_listbox = tk.Listbox(right_side, height=20, width = 50 ,selectmode=tk.MULTIPLE, font=("Arial", 8))
sd_files_listbox.grid(row=3, column=0, padx=5, pady=5, sticky="ew")
sd_files_listbox.insert(0, "Click 'Get SD Card Files' to load")

# Scrollbar for the listbox
scrollbar = tk.Scrollbar(right_side, orient="vertical")
scrollbar.grid(row=3, column=1, sticky="ns", pady=5)
sd_files_listbox.config(yscrollcommand=scrollbar.set)
scrollbar.config(command=sd_files_listbox.yview)

download_btn = tk.Button(right_side, text="Download Selected Files", command=download_selected_files,
                        bg="lightsalmon", font=("Arial", 9, "bold"), state="disabled")
download_btn.grid(row=4, column=0, padx=10, pady=5, sticky="ew")

# Configure column weights for proper resizing
left_side.grid_columnconfigure(0, weight=1)
right_side.grid_columnconfigure(0, weight=1)
right_side.grid_columnconfigure(1, weight=0)  # Scrollbar column

# Start updating computer time
update_computer_time()

# Execute until a device is there to soft reset
soft_reset_device()

# Start the GUI event loop
root.mainloop()
