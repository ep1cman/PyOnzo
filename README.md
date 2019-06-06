# PyOnzo
A Python library for interfacing with the "ONZO" energy monitor

Tested on Linux & MacOS

# Installation
This software requires that you use [Python 3.x](https://www.python.org/downloads/).

To use this package you must also ensure you install hidapi.
```
sudo pip install hidapi
```

# Energy readings
To get a basic understanding of the meter readings from your Onzo energy meter you can use ``device.py`` script to view data being broadcast over 433Mhz from your energy clamp and then read the data over usb connected to your computer.

```
python device.py
```

# To Do
- Add documentation
- Add support for reading off historic data from display
- Document the devices protocol
