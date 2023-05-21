#!/usr/bin/env python3
'''
CC_speed.py

 Created: November 19, 2022
 Author: Lawrence Bandini
 Copyright (c) 2022-2032 Lawrence Bandini, Luca Bandini
 
 
LICENSE

Subject to the terms set forth in this Agreement and the App Store Terms of Service, the author grants You a
nonexclusive, nontransferable, nonsublicensable, revocable, limited right and license to install and run the
Program on Your Device solely in connection with Your authorized use of the Associated Product.
Your use of the Associated Product is governed by the terms of the Associated Product Agreement. Your
right to use the Program will cease upon the earlier of (i) the expiration, termination or suspension of the
Associated Product Agreement, or (ii) the expiration, termination or suspension of Your status as an
authorized user of the Associated Product. The author may audit Your use of the Program. You are not
permitted to use the Program for any purpose other than in connection with Your authorized use of the
Associated Product. You agree to comply with any applicable third party terms when using the Program.

CONSENT TO USE LOCATION-BASED SERVICES AND DATA

The Program may contain or use location-based services. If You enable, use or access such location-
based services in connection with the Program, You hereby consent to the collection, transmission and use
of Your location data by the Program. Information about the Program’s collection and use of location data
will be specified in the Program’s About section; such use may include verifying or otherwise recording your
location for the purposes specified in the Data Collection and Privacy section below.
If the Program provides real-time location or route guidance, YOU ASSUME ALL RISKS ASSOCIATED
WITH YOUR USE OF SUCH REAL TIME LOCATION DATA OR ROUTE GUIDANCE. LOCATION DATA
MAY NOT BE ACCURATE. 
'''

import telnetlib
import time
import subprocess
import sqlite3
from sqlite3 import Error

HOST = "192.168.4.1"                                  # Default IP of MACCHINA A0 with ESP32RET firmware

CC_tn_data_binary_MINUS = b"\xf1\x00\x83\x00\x00\x00\x00\x08\x00\xE0\x80\x10\x00\x00\x00\x00\x00" # C.C. - button byte stream to send at MACCHINA A0 for 1 Km/h change
CC_tn_data_binary_PLUS = b"\xf1\x00\x83\x00\x00\x00\x00\x08\x00\xE0\x80\x08\x00\x00\x00\x00\x00" # C.C. +  // 

def create_connection(db_file):                       # SQlite database connection function 
    """ create a database connection to the SQLite database
        specified by the db_file
    :param db_file: database file
    :return: Connection object or None
    """
    conn = None
    try:
        conn = sqlite3.connect(db_file)             
 #       conn.set_trace_callback(print)
    except Error as e:
        print(e)

    return conn
	
def query_velox_speed_by_position(conn, lon, lat):    # Main function
    """
    Query  speed by latitude and longitude
    :param conn: the Connection object
    :param speed:
    :return:
    """

    cur = conn.cursor()
    cur.execute("SELECT speed FROM t_velox WHERE x LIKE ? AND y LIKE ?", (lon, lat,))  # The SQLITE query for retriving velox speed limit given current car position 
    row = cur.fetchone()
    car_speed = int((float(speed.stdout)+1)*3.6)      # m/s to Km/h conversion with upper rounding for extra security


    if row is None:                                   # Idle waiting for velox in range and set 200 Km/h as precautional exit from app 
       speed_limit_v = 200  
       print("No velox in car range")
       with open('excess.txt', 'r') as f:             # Check if we sent C.C. - and how many times
           stringa = f.read()
           f.close()
           v_add = int(stringa)                     
           if v_add > 0:                              # Check if and how much CC - was triggered
                print("Returing to prevoius speed")
                for i in range(v_add):
                    if i>0:
                        time.sleep(0.25)
                    print("Sending + signal to CC")   ### Command C.C. + n times	to increase car speed					
                    tn.write(CC_tn_data_binary_PLUS)
                time.sleep(20)

                with open('excess.txt', 'w') as f:    # Reset to 0 the excess speed after reading the extra speed
                     f.write('%d' % 0)
                     f.close()		        
    else:		
            
            speed_limit = row[0]                      # Get speed limit from velox in range
            speed_limit_v = int(speed_limit)          # Float to integer 
            excess = car_speed - speed_limit_v        # Speed to remove 
            n_required_signals = int(excess)          # Number of C.C. triggerings
			
	
    if car_speed <= speed_limit_v:                    # Not overspeeding so no action needed
            print("Cruising below limits...")
    if car_speed > speed_limit_v:                     # If we are over speed limit save the extra speed to file for later
            excess = car_speed - speed_limit_v        # Speed to remove 
            n_required_signals = int(excess)          # Number of C.C. triggerings
            print("Doing", car_speed,"Km/h")
            print("Car is", excess, "too fast")        
            with open('excess.txt', 'w') as f:       
                f.write('%d' % excess)
            for i in range(n_required_signals):
                if i>0:
                    time.sleep(0.25)				
                    print("Sending - signal to CC")				
                    tn.write(CC_tn_data_binary_MINUS) ### Command C.C. - n times to reduce car speed
            time.sleep(20)
		
     
if __name__ == "__main__":                            ###### Main program #####
  while True:	
    try:
        with open('last_location.txt', 'w') as f:     # Save GPS data from termux api call
             GPS_data = subprocess.run(['termux-location', '-p','gps'], capture_output=True, encoding='UTF-8')
             f.write(GPS_data.stdout)
             f.close()
             tn = telnetlib.Telnet(HOST)              # Open Telnet connection
             tn.write( b'\xe7\xe7' )                  # Put Telnet connection in binary mode  
             x = subprocess.run(['cat last_location.txt | jq .longitude | cut -c 1-5 | sed "s/$/%/" | tr -d "\n"'], shell=True, capture_output=True, encoding='utf-8') # Parsing the x column value placeholder substitute from car longitude
             y = subprocess.run(['cat last_location.txt | jq .latitude | cut -c 1-5 | sed "s/$/%/" | tr -d "\n"'], shell=True, capture_output=True, encoding='utf-8') # Parsing the y column value placeholder substitute from car latitude
             speed = subprocess.run(['cat last_location.txt | jq .speed | tr -d "\n"'], shell=True, capture_output=True, encoding='UTF-8') # Parsing the car speed
             database = r"velox.db"
             conn = create_connection(database)       # Create a database connection
             query_velox_speed_by_position(conn, x.stdout, y.stdout)  # Execute main function
             tn.close()                               # Close Telnet connection

    except ValueError:

        print("Oi...",Error)
		
#conn.close()                                         # Closing the DB connection
