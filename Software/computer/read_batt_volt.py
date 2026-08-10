from machine import Pin, PWM, Timer,I2C,lightsleep,WDT, idle, ADC,SPI, ADC
import json

battery_pin = ADC(26)

with open('info.json','r') as f:
    config = json.load(f)
    if "batt_R1" in config:
        batt_r1 = float(config["batt_R1"])
        batt_r2 = float(config["batt_R2"])
    else:
        batt_r1 = 22
        batt_r2 = 68

voltage_drop_factor = 1/(batt_r1/(batt_r2+batt_r1))

sensor_value = 0
for i in range(0,10):
    sensor_value = sensor_value + battery_pin.read_u16()/10
battery_voltage = sensor_value * (3.3 / 65535) * voltage_drop_factor
print(battery_voltage)