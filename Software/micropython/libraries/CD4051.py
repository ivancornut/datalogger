from machine import Pin

class CD4051:
    def __init__(self,pinA,pinB,pinC):
        self.A = Pin(pinA, Pin.OUT)
        self.B = Pin(pinB, Pin.OUT)
        self.C = Pin(pinC, Pin.OUT)
        
        self.A.value(0)
        self.B.value(0)
        self.C.value(0)
        
    def set_output(self,output_nb):
        if output_nb==0:
            self.A.value(0)
            self.B.value(0)
            self.C.value(0)
        elif output_nb==1:
            self.A.value(1)
            self.B.value(0)
            self.C.value(0)
        elif output_nb==2:
            self.A.value(0)
            self.B.value(1)
            self.C.value(0)
        elif output_nb==3:
            self.A.value(1)
            self.B.value(1)
            self.C.value(0)
        elif output_nb==4:
            self.A.value(0)
            self.B.value(0)
            self.C.value(1)            
        elif output_nb==5:
            self.A.value(1)
            self.B.value(0)
            self.C.value(1)   
        elif output_nb==6:
            self.A.value(0)
            self.B.value(1)
            self.C.value(1)
        elif output_nb==7:
            self.A.value(1)
            self.B.value(1)
            self.C.value(1)