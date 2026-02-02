import time
import urtc
from machine import I2C, Pin

# set the I2C of the clock on pins 5 and 4 of the cowbell datalogger from adafruit
i2c_clock = I2C(0,scl=Pin(5), sda=Pin(4))
rtc = urtc.PCF8523(i2c_clock)

datetime = rtc.datetime() # read the datetime from the RTC of the cowbell datalogger shield
print("Year: ",datetime.year, ", Month: ",datetime.month, ", Day: ",datetime.day, ", Hour: ",datetime.hour, ", Minute: ",datetime.minute, ", Seconds: ",datetime.second)
