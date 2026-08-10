from time import  sleep_ms, sleep, ticks_us, ticks_ms, ticks_diff
import math
from machine import Pin
import binascii
import CD4051
from counter import PWMCounter
import onewire, ds18x20
import sht4x
import ads1x15
import tmp1826

def standard_deviation_calc(ind_val_array):
    sample_mean = 0
    if len(ind_val_array)>0:
        for i in ind_val_array:
            sample_mean = sample_mean + i/len(ind_val_array)
        sum_diffs = 0
        for i in ind_val_array:
            sum_diffs = sum_diffs + math.pow(i-sample_mean,2)
        variance = sum_diffs/len(ind_val_array)
        standard_deviation = math.sqrt(variance)
    else:
        standard_deviation = 9999

    return standard_deviation

def rerun_meas_loop(std,sample_mean,criteria):
    if sample_mean == 0:
        return False
    var_pct = std/sample_mean * 100
    print(f"Variance: %1.1f" % var_pct)
    if var_pct > criteria:
        return True
    else:
        return False


class temp_tmp1826:
    def __init__(self, meas_pin=12):
        self.exists = True
        try:
            self.dat_pin = Pin(meas_pin)
            self.ow = onewire.OneWire(self.dat_pin) # choose the adapted pin
            self.ow.reset() # reset the onewire bus (necessary)
            self.sensor = tmp1826.TMP1826(self.ow) # create the tmp1826 object
            self.roms = self.sensor.scan() # get all sensors
            self.sensor_dict = {}
            self.column_names = []
            sleep(0.25)
            for i in self.roms:
                label = self.sensor.read_label(i)
                self.sensor_dict[str(binascii.hexlify(i))] = label
                self.column_names.append("Temp_"+label)
        except Exception as e:
            print("Error in initialising tmp1826 sensor")
            self.column_names = []
            self.sensor_ditc = {}
            print(e)
            self.exists = False
        
        self.error = False
        self.total_error = False
        
    def read_values(self,watchdog,internal_led, debug = False):
        data_values = []
        try:
            self.ow.reset() # reset the onewire bus (necessary)
            sleep(0.5)
            self.sensor.convert_temp()
            sleep(0.750)
            for i in self.roms:
                print("Sensor: "+self.sensor_dict[str(binascii.hexlify(i))])
                try:
                    data_values.append(self.sensor.read_temp(i, verbose = True))
                except Exception as e:
                    print("Error for this sensor")
                    print(e)
                    data_values.append(9999)
                sleep(0.1)
            return data_values
        except Exception as e:
            print("Major error in tmp1826 loop:")
            print(e)
            for i in self.roms:
                data_values.append(9999)
            return data_values
                    
class temp_DS18B20:
    def __init__(self,meas_pin=12,roms={7: bytearray(b'(\xac`TB \x01\x19'), 6 : bytearray(b'(*n\xf1B \x01\xcb')}):
        self.exists = True
        try:
            self.dat_pin = Pin(meas_pin)
            self.ds = ds18x20.DS18X20(onewire.OneWire(self.dat_pin))
            self.roms = roms # a dictionnary with sensor number and roms
            self.column_names = []
        except Exception as e:
            self.exists = False
            self.roms = roms # a dictionnary with sensor number and roms
            self.column_names = []
            with open('logs.txt','a') as f:
                f.write("Error initialising ds18B20:")
                f.write(str(e))
                f.write("\n")
        for key, value in self.roms.items():
            self.column_names.append("Temp_"+str(key))
        self.error = False
        self.total_error = False
            
    def read_values(self,watchdog,internal_led, debug = False):
        data_values = []
        self.ds.convert_temp()
        sleep(1)
        for key, value in self.roms.items():
            try:
                temp = self.ds.read_temp(value)
            except Exception as e:
                temp = 9999
                if not self.error:
                    with open('logs.txt','a') as f:
                        f.write("Error read temp ds18b20:")
                        f.write(str(e))
                        f.write("\n")
                    self.error = True
            data_values.append(temp)
            internal_led.value(1)
            sleep(0.05)
            internal_led.value(0)
            watchdog.feed()
        return data_values
        
