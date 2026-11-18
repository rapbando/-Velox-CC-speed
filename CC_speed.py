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

import json
import math
import os
import socket
import sqlite3
import subprocess
import time

# --- Configuration -----------------------------------------------------------

HOST = "192.168.4.1"            # Default IP of MACCHINA A0 with ESP32RET firmware
PORT = 23                       # Telnet port of ESP32RET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "velox.db")
EXCESS_FILE = os.path.join(BASE_DIR, "excess.txt")            # Total km/h removed so far
LOCATION_FILE = os.path.join(BASE_DIR, "last_location.txt")   # Last raw GPS fix (debug)

SEARCH_RADIUS_M = 500           # A velox closer than this is "in range"
SPEED_MARGIN_MS = 1.0           # Added to GPS speed (m/s) for extra security
SIGNAL_GAP_S = 0.25             # Pause between two C.C. button frames
SETTLE_TIME_S = 20              # Wait for the car to reach the new speed
ERROR_RETRY_S = 5               # Wait after a failed cycle
GPS_TIMEOUT_S = 60              # Max time to wait for termux-location
MAX_SIGNALS_PER_CYCLE = 30     # Safety cap: never send more frames than this at once
MAX_TOTAL_REDUCTION = 60        # Safety cap: never lower C.C. by more than this in total
SOUND_ALERT = True              # Announce each new velox when it comes in range
ALERT_TEXT = "Velox, limite %d"  # Spoken text, %d = speed limit in km/h

CC_tn_data_binary_MINUS = b"\xf1\x00\x83\x00\x00\x00\x00\x08\x00\xE0\x80\x10\x00\x00\x00\x00\x00"  # C.C. - button frame, 1 km/h
CC_tn_data_binary_PLUS = b"\xf1\x00\x83\x00\x00\x00\x00\x08\x00\xE0\x80\x08\x00\x00\x00\x00\x00"   # C.C. + button frame, 1 km/h
ESP32RET_BINARY_MODE = b"\xe7\xe7"                                                                 # Put connection in binary mode


# --- Persistent state ---------------------------------------------------------

def read_reduction():
    """Return how many km/h we have taken off the cruise control so far."""
    try:
        with open(EXCESS_FILE) as f:
            return max(0, int(f.read().strip() or 0))
    except (OSError, ValueError):
        return 0


def write_reduction(value):
    with open(EXCESS_FILE, "w") as f:
        f.write("%d" % value)


# --- GPS ----------------------------------------------------------------------

def get_location():
    """Return (lon, lat, speed_m_s) from termux-location, or None if no usable fix."""
    result = subprocess.run(["termux-location", "-p", "gps"], capture_output=True,
                            encoding="utf-8", timeout=GPS_TIMEOUT_S)
    with open(LOCATION_FILE, "w") as f:
        f.write(result.stdout)
    try:
        data = json.loads(result.stdout)
        lon = float(data["longitude"])
        lat = float(data["latitude"])
        speed = float(data["speed"])
    except (ValueError, KeyError, TypeError):
        print("No usable GPS fix")
        return None
    return lon, lat, speed


# --- Sound alert --------------------------------------------------------------

_alerted_velox = None           # Position of the velox we already announced


def _spawn(cmd):
    """Start a command without waiting for it. Returns False if it can't be run."""
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def sound_alert(speed_limit):
    """Speak the speed limit and vibrate; fall back to the terminal bell."""
    spoken = _spawn(["termux-tts-speak", ALERT_TEXT % speed_limit])
    _spawn(["termux-vibrate", "-f", "-d", "400"])
    if not spoken:
        print("\a", end="", flush=True)


def alert_if_new(velox):
    """Alert once when a velox comes in range; re-arm when it leaves range."""
    global _alerted_velox
    if velox is None:
        _alerted_velox = None
        return
    speed_limit, _, pos = velox
    if pos != _alerted_velox:
        _alerted_velox = pos
        if SOUND_ALERT:
            sound_alert(speed_limit)


