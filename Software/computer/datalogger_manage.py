import json
import os
import re
import subprocess
import tempfile
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# =============================================================================
# Utility functions
# =============================================================================


def get_relative_path(*parts: str) -> str:
    """Build a relative path that works on both Windows and Linux."""
    return str(Path(*parts))


def list_files(directory: str) -> list[str]:
    """Return a list of all files at the given path."""
    p = Path(directory)
    pattern = "*"
    return [str(f) for f in p.glob(pattern) if f.is_file()]


def get_filename(filepath: str) -> str:
    """Extract the filename from a full path."""
    p = Path(filepath)
    return p.name


def run_mpremote(args: str, timeout: int = 10) -> subprocess.CompletedProcess:
    """Run an mpremote command and return the result."""
    return subprocess.run(
        f"python -m mpremote {args}",
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=True,
    )


def device_not_found(result: subprocess.CompletedProcess) -> bool:
    """Check if an mpremote result indicates no device was found."""
    return ("no device found" in result.stdout) or ("no device found" in result.stderr)


# =============================================================================
# Sensor configuration dialogs (from config_generator.py)
# =============================================================================


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
        ttk.Radiobutton(number_frame,text="1",variable=self.number_var,value=1,command=self.update_dynamic_fields,).pack(side=tk.LEFT)
        ttk.Radiobutton(number_frame,text="2",variable=self.number_var,value=2,command=self.update_dynamic_fields,).pack(side=tk.LEFT)

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
        for widget in self.dynamic_frame.winfo_children():
            widget.destroy()

        self.name_entries = []
        self.excite_entries = []
        num = self.number_var.get()

        for i in range(num):
            row_frame = ttk.Frame(self.dynamic_frame)
            row_frame.pack(fill=tk.X, pady=2)

            ttk.Label(row_frame, text=f"Dendro {i + 1} Name:").pack(side=tk.LEFT)
            name_entry = ttk.Entry(row_frame, width=15)
            name_entry.pack(side=tk.LEFT, padx=5)
            name_entry.insert(0, f"dendro_{i + 1}")
            self.name_entries.append(name_entry)

            ttk.Label(row_frame, text="Excite Pin:").pack(side=tk.LEFT, padx=(10, 0))
            excite_entry = ttk.Entry(row_frame, width=8)
            excite_entry.pack(side=tk.LEFT, padx=5)
            excite_entry.insert(0, str(6 + i))
            self.excite_entries.append(excite_entry)

    def validate(self):
        try:
            address = int(self.address_entry.get().strip())

            timestep = int(self.timestep_entry.get())
            if timestep <= 0:
                raise ValueError("Timestep must be positive")

            excite_pins = []
            for entry in self.excite_entries:
                excite_pins.append(int(entry.get()))

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
                    "names": names,
                },
                "timestep": timestep,
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

        # Disable Pin
        ttk.Label(main_frame, text="Disable Pin:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.enab_entry = ttk.Entry(main_frame, width=10)
        self.enab_entry.grid(row=3, column=1, sticky=tk.W, pady=2)
        self.enab_entry.insert(0, "9")

        # Timestep
        ttk.Label(main_frame, text="Timestep (seconds):").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.timestep_entry = ttk.Entry(main_frame, width=10)
        self.timestep_entry.grid(row=4, column=1, sticky=tk.W, pady=2)
        self.timestep_entry.insert(0, "10")

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="OK", command=self.ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.cancel).pack(side=tk.LEFT, padx=5)

    def validate(self):
        try:
            number = int(self.number_spinbox.get())
            if not 0 <= number <= 8:
                raise ValueError("Number must be between 0 and 8")

            ctrl_pins = [int(entry.get()) for entry in self.ctrl_entries]
            meas_pin = int(self.meas_entry.get())
            disab_Pin = int(self.enab_entry.get())

            timestep = int(self.timestep_entry.get())
            if timestep <= 0:
                raise ValueError("Timestep must be positive")

            self.result = {
                "type": "CS616",
                "params": {
                    "number": number,
                    "ctrlPins": ctrl_pins,
                    "measPin": meas_pin,
                    "disabPin": disab_Pin,
                },
                "timestep": timestep,
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

            params = {"name": name}
            params["I2C"] = self.i2c_var.get()

            self.result = {"type": "SHT45", "params": params, "timestep": timestep}
            return True

        except ValueError as e:
            messagebox.showerror("Validation Error", f"Invalid input: {e}")
            return False


# =============================================================================
# Config generator window (opened as Toplevel from the main GUI)
# =============================================================================


class DataloggerConfigApp:
    """Configuration editor window for building datalogger JSON files.

    Can operate either as a standalone root window or as a Toplevel
    opened from the main management GUI.
    """

    def __init__(self, parent):
        """parent: a tk.Tk or tk.Toplevel that will contain the widgets."""
        self.parent = parent
        self.parent.title("Datalogger JSON Configuration Generator")
        self.parent.geometry("900x700")

        self.sensors = []  # List to store sensor configurations

        self.create_widgets()

    # -----------------------------------------------------------------
    # Widget layout
    # -----------------------------------------------------------------
    def create_widgets(self):
        main_frame = ttk.Frame(self.parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ===== Device Information Section =====
        info_frame = ttk.LabelFrame(main_frame, text="Device Information", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(info_frame, text="Device Name:").grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        self.device_name_entry = ttk.Entry(info_frame, width=40)
        self.device_name_entry.grid(row=0, column=1, sticky=tk.W, pady=2, padx=5)

        ttk.Label(info_frame, text="Description:").grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        self.description_entry = ttk.Entry(info_frame, width=40)
        self.description_entry.grid(row=1, column=1, sticky=tk.W, pady=2, padx=5)

        ttk.Label(info_frame, text="Named Location:").grid(
            row=2, column=0, sticky=tk.W, pady=2
        )
        self.named_location_entry = ttk.Entry(info_frame, width=40)
        self.named_location_entry.grid(row=2, column=1, sticky=tk.W, pady=2, padx=5)

        ttk.Label(info_frame, text="Latitude:").grid(
            row=3, column=0, sticky=tk.W, pady=2
        )
        self.latitude_entry = ttk.Entry(info_frame, width=20)
        self.latitude_entry.grid(row=3, column=1, sticky=tk.W, pady=2, padx=5)
        self.latitude_entry.insert(0, "9999")

        ttk.Label(info_frame, text="Longitude:").grid(
            row=4, column=0, sticky=tk.W, pady=2
        )
        self.longitude_entry = ttk.Entry(info_frame, width=20)
        self.longitude_entry.grid(row=4, column=1, sticky=tk.W, pady=2, padx=5)
        self.longitude_entry.insert(0, "9999")

        # ===== Add Sensors Section =====
        sensor_btn_frame = ttk.LabelFrame(main_frame, text="Add Sensors", padding="10")
        sensor_btn_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(sensor_btn_frame, text="Add Dendrometer", command=self.add_dendro).pack(side=tk.LEFT, padx=5)
        ttk.Button(sensor_btn_frame, text="Add CS616", command=self.add_cs616).pack(side=tk.LEFT, padx=5)
        ttk.Button(sensor_btn_frame, text="Add SHT45", command=self.add_sht45).pack(side=tk.LEFT, padx=5)

        # ===== Sensors List Section =====
        list_frame = ttk.LabelFrame(main_frame, text="Configured Sensors", padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        columns = ("Type", "Details", "Timestep")
        self.sensor_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)

        self.sensor_tree.heading("Type", text="Type")
        self.sensor_tree.heading("Details", text="Details")
        self.sensor_tree.heading("Timestep", text="Timestep (s)")

        self.sensor_tree.column("Type", width=100)
        self.sensor_tree.column("Details", width=400)
        self.sensor_tree.column("Timestep", width=100)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.sensor_tree.yview)
        self.sensor_tree.configure(yscrollcommand=scrollbar.set)

        self.sensor_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Button(list_frame, text="Remove Selected", command=self.remove_sensor).pack(side=tk.BOTTOM, pady=5)

        # ===== Save / Load Section =====
        save_frame = ttk.Frame(main_frame)
        save_frame.pack(fill=tk.X)

        # Local file operations (right side)
        ttk.Button(save_frame, text="Save JSON", command=self.save_json).pack(side=tk.RIGHT, padx=5)
        ttk.Button(save_frame, text="Preview JSON", command=self.preview_json).pack(side=tk.RIGHT, padx=5)
        ttk.Button(save_frame, text="Load JSON", command=self.load_json).pack(side=tk.RIGHT, padx=5)

        # Device operations (left side)
        ttk.Button(save_frame, text="Save JSON to Device", command=self.save_json_to_device).pack(side=tk.LEFT, padx=5)
        ttk.Button(save_frame,text="Import JSON from Device",command=self.import_json_from_device,).pack(side=tk.LEFT, padx=5)

    # -----------------------------------------------------------------
    # Sensor add / remove helpers
    # -----------------------------------------------------------------
    def add_dendro(self):
        dialog = DendroDialog(self.parent)
        if dialog.result:
            self.sensors.append(dialog.result)
            self.update_sensor_list()

    def add_cs616(self):
        dialog = CS616Dialog(self.parent)
        if dialog.result:
            self.sensors.append(dialog.result)
            self.update_sensor_list()

    def add_sht45(self):
        dialog = SHT45Dialog(self.parent)
        if dialog.result:
            self.sensors.append(dialog.result)
            self.update_sensor_list()

    def update_sensor_list(self):
        for item in self.sensor_tree.get_children():
            self.sensor_tree.delete(item)

        for i, sensor in enumerate(self.sensors):
            sensor_type = sensor["type"]
            timestep = sensor["timestep"]
            params = sensor["params"]

            if sensor_type == "dendro":
                details = f"I2C:{params['I2C']}, Addr:{params['address']}, Names:{params['names']}"
            elif sensor_type == "CS616":
                details = (
                    f"Num:{params['number']}, CtrlPins:{params['ctrlPins']}, "
                    f"MeasPin:{params['measPin']}, DisabPin:{params['disabPin']}"
                )
            elif sensor_type == "SHT45":
                i2c = params.get("I2C", 0)
                details = f"I2C:{i2c}, Name:{params['name']}"
            else:
                details = str(params)

            self.sensor_tree.insert(
                "", tk.END, iid=str(i), values=(sensor_type, details, timestep)
            )

    def remove_sensor(self):
        selected = self.sensor_tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select a sensor to remove", parent=self.parent)
            return

        indices = sorted([int(s) for s in selected], reverse=True)
        for idx in indices:
            del self.sensors[idx]

        self.update_sensor_list()

    # -----------------------------------------------------------------
    # JSON build / preview / save / load (local file)
    # -----------------------------------------------------------------
    def build_json(self):
        """Build the JSON structure from current configuration."""
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
            "Cowbell": True,
            "latitude": latitude,
            "longitude": longitude,
            "named_location": self.named_location_entry.get().strip(),
            "device_name": self.device_name_entry.get().strip(),
            "description": self.description_entry.get().strip(),
            "sensors": [],
            "timesteps": [],
        }

        for sensor in self.sensors:
            sensor_entry = {"type": sensor["type"], "params": sensor["params"]}
            config["sensors"].append(sensor_entry)
            config["timesteps"].append(sensor["timestep"])

        return config

    def preview_json(self):
        """Show a preview of the JSON output."""
        config = self.build_json()
        json_str = json.dumps(config, indent=4)

        preview_win = tk.Toplevel(self.parent)
        preview_win.title("JSON Preview")
        preview_win.geometry("500x400")

        text = tk.Text(preview_win, wrap=tk.NONE)
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        y_scroll = ttk.Scrollbar(text, orient=tk.VERTICAL, command=text.yview)
        x_scroll = ttk.Scrollbar(text, orient=tk.HORIZONTAL, command=text.xview)
        text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        text.insert(tk.END, json_str)
        text.configure(state=tk.DISABLED)

    def save_json(self):
        """Save the configuration to a local JSON file."""
        config = self.build_json()

        default_name = self.device_name_entry.get().strip() or "datalogger_config"
        default_name = "".join(
            c if c.isalnum() or c in "._-" else "_" for c in default_name
        )

        filepath = filedialog.asksaveasfilename(
            parent=self.parent,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"{default_name}.json",
        )

        if filepath:
            try:
                with open(filepath, "w") as f:
                    json.dump(config, f, indent=4)
                messagebox.showinfo(
                    "Success",
                    f"Configuration saved to:\n{filepath}",
                    parent=self.parent,
                )
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Failed to save file:\n{e}", parent=self.parent
                )

    def load_json(self):
        """Load a configuration from a local JSON file."""
        filepath = filedialog.askopenfilename(
            parent=self.parent,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )

        if not filepath:
            return

        try:
            with open(filepath, "r") as f:
                config = json.load(f)
            self._apply_config(config)
            messagebox.showinfo(
                "Success", "Configuration loaded successfully", parent=self.parent
            )
        except Exception as e:
            messagebox.showerror(
                "Error", f"Failed to load file:\n{e}", parent=self.parent
            )

    # -----------------------------------------------------------------
    # Device operations (mpremote)
    # -----------------------------------------------------------------
    def save_json_to_device(self):
        """Write current config to a temp file then copy it to the device as info.json."""
        config = self.build_json()
        tmp_path = os.path.join(tempfile.gettempdir(), "tmp_config.json")

        try:
            with open(tmp_path, "w") as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            messagebox.showerror(
                "Error", f"Failed to write temporary file:\n{e}", parent=self.parent
            )
            return

        try:
            result = run_mpremote(f"cp {tmp_path} :info.json", timeout=15)
            print(result.stdout, result.stderr)

            if device_not_found(result):
                messagebox.showerror("Error", "No device found.", parent=self.parent)
            elif result.returncode == 0:
                messagebox.showinfo("Success","Configuration saved to device as info.json",parent=self.parent)
            else:
                messagebox.showerror("Error",result.stderr.strip() or result.stdout.strip(),parent=self.parent)
        except subprocess.TimeoutExpired:
            messagebox.showerror("Error", "Timeout while communicating with device.", parent=self.parent)
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def import_json_from_device(self):
        """Copy info.json from the device to a temp file, then load it into the editor."""
        tmp_path = os.path.join(tempfile.gettempdir(), "tmp_config.json")

        try:
            result = run_mpremote(f"cp :info.json {tmp_path}", timeout=15)
            print(result.stdout, result.stderr)

            if device_not_found(result):
                messagebox.showerror("Error", "No device found.", parent=self.parent)
                return
            if result.returncode != 0:
                messagebox.showerror("Error",result.stderr.strip() or result.stdout.strip(),parent=self.parent)
                return
        except subprocess.TimeoutExpired:
            messagebox.showerror("Error", "Timeout while communicating with device.", parent=self.parent)
            return

        try:
            with open(tmp_path, "r") as f:
                config = json.load(f)
            self._apply_config(config)
            messagebox.showinfo("Success", "Configuration imported from device", parent=self.parent)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read config from device:\n{e}", parent=self.parent)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # -----------------------------------------------------------------
    # Internal helper to populate the GUI from a config dict
    # -----------------------------------------------------------------
    def _apply_config(self, config: dict):
        """Populate all fields from a configuration dictionary."""
        self.sensors.clear()

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

        sensors_list = config.get("sensors", [])
        timesteps_list = config.get("timesteps", [])

        for i, sensor_data in enumerate(sensors_list):
            timestep = timesteps_list[i] if i < len(timesteps_list) else 10
            sensor = {
                "type": sensor_data["type"],
                "params": sensor_data["params"],
                "timestep": timestep,
            }
            self.sensors.append(sensor)

        self.update_sensor_list()