class temp_hum_sht45:    
    def __init__(self,i2c_obj, name="SHT45"):
        self.error = False
        self.i2c_obj = i2c_obj
        try:
            self.sht = sht4x.SHT4X(self.i2c_obj)
            self.exists = True
        except Exception as e:
            print(e)
            self.exists = False
            with open('logs.txt','a') as f:
                f.write("Error init SHT45:")
                f.write(str(e))
                f.write("\n")
            print("Major Error in init SHT45")
        self.column_names  = [name+"_T_air",name+"_RH_air"]
    
    def read_values(self,watchdog, internal_led, debug = False):
        data_values = []
        try:
            temperature, relative_humidity = self.sht.measurements
        except Exception as e:
            print(e)
            temperature = 9999
            relative_humidity = 9999
            if not self.error:
                with open('logs.txt','a') as f:
                    f.write("Error read SHT45:")
                    f.write(str(e))
                    f.write("\n")
                self.error = True
        data_values.append(temperature)
        data_values.append(relative_humidity)
        watchdog.feed()
        print("SHT45 data:",data_values)
        
        return data_values
    
class TDR_CS616:
    def __init__(self, nb_cs616=8, meas_pin=11,ctrl_pins = [6,7,8], disable_pin=9,corrected=False,rtc=None):
        #self.enable_Pin = Pin(enable_pin,Pin.OUT) # Pin to enable sensors with 5V
        #self.enable_Pin.value(0)
        self.disable_Pin = Pin(disable_pin,Pin.OUT) # Pin to disable sensors with 5V
        self.disable_Pin.value(1) # turn ON to disable
        
        self.switch_control = CD4051.CD4051(ctrl_pins[0],ctrl_pins[1],ctrl_pins[2]) # control of the first CD4051 switch
        
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
        
        self.exists = True # allways exists since no way to check
        
        self.number = nb_cs616
        self.corrected = corrected
        
        if corrected:
            self.rtc = rtc
            self.rtc.output_32kHz(False)
            self.column_names.append("32kHz_correction")
        
    def _cs616_measure(self, watchdog):
        ''' The frequency measuring function
        the period of the CS616 is then used to deduce soil
        water content'''
        sampling_time = 100000
        mean_freq = 0
        self.pin_counter.stop()
        self.pin_counter.reset()
        
        outlier = True # to see if there is a major discrepancy between meass
        stop_loop = 0 
        
        while outlier:
            ind_freqs = []
            mean_freq = 0
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
            outlier = rerun_meas_loop(std_freq,mean_freq,2)
            if stop_loop > 3:
                mean_freq = 0
                outlier = False
            watchdog.feed()
        
        if mean_freq>100:
            period = 1/mean_freq * 1000000 # in us
            if period < 12 or period > 50:
                period = 9999
        else:
            period = 9999
        
        return period, std_freq, stop_loop
    
    def measure_32kHz(watchdog):
        ''' Measure the 32.768 kHz frequency of RTC'''
        sampling_time = 100000
        mean_freq = 0
        self.pin_counter.stop()
        self.pin_counter.reset()
        
        outlier = True # to see if there is a major discrepancy between meass
        stop_loop = 0 
        
        while outlier:
            ind_freqs = []
            mean_freq = 0
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
            outlier = rerun_meas_loop(std_freq,mean_freq,2)
            if stop_loop > 3:
                mean_freq = 0
                outlier = False
            watchdog.feed()
        return period, std_freq, stop_loop    
    
    def _convert_period_to_wc(self,period_value):
        # this function is given in the manual of the CS616
        VW=(-0.0663 + (-0.0063*period_value)+(0.0007*period_value**2))*100
        if (VW>80):
            VW = 9999
        return VW
    
    def turn_off(self):
        #self.enable_Pin.value(0)
        self.disable_Pin.value(1)
        
    def read_values(self,watchdog,internal_led, debug = False):
        data_values = []
        error_in_corr = False
        
        ### Correction 1:
        if self.corrected:
            self.disable_Pin.value(1) # make sure we are not receiving any CS616 data
            self.rtc.output_32kHz(True) # turn on kHz temperature corrected output from RTC
            sleep(0.1)
            try:
                freq_corr1, std_freq_meas,nb_loops = measure_32kHz(watchdog) # Measure frequency
            except:
                freq_corr = 9999
                error_in_corr = True
            self.rtc.output_32kHz(False) # turn off kHz temperature corrected output from RTC
        
        for i in range(0,self.number):
            self.switch_control.set_output(i)
            #self.enable_Pin.value(1)
            self.disable_Pin.value(0)
            sleep(0.3) # just wait for it to turn on
            try:
                value_1, std_freq_meas,nb_loops = self._cs616_measure(watchdog) # Measure frequency
                print(f"Probe {i} period is {value_1:.1f}. It took {nb_loops} loops.")
                if value_1 == 0:
                    value_2 = 0
                else:
                    if value_1 != 9999:
                        value_2 = self._convert_period_to_wc(value_1) # convert freq to water content
                    else:
                        value_2 = 9999
                if debug:
                    print(f"Probe {i} water content is {value_2:.1f}")
            except Exception as e:
                value_1 = 9999
                value_2 = 9999
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
        
        ### Frequency Correction 2:
        if self.corrected:
            self.disable_Pin.value(1) # make sure we are not receiving any CS616 data
            sleep(0.1)
            self.rtc.output_32kHz(True) # turn on kHz temperature corrected output from RTC
            sleep(0.1)
            try:
                freq_corr2, std_freq_meas,nb_loops = measure_32kHz(watchdog) # Measure frequency
            except Eception as e:
                freq_corr = 9999
                error_in_corr = True
                print(e)
            self.rtc.output_32kHz(False) # turn off kHz temperature corrected output from RTC
            freq_corr = (freq_corr1+freq_corr2)/2
            data_values.append(freq_corr)
        
        return data_values

