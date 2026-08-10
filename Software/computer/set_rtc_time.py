import time
from ds3231 import DS3231
from machine import I2C, Pin
import json
import urtc

# set the I2C of the clock on pins 5 and 4 of the cowbell datalogger from adafruit
i2c_clock = I2C(0,scl=Pin(5), sda=Pin(4))

with open('info.json','r') as f:
    config = json.load(f)
if "rtc_type" in config: # to account for older versions of datalogger using the adafruit shield
    rtc_type = config["rtc_type"]
else:
    rtc_type = "Adafruit"
    
if rtc_type == "DS3232":
    rtc = DS3231(i2c_clock) # for time
    rtc.output_32kHz(False)
    # read the datetime from the processor (which we set using mpremote)
    dt = time.localtime() 
    year=dt[0]
    month=dt[1]
    day=dt[2]
    hour = dt[3]
    minute = dt[4]
    second = dt[5]
    # set the DS3231
    datetime = (year, month, day, hour, minute, second)
    rtc.datetime(datetime)
else:
    rtc = urtc.PCF8523(i2c_clock)
    # read the datetime from the processor (which we set using mpremote)
    dt = time.localtime() 
    # set the Adafruit Pi cowbell datalogging shield urtc clock using the datetime from processor
    datetime = urtc.datetime_tuple(year=dt[0], month=dt[1], day=dt[2], hour = dt[3], minute = dt[4], second = dt[5])
    rtc.datetime(datetime)
    