# -Velox-CC-speed


REQUIREMENTS


- Modern car with CC commanded trough CANbus
- Any esp32 module with wifi connection wired to a CAN socket (I use the MACCHINA <a href="https://www.macchina.cc/catalog/a0-boards/a0-under-dash">A0</a> with stock <a href="https://github.com/collin80/ESP32RET">firmware</a> )
- Smartphone with TERMUX app and <a href="https://wiki.termux.com/wiki/Termux:API">TERMUX-API</a> package installed and of course python3
- The correct speed camera locations database for your country converted to sqlite format (Italian DB is already provided).
- Last but not least you need to obtain the 2 strings that correspond to your car + and - CC buttons and substitute them in at line 42 and 43 in the python  <a href="https://github.com/rapbando/-Velox-CC-speed/blob/main/CC_speed.py">script</a> , easy way is to use <a href="https://savvycan.com">savvycan</a>

USAGE:

python3 CC_speed.py
