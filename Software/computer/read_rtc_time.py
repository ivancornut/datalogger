import time
from ds3231 import DS3231
from machine import I2C, Pin
import urtc
import json

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
    datetime = rtc.datetime() # read the datetime from the RTC of the cowbell datalogger shield
    year = datetime[0]
    month = datetime[1]
    day = datetime[2]
    hour = datetime[4]
    minute = datetime[5]
    second = datetime[6]
    print("Year: ",year, ", Month: ",month, ", Day: ",day, ", Hour: ",hour, ", Minute: ",minute, ", Seconds: ",second)
else:
    rtc = urtc.PCF8523(i2c_clock)
    datetime = rtc.datetime() # read the datetime from the RTC of the cowbell datalogger shield
    print("Year: ",datetime.year, ", Month: ",datetime.month, ", Day: ",datetime.day, ", Hour: ",datetime.hour, ", Minute: ",datetime.minute, ", Seconds: ",datetime.second)
    

