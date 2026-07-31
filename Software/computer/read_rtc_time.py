import time
from ds3231 import DS3231
from machine import I2C, Pin

# set the I2C of the clock on pins 5 and 4 of the cowbell datalogger from adafruit
i2c_clock = I2C(0,scl=Pin(5), sda=Pin(4))
#rtc = urtc.PCF8523(i2c_clock)
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
