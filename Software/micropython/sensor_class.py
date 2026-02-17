from time import  sleep_ms, sleep, ticks_us, ticks_ms, ticks_diff
import math
from machine import Pin

import CD4051
from counter import PWMCounter
import onewire, ds18x20
from micropython_sht4x import sht4x
import ads1x15

def standard_deviation_calc(ind_val_array):
    sample_mean = 0
    for i in ind_val_array:
        sample_mean = sample_mean + i/len(ind_val_array)
    sum_diffs = 0
    for i in ind_val_array:
        sum_diffs = sum_diffs + math.pow(i-sample_mean,2)
    variance = sum_diffs/len(ind_val_array)
    standard_deviation = math.sqrt(variance)

    return standard_deviation

def rerun_meas_loop(std,sample_mean,criteria):
    var_pct = std/sample_mean * 100
    print(var_pct)
    if var_pct > criteria:
        return True
    else:
        return False

class temp_DS18B20:
    def __init__(self,meas_pin=12,roms={7: bytearray(b'(\xac`TB \x01\x19'), 6 : bytearray(b'(*n\xf1B \x01\xcb')}):
        self.dat_pin = machine.Pin(meas_pin)
        ds18x20.DS18X20(onewire.OneWire(self.dat_pin))
        self.roms = roms # a dictionnary with sensor number and roms
        self.column_names = []
        for key, value in self.roms.items():
            self.column_names.append("Temp_"+str(key))
    def read_values(self,watchdog,internal_led, debug = False):
        data_values = []
        self.ds.convert_temp()
        for key, value in self.roms.items():
            try:
                temp = self.ds.read_temp(value)
            except:
                temp = 999.9
                print("Issue getting temperature")
            data_values.append(temp)
            internal_led.value(1)
            sleep(0.1)
            internal_led.value(0)
        watchdog.feed()
        return data_values
        
class temp_hum_sht45:    
    def __init__(self,i2c_obj, name="SHT45"):
        self.sht = sht4x.SHT4X(i2c_obj)
        self.column_names  = [name+"_Air Temperature",name+"_RH"]
    
    def read_values(self,watchdog, internal_led, debug = False):
        data_values = []
        try:
            temperature, relative_humidity = self.sht.measurements
        except:
            temperature = 999.9
            relative_humidity = 999.9
        data_values.append(temperature)
        data_values.append(relative_humidity)
        watchdog.feed()
        
        return data_values
    
