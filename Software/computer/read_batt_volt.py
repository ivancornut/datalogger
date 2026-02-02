from machine import Pin, PWM, Timer,I2C,lightsleep,WDT, idle, ADC,SPI, ADC

battery_pin = ADC(26)
voltage_drop_factor = 1/(22/(68+22))

sensor_value = 0
for i in range(0,10):
    sensor_value = sensor_value + battery_pin.read_u16()/10
battery_voltage = sensor_value * (3.3 / 65535) * voltage_drop_factor
print(battery_voltage)