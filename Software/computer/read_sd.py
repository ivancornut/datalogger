import vfs
import sdcard
import time
from machine import SPI, Pin

# Setup SPI for the SD card on the Adafruit Pi Cowbell datalogging shield
cs = Pin(17,Pin.OUT)

spi = machine.SPI(0,
                  baudrate=1000000,
                  polarity=0,
                  phase=0,
                  bits=8,
                  firstbit=machine.SPI.MSB,
                  sck=Pin(18),
                  mosi=Pin(19),
                  miso=Pin(16))

sd = sdcard.SDCard(spi, cs)
# we use the now standard (as of the latest micropython version) vfs library 
filsys = vfs.VfsFat(sd)

vfs.mount(filsys, "/sd") # mount the SD to make it readable by the connected computer
