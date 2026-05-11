from machine import Pin, PWM, Timer,I2C,lightsleep,WDT, idle, ADC,SPI, reset, deepsleep
from time import sleep
import sensor_class
import json
import urtc
import sdcard
import vfs
import os

class datalogger:
    """ A datalogger class to be used with any sensors
    that use a compatible sensor class """
    def __init__(self):
        
        ### Initial wait and led indication ###
        self.led = Pin(25, Pin.OUT) # internal led of the Pi Pico
        self.led.value(0)
        
        self.testing = False
        self.i2c_0_used = False # This is to know whether to initialise the I2C ports
        self.i2c_1_used = False # This is to know whether to initialise the I2C ports
        
        try:
            with open('info.json','r') as f:
                config = json.load(f)
            self.file_prefix = config["device_name"]
            self.sensors = config["sensors"]
            self.timesteps = config["timesteps"]
            self.cowbell = config["Cowbell"]
        except Exception as e:
            print(e)
            with open('logs.txt','a') as f:
                f.write("Error reading info json:")
                f.write(str(e))
                f.write("\n")
            self.blink_status("no_info_file")
            deepsleep(30*60*1000)
        
        self.battery_pin = ADC(26)
        self.voltage_drop_factor = 1/(22/(68+22))
        
        self.temp_sensor = ADC(4)
        
        self.battery_voltage = 12 # dummy to start
        
        self.usb_pin = Pin(24, Pin.IN) # identifies if Pi Pico is plugged into a computer
        
        self.column_names = ["Battery_voltage","internal_temperature"] # initialise column names
        
        # create the sensor objects
        self.sensor_objs = []
        print(self.sensors)
        for s in self.sensors:
            self.sensor_objs.append(self.create_sensor(s))
        
        # the sensor objects will output the corresponding columns
        for sensor in self.sensor_objs:
            self.column_names = self.column_names + sensor.column_names
        
        # check if the dafruit cowbell datalogger module is attached
        if self.cowbell:
            try:
                 # set up SD card if necessary, adapted for the Pi cowbell datalogger
                cs = Pin(17,Pin.OUT)
                spi = SPI(0, baudrate=1000000,polarity=0,phase=0,bits=8,
                                  firstbit=SPI.MSB,sck=Pin(18),mosi=Pin(19),miso=Pin(16))
                self.sd = sdcard.SDCard(spi, cs)
                self.filsys = vfs.VfsFat(self.sd)
                # The RTC for the cowbell datalogger board
                self.i2c_clock = I2C(0,scl=Pin(5), sda=Pin(4))
                self.rtc = urtc.PCF8523(self.i2c_clock)
                self.i2c_0_used = True
            except Exception as e:
                print(e)
                with open('logs.txt','a') as f:
                    f.write("Error connecting cowbell:")
                    f.write(str(e))
                    f.write("\n")
        
        # check if all timesteps are equal:
        val = self.timesteps[0]
        self.is_timer = False
        self.different_timesteps = len(set(self.timesteps)) > 1
        self.multi_files = self.different_timesteps
        if len(set(self.timesteps)) > 1:
            raise NotImplementedError("Mixed timesteps not yet supported")
        
        if self.different_timesteps:
            # this is experimental does not work for now
            # Here we see if we need timers or rather to use the RTC for time intervall
            self.timers = []
            self.sensors_with_timers = []
            self.mini_timestep = 9999
            for i in timesteps:
                if i<60:
                    self.timers.append(Timer())
                    self.sensors_with_timers.append(sensor_nb)
                    self.is_timer=True
                else:
                    # mini timestep is the smallest timestep of the series
                    self.mini_timestep = min(i,self.mini_timestep) 
                sensor_nb = sensor_nb + 1
        else:
            if val<60:
                # this is experimental does not work for now
                self.interval = val
                self.unique_timer = Timer()
                self.is_timer = True
            else:
                self.interval = val
        
        if self.usb_pin():
            self.blink_status("USB_conn")
            sleep(8) # time for the reset before setting the watchdog
        else:
            self.blink_status("start_ok")
            
        ### Watchdog ###
        """ The watchdog will reset the device if execution stops for whatever reason
        this is useful since bugs or unexpected errors can happen """
        self.watchdog = WDT(timeout=8000)
    
    def blink_status(self, status):
        if status=="start_ok":
            for i in range(0,7):
                sleep(1)
                self.led.toggle()
                sleep(0.3)
                self.led.value(0)
        elif status=="no_info_file":
            for i in range(0,15):
                sleep(0.3)
                self.led.toggle()
                sleep(0.3)
                self.led.value(0)
        elif status=="USB_conn":
            for i in range(0,2):
                sleep(1)
                self.led.toggle()
                sleep(0.3)
                self.led.value(0)
        else:
            return False
    
    def read_battery_voltage(self):
        sensor_value = 0
        for i in range(0,10):
            sensor_value = sensor_value + self.battery_pin.read_u16()/10
        self.battery_voltage = sensor_value * (3.3 / 65535) * self.voltage_drop_factor
    
    def read_internal_temperature(self):
        adc_value = self.temp_sensor.read_u16()
        voltage = adc_value * (3.3 / 65535.0)
        self.internal_temp = 27 - (voltage - 0.706) / 0.001721
        
    def create_sensor(self,sensor):
        # This function initialises the different sensors
        sensor_name = sensor["type"]
        
        # !!! Campbell CS616 soil humidity probes !!!
        if sensor_name == "CS616": 
            p = sensor["params"]
            return sensor_class.TDR_CS616(nb_cs616=p["number"], meas_pin=p["measPin"],ctrl_pins = p["ctrlPins"], disable_pin = p["disabPin"])
            
        # !!! Fine Open dendros on ADS1115 !!!
        elif sensor_name == "dendro": 
            p = sensor["params"]
            if p["I2C"] == 0:
                if not self.i2c_0_used:
                    self.I2C_0_obj = I2C(0, sda=Pin(4), scl=Pin(5))
                    self.i2c_0_used = True
                return sensor_class.dendrometer(self.I2C_0_obj,on_pins=p["excite"],nb_dendros=p["number"],addr=p["address"], names=p["names"])
            elif p["I2C"] == 1: 
                if not self.i2c_1_used:
                    self.I2C_1_obj = I2C(1, sda=Pin(2), scl=Pin(3))
                    self.i2c_1_used = True
                return sensor_class.dendrometer(self.I2C_1_obj,on_pins=p["excite"],nb_dendros=p["number"],addr=p["address"], names=p["names"])
              
        # !!! SHT45 !!!
        elif sensor_name == "SHT45":
            p = sensor["params"]
            if p["I2C"] == 0:
                if not self.i2c_0_used:
                    self.I2C_0_obj = I2C(0, sda=Pin(4), scl=Pin(5))
                    self.i2c_0_used = True
                return sensor_class.temp_hum_sht45(self.I2C_0_obj, name = p["name"])
            elif p["I2C"] == 1:
                if not self.i2c_1_used:
                    self.I2C_1_obj = I2C(1, sda=Pin(2), scl=Pin(3))
                    self.i2c_1_used = True
                return  sensor_class.temp_hum_sht45(self.I2C_1_obj, name = p["name"])
        
        # !!! DS18B20 !!!    
        elif sensor_name == "temp_sensor":
            p = sensor["params"]
            return sensor_class.temp_DS18B20(meas_pin=p[0],roms = p[1])
            
    
    def _write_file(self,sensor_values,test = False):
        # read the diagnostics
        self.read_battery_voltage()
        self.read_internal_temperature()
        
        vfs.mount(self.filsys, "/sd") # mount the SD card
        if self.multi_files:
            return None
        else:
            now = self.rtc.datetime() # check date
            local_filename = self.file_prefix+'_'+str(now.year)+"-"+str(now.month)+"-"+str(now.day)+".csv"
            if test:
                self.filename = "test.csv"
            else:
                self.filename = "/sd/"+local_filename
            if not local_filename in os.listdir('/sd'):
                # create the header of the file
                with open(self.filename,'a') as f:
                    f.write("DateTime")
                    for i in self.column_names:
                        f.write(",")
                        f.write(i)
                    f.write("\n")    
            with open(self.filename,'a') as f:
                # append the file with the newline of data
                f.write(f"{now.year:04d}-{now.month:02d}-{now.day:02d}T{now.hour:02d}:{now.minute:02d}:{now.second:02d}")
                f.write(",")
                f.write(f"%1.2f" % self.battery_voltage)
                f.write(",")
                f.write(f"%1.1f" % self.internal_temp)
                for sv in sensor_values:
                    for v in sv:
                        f.write(",")
                        f.write("%1.4f" % v)
                f.write("\n")
            vfs.umount("/sd") # unmount the SD card
            self.watchdog.feed()
    
    def _display_batt(self):
        if self.battery_voltage > 12.7:
            self.led.value(1)
            sleep(0.03)
            self.led.value(0)
            sleep(0.1)
            self.led.value(1)
            sleep(0.03)
            self.led.value(0)
            sleep(0.1)
            self.led.value(1)
            sleep(0.03)
            self.led.value(0)
        elif self.battery_voltage <= 12.7 and self.battery_voltage > 12.5:
            self.led.value(1)
            sleep(0.03)
            self.led.value(0)
            sleep(0.1)
            self.led.value(1)
            sleep(0.03)
            self.led.value(0)
        elif self.battery_voltage <= 12.5:
            self.led.value(1)
            sleep(0.03)
            self.led.value(0)
        else:
            self.led.value(1)
            sleep(0.5)
            self.led.value(0)
        self.led.value(0)
    
    def _run_interval(self):
        """ This function is for sensors with measurement intervalls of
        more than a minute """
        self.interval_minutes = self.interval // 60
        while True:
            now = self.rtc.datetime() # check the datetime
            if self.usb_pin():
                self.read_internal_temperature()
                # if connected to usb do not sleep
                # and instead read sensors every 4s
                print(self.sensor_objs)
                for sensor in self.sensor_objs:
                    sensor.read_values(self.watchdog, self.led, debug = True)
                    self.watchdog.feed()
                print(f"Internal temp: %1.1f" % self.internal_temp)
                sleep(4)
            else:
                if (now.hour==0 and now.minute ==0):
                    # this is to reset the datalogger once a day.
                    if (now.minute%self.interval_minutes) == 0: # check whether it is time to log
                        values = []
                        for sensor in self.sensor_objs:
                            values.append(sensor.read_values(self.watchdog,self.led))
                            self.watchdog.feed()
                        self._write_file(values)
                    reset()
                if (now.minute%self.interval_minutes) == 0: # check whether it is time to log
                    values = []
                    for sensor in self.sensor_objs:
                        values.append(sensor.read_values(self.watchdog,self.led))
                        self.watchdog.feed()
                    self._write_file(values)
                    
                    # Then sleep to keep energy
                    for i in range(0,9*self.interval_minutes):
                        lightsleep(5750)
                        self.watchdog.feed()
                        #self._display_batt()
                        self.led.value(1)
                        sleep(0.03)
                        self.led.value(0)
                else:
                    for i in range(0,5):
                        lightsleep(5750)
                        self.watchdog.feed()
                        #self._display_batt()
                        self.led.value(1)
                        sleep(0.03)
                        self.led.value(0)
                    
    def _run_test(self):
        while True:
            values = []
            for sensor in self.sensor_objs:
                values.append(sensor.read_values(self.watchdog,self.led))
                self.watchdog.feed()
            self._write_file(values, test = True)
            sleep(5)
            
    def _run_timers(self):
        return None
     
    def run(self):
        if self.testing:
            self._run_test()
        else:
            if self.is_timer:
                self._run_timers()
            else:
                self._run_interval()
        
