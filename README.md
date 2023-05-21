# -Velox-CC-speed


REQUIREMENTS


1- Modern car with CC commanded by CANbus
2- Any esp32 module with wifi connection wired to a CAN socket (I use the MACCHINA <a href="https://www.macchina.cc/catalog/a0-boards/a0-under-dash">A0</a> with stock <a href="https://github.com/collin80/ESP32RET">firmware</a> )
3- Smartphone with TERMUX app and <a href="https://wiki.termux.com/wiki/Termux:API">TERMUX-API</a> package installed
4- The correct speed camera database for your country coverted to sqlite format (Italian DB is already provided).
5- Last but not least you need to obtain the 2 strings that correspond to your car + and - CC buttons and substitute them in the python script.