class dendrometer:
    def __init__(self,i2c_obj,on_pins=[6],nb_dendros=1,addr=72,names=["test"]):
        self.error = False
        self.i2c_obj = i2c_obj
        self.addr = addr
        self.gain = 1
        self.exists = True
        
        if len(on_pins) != nb_dendros:
            print("Mismatch between dendro number and excitation pin number")
            self.exists = False
        
        self.excite_pins = []
        try:
            c = 0
            for i in on_pins:
                self.excite_pins.append(Pin(i,Pin.OUT))
                self.excite_pins[c].value(0)
                c = c+1
        except Exception as e:
            print("Error in selecting excite pins")
            self.exists = False
        try:    
            self.ads = ads1x15.ADS1115(i2c_obj, addr, self.gain)
        except Exception as e:
            print(e)
            with open('logs.txt','a') as f:
                f.write("Error init ADS1115:")
                f.write(str(e))
                f.write("\n")
            self.exists = False
        
        self.nb_dendros = nb_dendros
        if self.nb_dendros == 1:
            self.column_names = [names[0]+"_raw_1",names[0]+"_raw_2",names[0]+"_ratio"]
        elif self.nb_dendros ==2:
            self.column_names = [names[0]+"_raw_1",names[0]+"_raw_2",names[0]+"_ratio",
                                 names[1]+"_raw_1",names[1]+"_raw_2",names[1]+"_ratio"]
        else:
            self.column_names = None
            self.exists = False
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
                    value1 = value1 + self.ads.read(1,0+i*2)/10
                    value2 = value2 + self.ads.read(1,1+i*2)/10
                    sleep(0.05)
                internal_led.value(0)
                sleep(0.05)
                self.excite_pins[i].value(0)
                data_values.append(value1)
                data_values.append(value2)
                ratio = value2/value1 if value1 != 0 else 9999
                data_values.append(ratio)
                    
        except Exception as e:
            print(e)
            if not self.error:
                with open('logs.txt','a') as f:
                    f.write("Error read dendro:")
                    f.write(str(e))
                    f.write("\n")
            if self.nb_dendros == 2:
                for i in range(len(data_values),6):
                    data_values.append(9999)
            else:
                data_values = [9999,9999,9999]
            self.error = True
            
        for n in range(0,self.nb_dendros):
            self.excite_pins[n].value(0) # make sure the activation pin is off
            
        watchdog.feed() # feed the watchdog of the datalogger class
        internal_led.value(0)
        
        print("Dendro data:",data_values)
        
        return data_values