# --- Velox database -----------------------------------------------------------

def distance_m(lon1, lat1, lon2, lat2):
    """Great-circle distance in metres (haversine)."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_velox(conn, lon, lat, radius_m=SEARCH_RADIUS_M):
    """Return (speed_limit_kmh, distance_m, (x, y)) of the closest velox within radius_m, or None.

    Note: the DIRTYPE/DIRECTION columns in velox.db are all 0, so the direction
    of travel cannot be used to filter cameras.
    """
    dlat = radius_m / 111320.0
    dlon = radius_m / (111320.0 * max(math.cos(math.radians(lat)), 0.01))
    rows = conn.execute(
        "SELECT x, y, speed FROM t_velox "
        "WHERE x BETWEEN ? AND ? AND y BETWEEN ? AND ? AND speed <> ''",
        (lon - dlon, lon + dlon, lat - dlat, lat + dlat),
    ).fetchall()

    best = None
    for x, y, speed in rows:
        try:
            limit = int(float(speed))
        except (TypeError, ValueError):
            continue
        d = distance_m(lon, lat, x, y)
        if d <= radius_m and (best is None or d < best[1]):
            best = (limit, d, (x, y))
    return best


# --- Cruise control (CAN via ESP32RET socket) --------------------------------

def send_cc_signals(frame, count):
    """Send `frame` `count` times. Returns how many were actually sent."""
    sent = 0
    if count <= 0:
        return 0
    try:
        with socket.create_connection((HOST, PORT), timeout=5) as sock:
            sock.sendall(ESP32RET_BINARY_MODE)
            for i in range(count):
                if i > 0:
                    time.sleep(SIGNAL_GAP_S)
                sock.sendall(frame)
                sent += 1
    except OSError as e:
        print("CAN adapter error:", e)
    return sent


# --- Main logic ---------------------------------------------------------------

def run_cycle(conn, reduction):
    """Run one control cycle. Returns the updated total reduction."""
    loc = get_location()
    if loc is None:
        time.sleep(ERROR_RETRY_S)
        return reduction
    lon, lat, speed_ms = loc
    car_speed = int((speed_ms + SPEED_MARGIN_MS) * 3.6)   # m/s to km/h, rounded up for security

    velox = nearest_velox(conn, lon, lat)
    alert_if_new(velox)

    if velox is None:
        print("No velox in car range")
        if reduction > 0:
            print("Returning to previous speed (+%d km/h)" % reduction)
            sent = send_cc_signals(CC_tn_data_binary_PLUS, reduction)
            reduction -= sent
            write_reduction(reduction)
            time.sleep(SETTLE_TIME_S)
        return reduction

    speed_limit, dist, _ = velox
    print("Velox %d km/h at %.0f m, doing %d km/h" % (speed_limit, dist, car_speed))
    excess = car_speed - speed_limit
    if excess <= 0:
        print("Cruising below limits...")
        return reduction

    n = min(excess, MAX_SIGNALS_PER_CYCLE, MAX_TOTAL_REDUCTION - reduction)
    if n <= 0:
        print("Safety cap reached (%d km/h already removed), not sending more" % reduction)
        return reduction

    print("Car is %d km/h too fast, sending %d - signals to CC" % (excess, n))
    sent = send_cc_signals(CC_tn_data_binary_MINUS, n)
    reduction += sent
    write_reduction(reduction)
    time.sleep(SETTLE_TIME_S)
    return reduction


def main():
    conn = sqlite3.connect(DATABASE)
    reduction = read_reduction()
    try:
        while True:
            try:
                reduction = run_cycle(conn, reduction)
            except Exception as e:   # Keep running whatever happens in one cycle
                print("Oi...", repr(e))
                time.sleep(ERROR_RETRY_S)
    except KeyboardInterrupt:
        print("Stopped. Current C.C. reduction: %d km/h" % reduction)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
