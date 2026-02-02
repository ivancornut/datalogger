#!/usr/bin/env python3
"""
Datalogger JSON Configuration Generator
A tkinter GUI for creating JSON configuration files for dataloggers.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json


class SensorDialog(tk.Toplevel):
    """Base class for sensor configuration dialogs."""
    
    def __init__(self, parent, title):
        super().__init__(parent)
        self.title(title)
        self.result = None
        self.transient(parent)
        self.grab_set()
        
        # Center the dialog
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        
        self.create_widgets()
        
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.wait_window(self)
    
    def create_widgets(self):
        """Override in subclasses."""
        pass
    
    def validate(self):
        """Override in subclasses."""
        return True
    
    def ok(self):
        if self.validate():
            self.destroy()
    
    def cancel(self):
        self.result = None
        self.destroy()


class DendroDialog(SensorDialog):
    """Dialog for configuring dendrometer sensors."""
    
    def __init__(self, parent):
        self.name_entries = []
        self.excite_entries = []
        super().__init__(parent, "Add Dendrometer Sensor")
    
    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # I2C selection
        ttk.Label(main_frame, text="I2C Bus:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.i2c_var = tk.IntVar(value=0)
        i2c_frame = ttk.Frame(main_frame)
        i2c_frame.grid(row=0, column=1, sticky=tk.W, pady=2)
        ttk.Radiobutton(i2c_frame, text="0", variable=self.i2c_var, value=0).pack(side=tk.LEFT)
        ttk.Radiobutton(i2c_frame, text="1", variable=self.i2c_var, value=1).pack(side=tk.LEFT)
        
        # Address
        ttk.Label(main_frame, text="Address (decimal, e.g. 72):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.address_entry = ttk.Entry(main_frame, width=20)
        self.address_entry.grid(row=1, column=1, sticky=tk.W, pady=2)
        self.address_entry.insert(0, "72")
        
        # Number of dendrometers
        ttk.Label(main_frame, text="Number (1 or 2):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.number_var = tk.IntVar(value=1)
        number_frame = ttk.Frame(main_frame)
        number_frame.grid(row=2, column=1, sticky=tk.W, pady=2)
        ttk.Radiobutton(number_frame, text="1", variable=self.number_var, value=1, 
                       command=self.update_dynamic_fields).pack(side=tk.LEFT)
        ttk.Radiobutton(number_frame, text="2", variable=self.number_var, value=2,
                       command=self.update_dynamic_fields).pack(side=tk.LEFT)
        
        # Timestep
        ttk.Label(main_frame, text="Timestep (seconds):").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.timestep_entry = ttk.Entry(main_frame, width=20)
        self.timestep_entry.grid(row=3, column=1, sticky=tk.W, pady=2)
        self.timestep_entry.insert(0, "10")
        
        # Dynamic frame for excite pins and names
        self.dynamic_frame = ttk.LabelFrame(main_frame, text="Dendrometer Configuration", padding="5")
        self.dynamic_frame.grid(row=4, column=0, columnspan=2, sticky=tk.EW, pady=10)
        
        self.update_dynamic_fields()
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="OK", command=self.ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.cancel).pack(side=tk.LEFT, padx=5)
    
    def update_dynamic_fields(self):
        # Clear existing widgets
        for widget in self.dynamic_frame.winfo_children():
            widget.destroy()
        
        self.name_entries = []
        self.excite_entries = []
        
        num = self.number_var.get()
        
        for i in range(num):
            row_frame = ttk.Frame(self.dynamic_frame)
            row_frame.pack(fill=tk.X, pady=2)
            
            ttk.Label(row_frame, text=f"Dendro {i+1} Name:").pack(side=tk.LEFT)
            name_entry = ttk.Entry(row_frame, width=15)
            name_entry.pack(side=tk.LEFT, padx=5)
            name_entry.insert(0, f"dendro_{i+1}")
            self.name_entries.append(name_entry)
            
            ttk.Label(row_frame, text="Excite Pin:").pack(side=tk.LEFT, padx=(10, 0))
            excite_entry = ttk.Entry(row_frame, width=8)
            excite_entry.pack(side=tk.LEFT, padx=5)
            excite_entry.insert(0, str(6 + i))
            self.excite_entries.append(excite_entry)
    
    def validate(self):
        try:
            # Validate address (decimal number)
            address = int(self.address_entry.get().strip())
            
            # Validate timestep
            timestep = int(self.timestep_entry.get())
            if timestep <= 0:
                raise ValueError("Timestep must be positive")
            
            # Validate excite pins
            excite_pins = []
            for entry in self.excite_entries:
                excite_pins.append(int(entry.get()))
            
            # Collect names
            names = [entry.get().strip() for entry in self.name_entries]
            if any(not name for name in names):
                raise ValueError("All names must be filled")
            
            self.result = {
                "type": "dendro",
                "params": {
                    "I2C": self.i2c_var.get(),
                    "address": address,
                    "number": self.number_var.get(),
                    "excite": excite_pins,
                    "names": names
                },
                "timestep": timestep
            }
            return True
            
        except ValueError as e:
            messagebox.showerror("Validation Error", f"Invalid input: {e}")
            return False


class CS616Dialog(SensorDialog):
    """Dialog for configuring CS616 soil moisture sensors."""
    
    def __init__(self, parent):
        super().__init__(parent, "Add CS616 Sensor")
    
    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Number
        ttk.Label(main_frame, text="Number (0-8):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.number_spinbox = ttk.Spinbox(main_frame, from_=0, to=8, width=10)
        self.number_spinbox.grid(row=0, column=1, sticky=tk.W, pady=2)
        self.number_spinbox.set(8)
        
        # Control Pins (3 pins)
        ttk.Label(main_frame, text="Control Pins (3 pins):").grid(row=1, column=0, sticky=tk.W, pady=2)
        ctrl_frame = ttk.Frame(main_frame)
        ctrl_frame.grid(row=1, column=1, sticky=tk.W, pady=2)
        
        self.ctrl_entries = []
        default_pins = [8, 9, 10]
        for i in range(3):
            entry = ttk.Entry(ctrl_frame, width=6)
            entry.pack(side=tk.LEFT, padx=2)
            entry.insert(0, str(default_pins[i]))
            self.ctrl_entries.append(entry)
        
        # Measurement Pin
        ttk.Label(main_frame, text="Measurement Pin:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.meas_entry = ttk.Entry(main_frame, width=10)
        self.meas_entry.grid(row=2, column=1, sticky=tk.W, pady=2)
        self.meas_entry.insert(0, "13")
        
        # Timestep
        ttk.Label(main_frame, text="Timestep (seconds):").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.timestep_entry = ttk.Entry(main_frame, width=10)
        self.timestep_entry.grid(row=3, column=1, sticky=tk.W, pady=2)
        self.timestep_entry.insert(0, "10")
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="OK", command=self.ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.cancel).pack(side=tk.LEFT, padx=5)
    
    def validate(self):
        try:
            number = int(self.number_spinbox.get())
            if not 0 <= number <= 8:
                raise ValueError("Number must be between 0 and 8")
            
            ctrl_pins = [int(entry.get()) for entry in self.ctrl_entries]
            meas_pin = int(self.meas_entry.get())
            
            timestep = int(self.timestep_entry.get())
            if timestep <= 0:
                raise ValueError("Timestep must be positive")
            
            self.result = {
                "type": "CS616",
                "params": {
                    "number": number,
                    "ctrlPins": ctrl_pins,
                    "measPin": meas_pin
                },
                "timestep": timestep
            }
            return True
            
        except ValueError as e:
            messagebox.showerror("Validation Error", f"Invalid input: {e}")
            return False


class SHT45Dialog(SensorDialog):
    """Dialog for configuring SHT45 temperature/humidity sensors."""
    
    def __init__(self, parent):
        super().__init__(parent, "Add SHT45 Sensor")
    
    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # I2C selection
        ttk.Label(main_frame, text="I2C Bus:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.i2c_var = tk.IntVar(value=0)
        i2c_frame = ttk.Frame(main_frame)
        i2c_frame.grid(row=0, column=1, sticky=tk.W, pady=2)
        ttk.Radiobutton(i2c_frame, text="0", variable=self.i2c_var, value=0).pack(side=tk.LEFT)
        ttk.Radiobutton(i2c_frame, text="1", variable=self.i2c_var, value=1).pack(side=tk.LEFT)
        
        # Name
        ttk.Label(main_frame, text="Sensor Name:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.name_entry = ttk.Entry(main_frame, width=20)
        self.name_entry.grid(row=1, column=1, sticky=tk.W, pady=2)
        self.name_entry.insert(0, "Outside")
        
        # Timestep
        ttk.Label(main_frame, text="Timestep (seconds):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.timestep_entry = ttk.Entry(main_frame, width=10)
        self.timestep_entry.grid(row=2, column=1, sticky=tk.W, pady=2)
        self.timestep_entry.insert(0, "10")
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="OK", command=self.ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.cancel).pack(side=tk.LEFT, padx=5)
    
    def validate(self):
        try:
            name = self.name_entry.get().strip()
            if not name:
                raise ValueError("Name cannot be empty")
            
            timestep = int(self.timestep_entry.get())
            if timestep <= 0:
                raise ValueError("Timestep must be positive")
            
            # Build params - only include I2C if it's set to 1 (non-default)
            params = {"name": name}
            if self.i2c_var.get() == 1:
                params["I2C"] = 1
            
            self.result = {
                "type": "SHT45",
                "params": params,
                "timestep": timestep
            }
            return True
            
        except ValueError as e:
            messagebox.showerror("Validation Error", f"Invalid input: {e}")
            return False


class DataloggerConfigApp:
    """Main application window for datalogger configuration."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Datalogger JSON Configuration Generator")
        self.root.geometry("700x600")
        
        self.sensors = []  # List to store sensor configurations
        
        self.create_widgets()
    
    def create_widgets(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # ===== Device Information Section =====
        info_frame = ttk.LabelFrame(main_frame, text="Device Information", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Grid layout for device info
        ttk.Label(info_frame, text="Device Name:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.device_name_entry = ttk.Entry(info_frame, width=40)
        self.device_name_entry.grid(row=0, column=1, sticky=tk.W, pady=2, padx=5)
        
        ttk.Label(info_frame, text="Description:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.description_entry = ttk.Entry(info_frame, width=40)
        self.description_entry.grid(row=1, column=1, sticky=tk.W, pady=2, padx=5)
        
        ttk.Label(info_frame, text="Named Location:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.named_location_entry = ttk.Entry(info_frame, width=40)
        self.named_location_entry.grid(row=2, column=1, sticky=tk.W, pady=2, padx=5)
        
        ttk.Label(info_frame, text="Latitude:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.latitude_entry = ttk.Entry(info_frame, width=20)
        self.latitude_entry.grid(row=3, column=1, sticky=tk.W, pady=2, padx=5)
        self.latitude_entry.insert(0, "9999")
        
        ttk.Label(info_frame, text="Longitude:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.longitude_entry = ttk.Entry(info_frame, width=20)
        self.longitude_entry.grid(row=4, column=1, sticky=tk.W, pady=2, padx=5)
        self.longitude_entry.insert(0, "9999")
        
        # ===== Add Sensors Section =====
        sensor_btn_frame = ttk.LabelFrame(main_frame, text="Add Sensors", padding="10")
        sensor_btn_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(sensor_btn_frame, text="Add Dendrometer", 
                  command=self.add_dendro).pack(side=tk.LEFT, padx=5)
        ttk.Button(sensor_btn_frame, text="Add CS616", 
                  command=self.add_cs616).pack(side=tk.LEFT, padx=5)
        ttk.Button(sensor_btn_frame, text="Add SHT45", 
                  command=self.add_sht45).pack(side=tk.LEFT, padx=5)
        
        # ===== Sensors List Section =====
        list_frame = ttk.LabelFrame(main_frame, text="Configured Sensors", padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Treeview for sensors
        columns = ("Type", "Details", "Timestep")
        self.sensor_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        
        self.sensor_tree.heading("Type", text="Type")
        self.sensor_tree.heading("Details", text="Details")
        self.sensor_tree.heading("Timestep", text="Timestep (s)")
        
        self.sensor_tree.column("Type", width=100)
        self.sensor_tree.column("Details", width=400)
        self.sensor_tree.column("Timestep", width=100)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.sensor_tree.yview)
        self.sensor_tree.configure(yscrollcommand=scrollbar.set)
        
        self.sensor_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Remove sensor button
        ttk.Button(list_frame, text="Remove Selected", 
                  command=self.remove_sensor).pack(side=tk.BOTTOM, pady=5)
        
        # ===== Save Section =====
        save_frame = ttk.Frame(main_frame)
        save_frame.pack(fill=tk.X)
        
        ttk.Button(save_frame, text="Save JSON", 
                  command=self.save_json).pack(side=tk.RIGHT, padx=5)
        ttk.Button(save_frame, text="Preview JSON", 
                  command=self.preview_json).pack(side=tk.RIGHT, padx=5)
        ttk.Button(save_frame, text="Load JSON", 
                  command=self.load_json).pack(side=tk.RIGHT, padx=5)
    
    def add_dendro(self):
        dialog = DendroDialog(self.root)
        if dialog.result:
            self.sensors.append(dialog.result)
            self.update_sensor_list()
    
    def add_cs616(self):
        dialog = CS616Dialog(self.root)
        if dialog.result:
            self.sensors.append(dialog.result)
            self.update_sensor_list()
    
    def add_sht45(self):
        dialog = SHT45Dialog(self.root)
        if dialog.result:
            self.sensors.append(dialog.result)
            self.update_sensor_list()
    
    def update_sensor_list(self):
        # Clear existing items
        for item in self.sensor_tree.get_children():
            self.sensor_tree.delete(item)
        
        # Add sensors
        for i, sensor in enumerate(self.sensors):
            sensor_type = sensor["type"]
            timestep = sensor["timestep"]
            params = sensor["params"]
            
            if sensor_type == "dendro":
                details = f"I2C:{params['I2C']}, Addr:{params['address']}, Names:{params['names']}"
            elif sensor_type == "CS616":
                details = f"Num:{params['number']}, CtrlPins:{params['ctrlPins']}, MeasPin:{params['measPin']}"
            elif sensor_type == "SHT45":
                i2c = params.get('I2C', 0)
                details = f"I2C:{i2c}, Name:{params['name']}"
            else:
                details = str(params)
            
            self.sensor_tree.insert("", tk.END, iid=str(i), values=(sensor_type, details, timestep))
    
    def remove_sensor(self):
        selected = self.sensor_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a sensor to remove")
            return
        
        # Remove in reverse order to maintain indices
        indices = sorted([int(s) for s in selected], reverse=True)
        for idx in indices:
            del self.sensors[idx]
        
        self.update_sensor_list()
    
    def build_json(self):
        """Build the JSON structure from current configuration."""
        # Parse latitude and longitude as numbers
        try:
            latitude = float(self.latitude_entry.get().strip())
            if latitude == int(latitude):
                latitude = int(latitude)
        except ValueError:
            latitude = self.latitude_entry.get().strip()
        
        try:
            longitude = float(self.longitude_entry.get().strip())
            if longitude == int(longitude):
                longitude = int(longitude)
        except ValueError:
            longitude = self.longitude_entry.get().strip()
        
        config = {
            "latitude": latitude,
            "longitude": longitude,
            "named_location": self.named_location_entry.get().strip(),
            "device_name": self.device_name_entry.get().strip(),
            "description": self.description_entry.get().strip(),
            "sensors": [],
            "timesteps": []
        }
        
        # Add sensor configurations
        for sensor in self.sensors:
            sensor_entry = {
                "type": sensor["type"],
                "params": sensor["params"]
            }
            config["sensors"].append(sensor_entry)
            config["timesteps"].append(sensor["timestep"])
        
        return config
    
    def preview_json(self):
        """Show a preview of the JSON output."""
        config = self.build_json()
        json_str = json.dumps(config, indent=4)
        
        # Create preview window
        preview_win = tk.Toplevel(self.root)
        preview_win.title("JSON Preview")
        preview_win.geometry("500x400")
        
        text = tk.Text(preview_win, wrap=tk.NONE)
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Scrollbars
        y_scroll = ttk.Scrollbar(text, orient=tk.VERTICAL, command=text.yview)
        x_scroll = ttk.Scrollbar(text, orient=tk.HORIZONTAL, command=text.xview)
        text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        
        text.insert(tk.END, json_str)
        text.configure(state=tk.DISABLED)
    
    def save_json(self):
        """Save the configuration to a JSON file."""
        config = self.build_json()
        
        # Get default filename from device name
        default_name = self.device_name_entry.get().strip() or "datalogger_config"
        default_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in default_name)
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"{default_name}.json"
        )
        
        if filepath:
            try:
                with open(filepath, 'w') as f:
                    json.dump(config, f, indent=4)
                messagebox.showinfo("Success", f"Configuration saved to:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save file:\n{e}")
    
    def load_json(self):
        """Load a configuration from an existing JSON file."""
        filepath = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not filepath:
            return
        
        try:
            with open(filepath, 'r') as f:
                config = json.load(f)
            
            # Clear current configuration
            self.sensors.clear()
            
            # Load device info
            self.longitude_entry.delete(0, tk.END)
            self.longitude_entry.insert(0, str(config.get("longitude", "9999")))
            
            self.latitude_entry.delete(0, tk.END)
            self.latitude_entry.insert(0, str(config.get("latitude", "9999")))
            
            self.named_location_entry.delete(0, tk.END)
            self.named_location_entry.insert(0, config.get("named_location", ""))
            
            self.device_name_entry.delete(0, tk.END)
            self.device_name_entry.insert(0, config.get("device_name", ""))
            
            self.description_entry.delete(0, tk.END)
            self.description_entry.insert(0, config.get("description", ""))
            
            # Load sensors
            sensors_list = config.get("sensors", [])
            timesteps_list = config.get("timesteps", [])
            
            for i, sensor_data in enumerate(sensors_list):
                timestep = timesteps_list[i] if i < len(timesteps_list) else 10
                sensor = {
                    "type": sensor_data["type"],
                    "params": sensor_data["params"],
                    "timestep": timestep
                }
                self.sensors.append(sensor)
            
            self.update_sensor_list()
            messagebox.showinfo("Success", "Configuration loaded successfully")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file:\n{e}")


def main():
    root = tk.Tk()
    app = DataloggerConfigApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()