# =============================================================================
# Main management GUI functions
# =============================================================================


def update_computer_time():
    """Update the computer time display."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    computer_time_label.config(text=f"Computer Time:\n{current_time}")
    root.after(1000, update_computer_time)


def soft_reset_device():
    result = subprocess.run(
        "python -m mpremote soft-reset",
        capture_output=True,
        text=True,
        timeout=10,
        shell=True,
    )
    if ("no device found" in result.stdout) or ("no device found" in result.stderr):
        print("No device found")
        root.after(1000, soft_reset_device)
    else:
        print(result.stdout)
        print(result.stderr)
        result = subprocess.run(
            "python -m mpremote reset",
            capture_output=True,
            text=True,
            timeout=10,
            shell=True,
        )

        result = subprocess.run(
            "python -m mpremote soft-reset",
            capture_output=True,
            text=True,
            timeout=10,
            shell=True,
        )
        print("Device soft reset ready to work")


def get_device_time():
    """Get and display the time from the device."""
    result = subprocess.run(
        "python -m mpremote run read_rtc_time.py",
        capture_output=True,
        text=True,
        timeout=10,
        shell=True,
    )

    if ("no device found" in result.stdout) or ("no device found" in result.stderr):
        device_time_output.config(text="Device Time:\nNo device found")
    elif result.returncode == 0:
        numbers = re.findall(r"\d+", result.stdout.strip())

        if len(numbers) >= 3:
            seconds = int(numbers[-1])
            minutes = int(numbers[-2])
            hours = int(numbers[-3])
            formatted_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            device_time_output.config(text=f"Device Time:\n{formatted_time}")
        else:
            device_time_output.config(text=f"Device Time:\n{result.stdout.strip()}")
    else:
        device_time_output.config(text=f"Device Time:\n{result.stdout.strip()}")


def get_battery_voltage():
    """Get and display the battery voltage from the device."""
    result = subprocess.run(
        "python -m mpremote run read_batt_volt.py",
        capture_output=True,
        text=True,
        timeout=10,
        shell=True,
    )
    if ("no device found" in result.stdout) or ("no device found" in result.stderr):
        batt_volt_output.config(text="Battery voltage:\nNo device found")
    elif result.returncode == 0:
        match = re.search(r'-?\d+\.?\d*', result.stdout.strip())
        number = float(match.group())
        batt_volt_output.config(text=f"Battery voltage:\n{number:.2f} V")
    else:
        batt_volt_output.config(text=f"Battery voltage:\n{result.stdout.strip()}")


def get_sd_files():
    """Get list of files on the device SD card."""
    result = subprocess.run(
        "python -m mpremote connect auto run read_sd.py fs ls sd/",
        capture_output=True,
        text=True,
        timeout=15,
        shell=True,
    )
    if ("no device found" in result.stdout) or ("no device found" in result.stderr):
        sd_files_listbox.delete(0, tk.END)
        sd_files_listbox.insert(0, "No device found")
        download_btn.config(state="disabled")
    elif result.returncode == 0:
        files = []
        lines = result.stdout.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("ls :") and line != ":sd/":
                if line.startswith("sd/"):
                    line = line[3:]
                files.append(line)

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
        print(result.stderr)


def download_selected_files():
    """Download selected files from device SD card."""
    selected_indices = sd_files_listbox.curselection()

    if not selected_indices:
        messagebox.showwarning(
            "No Selection", "Please select one or more files to download."
        )
        return

    data_dir = filedialog.askdirectory(title="Select download destination folder")
    if not data_dir:
        return  # User cancelled

    downloaded_files = []
    failed_files = []

    for index in selected_indices:
        filename = sd_files_listbox.get(index)

        if filename in [
            "No device found",
            "No files found on SD card",
            "Error reading SD card",
        ]:
            continue
        # Strip leading file size (number) — robust even with spaces in filenames
        match = re.match(r'^\d+\s+(.+)$', filename)
        if match:
            filename = match.group(1)
        src = f":sd/{filename}"
        dst = str(Path(data_dir) / filename)
        print(src,dst)
        try:
            result = subprocess.run(
                ["python","-m","mpremote","run","read_sd.py","cp",src, dst],
                capture_output=True,
                text=True,
                timeout=30,
            )


            if result.returncode == 0:
                downloaded_files.append(filename)
            else:
                failed_files.append(f"{filename}: {result.stdout.strip()}")

        except Exception as e:
            print(e)
            failed_files.append(f"{filename}: {str(e)}")

    if downloaded_files and not failed_files:
        messagebox.showinfo("Download Complete",f"Successfully downloaded {len(downloaded_files)} file(s) to:\n{data_dir}\n\n"+ "\n".join(downloaded_files))
    elif downloaded_files and failed_files:
        messagebox.showwarning(
            "Partial Download",
            f"Downloaded {len(downloaded_files)} file(s):\n"
            + "\n".join(downloaded_files)
            + f"\n\nFailed {len(failed_files)} file(s):\n"
            + "\n".join(failed_files),
        )
    elif failed_files:
        messagebox.showerror("Download Failed",f"Failed to download {len(failed_files)} file(s):\n"+ "\n".join(failed_files))


def set_device_time():
    """Set the time on the device."""
    result1 = subprocess.run(
        "python -m mpremote rtc --set",
        capture_output=True,
        text=True,
        timeout=10,
        shell=True,
    )

    if ("no device found" in result1.stdout) or ("no device found" in result1.stderr):
        set_time_output.config(text="Set Time Result:\nNo device found")
        return
    elif result1.returncode != 0:
        set_time_output.config(text=f"Set Time Result:\n{result1.stdout.strip()}")
        return

    result2 = subprocess.run(
        "python -m mpremote run set_rtc_time.py",
        capture_output=True,
        text=True,
        timeout=10,
        shell=True,
    )

    if ("no device found" in result2.stdout) or ("no device found" in result2.stderr):
        set_time_output.config(text="Set Time Result:\nNo device found")
    elif result2.returncode == 0:
        set_time_output.config(text="Set Time Result:\nDevice time was set")
    else:
        set_time_output.config(text=f"Set Time Result:\n{result2.stdout.strip()}")


def check_device_connection():
    """Check if a device is connected using mpremote."""
    result = subprocess.run(
        'python -m mpremote exec "print("connected")"',
        capture_output=True,
        text=True,
        timeout=5,
        shell=True,
    )
    if ("no device found" in result.stdout) or ("no device found" in result.stderr):
        return False
    return result.returncode == 0 and "connected" in result.stdout


def init_new_device():
    """This is to make a new datalogger."""
    path_files = list_files(get_relative_path("../micropython/libraries"))
    for filepath in path_files:
        filename = get_filename(filepath)
        result = subprocess.run(
            "python -m mpremote cp " + filepath + " :" + filename,
            capture_output=True,
            text=True,
            timeout=5,
            shell=True,
        )
        print(result.stdout, result.stderr)
    path_datalogger = get_relative_path("../micropython/datalogger_class.py")
    filename_datalogger = "datalogger_class.py"
    path_sensor = get_relative_path("../micropython/sensor_class.py")
    filename_sensor = "sensor_class.py"
    path_main = get_relative_path("../micropython/main.py")
    filename_main = "main.py"
    result = subprocess.run(
        "python -m mpremote cp " + path_datalogger + " :" + filename_datalogger,
        capture_output=True,
        text=True,
        timeout=5,
        shell=True,
    )
    print(result.stdout, result.stderr)
    result = subprocess.run(
        "python -m mpremote cp " + path_sensor + " :" + filename_sensor,
        capture_output=True,
        text=True,
        timeout=5,
        shell=True,
    )
    result = subprocess.run(
        "python -m mpremote cp " + path_main + " :" + filename_main,
        capture_output=True,
        text=True,
        timeout=5,
        shell=True,
    )
    print(result.stdout, result.stderr)

    return


def upload_file_to_device():
    """Open a file dialog and upload the selected file to the device root using mpremote."""
    filepath = filedialog.askopenfilename(title="Select file to upload")
    if not filepath:
        return  # User cancelled
    filename = get_filename(filepath)
    result = subprocess.run(
        "python -m mpremote cp " + filepath + " :" + filename,
        capture_output=True,
        text=True,
        timeout=15,
        shell=True,
    )
    print(result.stdout, result.stderr)
    if ("no device found" in result.stdout) or ("no device found" in result.stderr):
        messagebox.showerror("Upload Failed", "No device found.")
    elif result.returncode == 0:
        messagebox.showinfo("Upload Complete", f"'{filename}' uploaded successfully.")
    else:
        messagebox.showerror(
            "Upload Failed", result.stderr.strip() or result.stdout.strip()
        )


def open_config_generator():
    """Open the configuration generator in a new Toplevel window."""
    config_window = tk.Toplevel(root)
    DataloggerConfigApp(config_window)


# =============================================================================
# Build the main window
# =============================================================================

root = tk.Tk()
root.title("Datalogger management tool")
root.geometry("700x650")

style = ttk.Style()
style.theme_use('clam')
style.configure('TButton', font=('Helvetica', 12,'bold'), foreground = "dark green",padding = 7.5, background = "light yellow")
style.configure('TLabel', font=('Helvetica', 12),relief = "sunken", padding = 5, background = "white")

# Critical — tell the parent columns to stretch:
root.columnconfigure(0, weight=1)
root.columnconfigure(2, weight=1)

right_side = tk.Frame(root)
left_side = tk.Frame(root)

left_side.grid(row=0, column=0, sticky="nsew")
right_side.grid(row=0, column=2, sticky="nsew")

# --- LEFT SIDE — Time Management Section ---

computer_time_label = ttk.Label(left_side,text="Computer Time:\nLoading...", justify="center", anchor = 'center')
computer_time_label.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

get_time_btn = ttk.Button(left_side,text="Get datalogger time",command=get_device_time)
get_time_btn.grid(row=1, column=0, padx=10, pady=5, sticky = "ew")

device_time_output = ttk.Label(left_side,text="Device Time:\nClick button to check",justify="center", anchor = 'center')
device_time_output.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

set_time_btn = ttk.Button(left_side,text="Set datalogger time",command=set_device_time)
set_time_btn.grid(row=3, column=0, padx=10, pady=5, sticky="ew")

set_time_output = ttk.Label(left_side,text="Set Time Result:\nClick button to set time",justify="center", anchor = 'center')
set_time_output.grid(row=4, column=0, padx=10, pady=5, sticky="ew")

separator = ttk.Separator(left_side, orient="horizontal")
separator.grid(row=5, column=0, sticky="ew", pady=10)

get_batt_volt_btn = ttk.Button(left_side,text="Get Battery voltage",command=get_battery_voltage)
get_batt_volt_btn.grid(row=6, column=0, padx=10, pady=15, sticky="ew")

batt_volt_output = ttk.Label(left_side,text="Battery voltage:\nClick button to check",justify="center", anchor = 'center')
batt_volt_output.grid(row=7, column=0, padx=10, pady=5, sticky="ew")

separator = ttk.Separator(left_side, orient="horizontal")
separator.grid(row=8, column=0, sticky="ew", pady=10)

init_datalogger_btn = ttk.Button(left_side,text="Install new datalogger", command=init_new_device)
init_datalogger_btn.grid(row=9, column=0, padx=10, pady=15, sticky="ew")

upload_file_btn = ttk.Button(left_side,text="Upload file to device",command=upload_file_to_device)
upload_file_btn.grid(row=10, column=0, padx=10, pady=5, sticky="ew")

# Config generator button
separator = ttk.Separator(left_side, orient="horizontal")
separator.grid(row=11, column=0, sticky="ew", pady=10)

config_gen_btn = ttk.Button(left_side, text="Config Generator",command=open_config_generator)
config_gen_btn.grid(row=12, column=0, padx=10, pady=5, sticky="ew")

# Vertical separator between left and right panels
separator = tk.Frame(root, width=2, bg="gray")
separator.grid(row=0, column=1, rowspan=15, sticky="ns", padx=2)

# --- RIGHT SIDE — SD Card File Management Section ---

tk.Label(right_side, text="SD Card Files", font=("Arial", 15, "bold")).grid(row=1, column=0, padx=1, pady=(15, 5))

get_files_btn = ttk.Button(right_side,text="Get SD Card Files",command=get_sd_files)
get_files_btn.grid(row=2, column=0, padx=5, pady=5, sticky="ew")

sd_files_listbox = tk.Listbox(right_side, height=30, width=50, selectmode=tk.MULTIPLE, font=("Arial", 8))
sd_files_listbox.grid(row=3, column=0, padx=5, pady=5, sticky="ew")
sd_files_listbox.insert(0, "Click 'Get SD Card Files' to load")

scrollbar = tk.Scrollbar(right_side, orient="vertical")
scrollbar.grid(row=3, column=1, sticky="ns", pady=5)
sd_files_listbox.config(yscrollcommand=scrollbar.set)
scrollbar.config(command=sd_files_listbox.yview)

download_btn = ttk.Button(
    right_side,
    text="Download Selected Files",
    command=download_selected_files,
    state="disabled",
)
download_btn.grid(row=4, column=0, padx=10, pady=5, sticky="ew")

left_side.grid_columnconfigure(0, weight=1)
right_side.grid_columnconfigure(0, weight=1)
right_side.grid_columnconfigure(1, weight=0)

# Start updating computer time
update_computer_time()

# Execute until a device is there to soft reset
soft_reset_device()

# Start the GUI event loop
root.mainloop()
