import os, sys, io
import M5
from M5 import *
import time
import network
import json
import socket
import utime as _time
import ntptime

# Configuration
SCREEN_WIDTH = 540
LEFT_COLUMN_WIDTH = 260
TOP_LEFT_OFFSET_X = 10 
LISTEN_PORT = 80

# Timezone and Power
UTC_OFFSET = 9     
IDLE_TIMEOUT = 30    # Seconds to return to today
SLEEP_TIMEOUT = 60   # Seconds idle before Deep Sleep

# UI Constants - Schedule
L_RECT_X, L_RECT_W = 35, 85 
R_RECT_X, R_RECT_W = 509, 3
Y_START_BASE = 259
RECT_H_BASE = 145 
GAP = 4
WEATHER_Y_OFFSET = 20 

# UI Constants - Calendar Grid (Top Right)
CAL_X, CAL_Y = 273, 60 
CELL_W, CELL_H = 32, 32
CELL_GAP = 4

# Grid Colors
CLR_MONTH_CELL = 0xcccccc
CLR_TODAY_CELL = 0x444444
CLR_OTHER_CELL = 0xeeeeee
CLR_PAST = 0x888888
CLR_FUTURE = 0x444444
CLR_TODAY = 0xffffff
CLR_OTHER = 0xaaaaaa

# Fonts
JP_FONT = Widgets.FONTS.EFontJA24     
TIME_FONT = Widgets.FONTS.DejaVu24    
TIME_FONT_SMALL = Widgets.FONTS.DejaVu18
NUM_FONT = Widgets.FONTS.DejaVu18

# Navigation Buttons
BTN_Y, BTN_W, BTN_H = 728, 80, 80
BTN_L_X, BTN_C_X, BTN_R_X = 38, 230, 438 
FONT_BTN_NUM = '/flash/res/font/Oxanium-SemiBold-40px.vlw'

# Footer/Update/Icons
UPD_X, UPD_Y = 150, 930
UPD_W, UPD_H = 240, 30
ICON_Y, WIFI_X, BATT_X = 917, 433, 483 

# Global State
all_available_dates = []  
current_date_idx = 0      
cached_json = None        
last_activity_time = 0    
server_socket = None
last_wifi_state = None
last_batt_lvl = -1

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
PERIOD_COLORS = [0xcccccc, 0xaaaaaa, 0x888888]
WEATHER_TEXT_COLOR = 0x777777

# ---------- Power Management ----------

def refresh_to_sleep():
    \