class TDR_CS616:
    def __init__(self, nb_cs616=8, meas_pin=11,ctrl_pins = [6,7,8], disable_pin=9):
        #self.enable_Pin = Pin(enable_pin,Pin.OUT) # Pin to enable sensors with 5V
        #self.enable_Pin.value(0)
        self.disable_Pin = Pin(enable_pin,Pin.OUT) # Pin to disable sensors with 5V
        self.disable_Pin.value(1) # turn ON to disable
        
        self.switch_control = CD4051.CD4051(ctrl_pins[0],ctrl_pins[1],ctrl_pins[2]) # control of the first CD4051 switch
        #self.signal_control = CD4051.CD4051(sig_ctrl_pins[0],sig_ctrl_pins[1],sig_ctrl_pins[2]) # control of the second CD4051 switch
        
        # create the column names for each sensor
        self.column_names = []
        for i in range(0,nb_cs616):
            self.column_names.append("TDR"+str(i)+"_us")
            self.column_names.append("TDR"+str(i)+"_WC%")
        # handle the frequency counting Pin 
        self.pin_counter = PWMCounter(meas_pin, PWMCounter.EDGE_RISING)
        self.pin_counter.set_div() # Set divisor to 1 (just in case)
        self.pin_counter.start() # Start counter
        self.pin_counter.stop() # Stop counter
        
        self.number = nb_cs616
        
    def _cs616_measure(self):
        ''' The frequency measuring function
        the period of the CS616 is then used to deduce soil
        water content'''
        sampling_time = 100000
        mean_freq = 0
        self.pin_counter.stop()
        self.pin_counter.reset()
        
        outlier = True # to see if there is a major discrepancy between meass
        ind_freqs = []
        stop_loop = 0 
        
        while outlier:
            if stop_loop > 3:
                mean_freq = 0
                outlier = False
            for i in range(1,11):
                cond = True
                last_check = ticks_us()
                self.pin_counter.start()
                while cond:
                    if ticks_diff(tmp := ticks_us(), last_check) >= sampling_time:
                        freq = self.pin_counter.read_and_reset() / (sampling_time / 1000000)
                        ind_freqs.append(freq)
                        mean_freq = mean_freq + (freq)/10
                        cond = False
                self.pin_counter.stop()
                self.pin_counter.reset()
            stop_loop = stop_loop+1
            std_freq = standard_deviation_calc(ind_freqs)
            outlier = rerun_meas_loop(std_freq,mean_freq,0.1)
        try:
            period = 1/mean_freq * 1000000 # in us
        except:
            period = 9999
        
        return period, std_freq, stop_loop
    
    def _convert_period_to_wc(self,period_value):
        # this function is given in the manual of the CS616
        VW=(-0.0663 + (-0.0063*period_value)+(0.0007*period_value**2))*100
        return VW
    
    def turn_off(self):
        #self.enable_Pin.value(0)
        self.disable_Pin.value(1)
        
    def read_values(self,watchdog,internal_led, debug = False):
        data_values = []
        
        for i in range(0,self.number):
            self.switch_control.set_output(i)
            #self.enable_Pin.value(1)
            self.disable_Pin.value(0)
            
            sleep(0.5) # just wait for it to turn on
            
            try:
                value_1, std_freq_meas,nb_loops = self._cs616_measure() # Measure frequency
                if debug:
                    print(f"Probe {i} period is {value1:.1f}. It took {nb_loops} loops.") 
                value_2 = self._convert_period_to_wc(value_1) # convert freq to water content
                if debug:
                    print(f"Probe {i} water content is {value2:.1f}")
            except Exception as e:
                value_1 = 999.9
                value_2 = 999.9
                print("Error: ",e)
            
            self.disable_Pin.value(1)
            #self.enable_Pin.value(0)
            
            data_values.append(value_1)
            data_values.append(value_2)
            
            watchdog.feed()
            
            internal_led.value(1)
            sleep(0.1)
            internal_led.value(0)
        
        self.switch_control.set_output(0) # go back to first position to avoid pin getting stuck
        self.disable_Pin.value(1)
        
        return data_values

class dendrometer:
    def __init__(self,i2c_obj,on_pins=[6],nb_dendros=1,addr=72,names=["test"]):
        gain = 1
        self.excite_pins = []
        try:
            c = 0
            for i in on_pins:
                self.excite_pins.append(Pin(i,Pin.OUT))
                self.excite_pins[c].value(0)
                c = c+1
            self.ads = ads1x15.ADS1115(i2c_obj, addr, gain)
        except Exception as e:
            print(e)
        
        self.nb_dendros = nb_dendros
        if self.nb_dendros == 1:
            self.column_names = [names[0]+"_raw_1",names[0]+"_raw_2",names[0]+"_ratio"]
        elif self.nb_dendros ==2:
            self.column_names = [names[0]+"_raw_1",names[0]+"_raw_2",names[0]+"_ratio",
                                 names[1]+"_raw_1",names[1]+"_raw_2",names[1]+"_ratio"]
        else:
            self.column_names = None
            print("Error too many dendros on same ADC")
            
    def read_values(self,watchdog,internal_led, debug = False):
        data_values = []
        try:
            for i in range(0,self.nb_dendros):
                self.excite_pins[i].value(1)
                sleep(0.05)
                value1 = 0
                value2 = 0
                internal_led.value(1)
                for u in range(0,10):
                    value1 = value1 + self.ads.read(1,0)/10
                    value2 = value2 + self.ads.read(1,1)/10
                    sleep(0.05)
                internal_led.value(0)
                sleep(0.05)
                self.excite_pins[i].value(0)
                data_values.append(value1)
                data_values.append(value2)
                data_values.append(value2/value1)
                
        except Exception as e:
            print(e)
            data_values = [999999,999999,999999]
            if self.nb_dendros == 2:
                data_values = [999999,999999,999999,999999,999999,999999]
        
        for n in range(0,self.nb_dendros):
            self.excite_pins[n].value(0) # make sure the activation pin is off
        
        watchdog.feed() # feed the watchdog of the datalogger class
        internal_led.value(0)
        print(data_values)
        return data_values