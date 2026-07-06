# Open Ecophysio Datalogger
A comptetitive datalogger for use in environmental science. It is adapted to situtation in remote locations with little access to networks.

The interfacing software is compatible with windows, macOS and linux computers. 

  * [Hardware](#hardware)
    + [Full size datalogger](#full-size-datalogger)
    + [Micro sized datalogger](#micro-sized-datalogger)
  * [Software](#software)
    + [On the computer](#on-the-computer)
    + [On the datalogger](#on-the-datalogger)

## Hardware
### Full size datalogger
![3D rendering of datalogger PCB](datalogger_pcb.png)
We use a custome made PCB that integrates
- A battery input (usable with 12V lead batteries)
- a low consumption and high efficiency step-down converter that can convert 6-40V down to 5V
- a low-drift RTC clock
- An SD card slot
- two controllable power outputs of 5V and 12V (or battery voltage) using MOSFETs
- temperature corrected reference frequency generators from the RTC chip
- Qwiic compatible I2C and UART connectors
- A way to measure input battery voltage
### Micro sized datalogger
![3D rendering of datalogger PCB](micro_datalogger_pcb.png)
This is a miniaturised version of the big pcb when size is a constraint. It pushed all the power and clock circuitry beneath the Pi Pico.
It lacks some functionnality of the bigger version such as the controllable power outputs and the full shutdown circuitry. 

## Software
### On the computer
![Examples of interefacing GUIs](GUI_example.png)
We use two GUIs on the computer:
- one that generates the json configuration file for the datalogger
- one that enables communication with the datalogger to update the clock and download files from the SD card

The datalogger management GUI also allows you to setup the datalogger with all the necessary libraries and config files to start datalogging right away.
#### Windows installation of the management GUI
The graphical user interface to perform some interfacing functions was made to be as easy to use as possible. For windows an executable file was created by using the pyinstaller library. 

To run on windows you first need to install python on your computer. You can install it easily from the windows store.
Then open up the powershell:
```
pip install mpremote
```
That should do the trick and you can just run the full_management_gui.exe in the Software/computer folder. 
#### Linux machine
You just need to install the mpremote tool. 
```
pip install mpremote
```
And then go to the folder containing full_management_gui.py: 
```
python full_management_gui.py
```

### On the datalogger
We use two modules. The datalogger module and the sensor module. 
