import time
import urtc
from machine import I2C, Pin

# set the I2C of the clock on pins 5 and 4 of the cowbell datalogger from adafruit
i2c_clock = I2C(0,scl=Pin(5), sda=Pin(4))
rtc = urtc.PCF8523(i2c_clock)
# read the datetime from the processor (which we set using mpremote)
dt = time.localtime() 
# set the Adafruit Pi cowbell datalogging shield urtc clock using the datetime from processor
datetime = urtc.datetime_tuple(year=dt[0], month=dt[1], day=dt[2], hour = dt[3], minute = dt[4], second = dt[5])
rtc.datetime(datetime)

