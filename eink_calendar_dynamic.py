import os, sys, io
import M5
from M5 import *
import time
import network
import json
import socket
import utime as _time
import ntptime
import machine

# Configuration
SCREEN_WIDTH = 540
LEFT_COLUMN_WIDTH = 260
TOP_LEFT_OFFSET_X = 10 
LISTEN_PORT = 80

# Timezone and Power
UTC_OFFSET = 9     
IDLE_TIMEOUT = 30           # Seconds to return to today
SLEEP_TIMEOUT = 60          # Seconds idle before Deep Sleep
MAINTENANCE_WINDOW = 600    # 10 minutes (600s) to stay awake at midnight for updates

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
full_refresh_done = False # To handle midnight rollover once

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
PERIOD_COLORS = [0xcccccc, 0xaaaaaa, 0x888888]
WEATHER_TEXT_COLOR = 0x777777

# ---------- Power Management ----------

def get_seconds_until_midnight():
    """Calculates seconds until the next midnight based on local time."""
    _, _, lt = get_local_now()
    h, m, s = lt[3], lt[4], lt[5]
    seconds_past_midnight = (h * 3600) + (m * 60) + s
    seconds_in_day = 24 * 3600
    return seconds_in_day - seconds_past_midnight

def refresh_to_sleep():
    """Erases interactive elements with precision offsets to protect background lines."""
    M5.Lcd.fillRect(BTN_L_X - 1, BTN_Y - 1, BTN_W + 2, BTN_H + 2, 0xffffff)
    M5.Lcd.fillRect(BTN_C_X - 1, BTN_Y - 1, BTN_W + 2, BTN_H + 2, 0xffffff)
    M5.Lcd.fillRect(BTN_R_X - 1, BTN_Y - 1, BTN_W + 2, BTN_H + 2, 0xffffff)
    M5.Lcd.fillRect(WIFI_X + 5, ICON_Y + 6, 40, 40, 0xdddddd)
    M5.Lcd.fillRect(BATT_X - 2, ICON_Y + 6, 55, 40, 0xdddddd)

def enter_deep_sleep():
    """Clean UI and power down until next midnight."""
    # Safety: Don't sleep if we are currently in the maintenance window
    _, _, lt = get_local_now()
    if lt[3] == 0 and lt[4] < (MAINTENANCE_WINDOW // 60):
        return

    refresh_to_sleep()
    img_x = (SCREEN_WIDTH - 320) // 2
    img_y = BTN_Y + 5 
    try:
        Widgets.Image("/flash/res/img/img_deepsleep.png", img_x, img_y)
    except:
        M5.Lcd.setFont(Widgets.FONTS.DejaVu24); M5.Lcd.setTextColor(0x888888, 0xffffff)
        M5.Lcd.drawString("DEEP SLEEP", img_x + 80, img_y + 25)
    
    M5.update()
    time.sleep(1) 
    
    # Calculate sleep duration to wake up exactly at midnight
    sleep_ms = get_seconds_until_midnight() * 1000
    machine.deepsleep(sleep_ms)

# ---------- Info Screens ----------

def wait_for_tap_to_return():
    time.sleep(0.5)
    while M5.Touch.getCount() > 0: M5.update(); time.sleep(0.01)
    while True:
        M5.update()
        handle_incoming_request()
        if M5.Touch.getCount() > 0: break
        time.sleep(0.1)
    while M5.Touch.getCount() > 0: M5.update(); time.sleep(0.01)
    refresh_view(full=True)

def show_wifi_info():
    M5.Lcd.fillScreen(0xffffff)
    wlan = network.WLAN(network.STA_IF)
    ssid = wlan.config('ssid') if wlan.isconnected() else "Disconnected"
    ip = wlan.ifconfig()[0] if wlan.isconnected() else "No IP"
    M5.Lcd.setTextColor(0x000000, 0xffffff); M5.Lcd.setFont(Widgets.FONTS.DejaVu24)
    M5.Lcd.drawString("WIFI NETWORK:", 40, 100)
    M5.Lcd.setFont(Widgets.FONTS.DejaVu40); M5.Lcd.drawString(str(ssid), 40, 140)
    M5.Lcd.setFont(Widgets.FONTS.DejaVu24); M5.Lcd.drawString("IP ADDRESS:", 40, 240)
    try: Widgets.Label(ip, 40, 280, 1.0, 0x000000, 0xffffff, '/flash/res/font/Oxanium-SemiBold-40px.vlw')
    except: M5.Lcd.setFont(Widgets.FONTS.DejaVu40); M5.Lcd.drawString(ip, 40, 280)
    M5.Lcd.drawString("Tap anywhere to return", 100, 800)
    M5.update()
    wait_for_tap_to_return()

# ---------- Networking ----------

def handle_incoming_request():
    global cached_json, last_activity_time
    if not server_socket: return
    try:
        conn, addr = server_socket.accept()
        conn.settimeout(2.0)
        request = conn.recv(2048).decode()
        if "POST" in request:
            parts = request.split("\r\n\r\n")
            if len(parts) > 1:
                try:
                    new_data = json.loads(parts[1])
                    with open('/flash/calendar.json', 'w') as f: json.dump(new_data, f)
                    cached_json = new_data
                    update_state_from_json()
                    play_click_sound()
                    last_activity_time = time.ticks_ms()
                    refresh_view(full=True)
                except: pass
        conn.send('HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nReceived')
        conn.close()
    except: pass

def start_server():
    global server_socket
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('', LISTEN_PORT))
        server_socket.listen(1)
        server_socket.setblocking(False) 
        return True
    except: return False

# ---------- Logic Helpers ----------

def update_state_from_json():
    global all_available_dates, current_date_idx
    today_iso, _, _ = get_local_now()
    dts = {today_iso}
    if cached_json:
        for e in cached_json.get("events", []):
            d = str(e.get('start_date', '')).strip()[:10]
            if d: dts.add(d)
    all_available_dates = sorted(list(dts))
    current_date_idx = all_available_dates.index(today_iso) if today_iso in all_available_dates else 0

def get_local_now():
    try:
        t = time.time() + (UTC_OFFSET * 3600)
        lt = time.localtime(t)
        return "{:04d}-{:02d}-{:02d}".format(lt[0], lt[1], lt[2]), "{:02d}:{:02d}".format(lt[3], lt[4]), lt
    except: return "2026-01-01", "00:00", (2026, 1, 1, 0, 0, 0, 0, 0)

def _weekday_from_ymd(y, m, d):
    return _time.localtime(_time.mktime((y, m, d, 0, 0, 0, 0, 0)))[6]

# ---------- UI Modules ----------

def update_ui_weather(target_date, clean=True):
    y_base = 820 + WEATHER_Y_OFFSET
    if clean:
        M5.Lcd.fillRect(88, y_base + 5, 75, 45, 0xffffff) 
        M5.Lcd.fillRect(249, y_base + 5, 75, 45, 0xffffff)
        M5.Lcd.fillRect(414, y_base + 5, 90, 45, 0xffffff) # Widened to 90px
    
    hi, lo, rn = "--", "--", "--%"
    if cached_json and "weather_ls" in cached_json:
        try:
            json_today = cached_json["generated_at"].split('T')[0]
            t_p, j_p = [int(x) for x in target_date.split('-')], [int(x) for x in json_today.split('-')]
            idx = int((_time.mktime((t_p[0],t_p[1],t_p[2],0,0,0,0,0)) - _time.mktime((j_p[0],j_p[1],j_p[2],0,0,0,0,0))) / 86400)
            w_ls = cached_json["weather_ls"][0]
            idx = max(0, min(idx, len(w_ls["high_ls"]) - 1))
            hi, lo = w_ls["high_ls"][idx].replace("°C", "").strip(), w_ls["low_ls"][idx].replace("°C", "").strip()
            rn = str(int(w_ls["rain_chance_ls"][idx] * 100)) + "%"
        except: pass
    
    M5.Lcd.setTextColor(WEATHER_TEXT_COLOR, 0xffffff)
    M5.Lcd.setFont(Widgets.FONTS.DejaVu40)
    M5.Lcd.drawString(lo, 88, y_base + 5)
    M5.Lcd.drawString(hi, 249, y_base + 5)
    M5.Lcd.drawString(rn, 414, y_base + 5)
    
    M5.Lcd.setFont(Widgets.FONTS.DejaVu24)
    M5.Lcd.drawString("o", 146 if len(lo)>1 else 126, y_base + 4)
    M5.Lcd.drawString("o", 304 if len(hi)>1 else 284, y_base + 4)

def draw_month_grid(target_date_str):
    rtc_iso, _, _ = get_local_now()
    rtc_y, rtc_m, rtc_d = [int(x) for x in rtc_iso.split('-')]
    y, m, _ = [int(x) for x in target_date_str.split('-')]
    M5.Lcd.setFont(JP_FONT); M5.Lcd.setTextColor(0x000000, 0xffffff)
    headers = ["日", "月", "火", "水", "木", "金", "土"]
    for i, h in enumerate(headers):
        M5.Lcd.drawString(h, CAL_X + i * (CELL_W + CELL_GAP) + 4, CAL_Y - 35)
    first_wd = (_weekday_from_ymd(y, m, 1) + 1) % 7
    days_in_m = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m-1]
    if m == 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)): days_in_m = 29
    for i in range(35):
        col, row = i % 7, i // 7
        day_val = (i - first_wd) + 1
        x, y_pos = CAL_X + col * (CELL_W + CELL_GAP), CAL_Y + row * (CELL_H + CELL_GAP)
        bg, txt = CLR_MONTH_CELL, CLR_FUTURE
        if day_val <= 0:
            pm = m - 1 if m > 1 else 12
            dim_p = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][pm-1]
            lbl, bg, txt = str(dim_p + day_val), CLR_OTHER_CELL, CLR_OTHER
        elif day_val > days_in_m:
            lbl, bg, txt = str(day_val - days_in_m), CLR_OTHER_CELL, CLR_OTHER
        else:
            lbl = str(day_val)
            if y == rtc_y and m == rtc_m:
                if day_val == rtc_d: bg, txt = CLR_TODAY_CELL, CLR_TODAY
                elif day_val < rtc_d: txt = CLR_PAST
            elif (y < rtc_y) or (y == rtc_y and m < rtc_m): txt = CLR_PAST
        M5.Lcd.fillRect(x, y_pos, CELL_W, CELL_H, bg)
        M5.Lcd.setFont(NUM_FONT); M5.Lcd.setTextColor(txt, bg)
        tw = M5.Lcd.textWidth(lbl); M5.Lcd.drawString(lbl, x + (CELL_W - tw) // 2, y_pos + 6)

def update_ui_events(events, target_date, clean=True):
    if clean:
        M5.Lcd.fillRect(35, Y_START_BASE, 480, 450, 0xffffff)
    day_evs = [e for e in events if target_date in str(e.get('start_date', '')).strip()]
    if not day_evs:
        try: Widgets.Image("/flash/res/img/img_noevents.png", (SCREEN_WIDTH - 400) // 2, Y_START_BASE + 100)
        except:
            M5.Lcd.setFont(Widgets.FONTS.DejaVu40); M5.Lcd.setTextColor(0x888888, 0xffffff)
            M5.Lcd.drawString("No events", 180, Y_START_BASE + 180)
        return
    all_day = [e for e in day_evs if str(e.get('all_day', '')).strip().lower() == "yes"]
    timed = sorted([e for e in day_evs if str(e.get('all_day', '')).strip().lower() != "yes"], key=lambda x: str(x.get('start_date', '')))
    y_off, rect_h = (45, RECT_H_BASE - 15) if all_day else (0, RECT_H_BASE)
    y_cursor = Y_START_BASE + y_off
    for color in PERIOD_COLORS:
        M5.Lcd.fillRect(L_RECT_X, y_cursor, L_RECT_W, rect_h, color)
        M5.Lcd.fillRect(R_RECT_X, y_cursor, R_RECT_W, rect_h, color); y_cursor += (rect_h + GAP)
    cur_y = Y_START_BASE + 5
    for e in all_day:
        M5.Lcd.setFont(TIME_FONT_SMALL); M5.Lcd.setTextColor(0x000000, 0xffffff)
        M5.Lcd.drawString("All-Day", L_RECT_X + 5, cur_y + 5)
        M5.Lcd.setFont(JP_FONT); M5.Lcd.drawString(e.get('title', ''), L_RECT_X + L_RECT_W + 15, cur_y); cur_y += 35
    last_y = Y_START_BASE + y_off - 30
    for e in timed:
        raw = str(e.get('start_date', '')).strip()
        t_str = raw.split('T')[1][:5] if 'T' in raw else raw.split(' ')[1][:5] if ' ' in raw else "00:00"
        try:
            h = int(t_str[:2]); p_idx = 0 if 5 <= h < 12 else 1 if 12 <= h < 18 else 2
            block_y = Y_START_BASE + y_off + (p_idx * (rect_h + GAP))
            final_y = block_y + 25 
            if final_y < last_y + 35: final_y = last_y + 35
            last_y = final_y
            M5.Lcd.setFont(TIME_FONT); M5.Lcd.setTextColor(0x000000, PERIOD_COLORS[p_idx])
            M5.Lcd.drawString(t_str, L_RECT_X + 5, final_y)
            M5.Lcd.setFont(JP_FONT); M5.Lcd.setTextColor(0x000000, 0xffffff); M5.Lcd.drawString(e.get('title', ''), L_RECT_X + L_RECT_W + 15, final_y)
        except: pass

def refresh_view(full=False):
    """Smart refresh. Erase all partial areas first, then draw modules."""
    y_base_weather = 820 + WEATHER_Y_OFFSET
    if full:
        Widgets.Image("/flash/res/img/bg_two_blocks_w.png", 0, 0)
        draw_month_grid(all_available_dates[current_date_idx] if all_available_dates else get_local_now()[0])
        M5.Lcd.setTextColor(WEATHER_TEXT_COLOR, 0xffffff)
        M5.Lcd.setFont(Widgets.FONTS.DejaVu24)
        M5.Lcd.drawString("min", 32, y_base_weather + 8)
        M5.Lcd.drawString("max", 188, y_base_weather + 8)
        M5.Lcd.drawString("rain", 353, y_base_weather + 8)
    else:
        M5.Lcd.fillRect(15, 0, LEFT_COLUMN_WIDTH - 15, 235, 0xffffff)
        M5.Lcd.fillRect(15, Y_START_BASE, 525, 710 - Y_START_BASE, 0xffffff)
        M5.Lcd.fillRect(88, y_base_weather + 5, 75, 45, 0xffffff)
        M5.Lcd.fillRect(249, y_base_weather + 5, 75, 45, 0xffffff)
        M5.Lcd.fillRect(414, y_base_weather + 5, 90, 45, 0xffffff) # Widened to 90px
        M5.Lcd.fillRect(BTN_L_X, BTN_Y, 480, BTN_H, 0xffffff)

    today_iso, _, _ = get_local_now()
    target_date = all_available_dates[current_date_idx] if all_available_dates else today_iso
    d_num, d_name = extract_date_info(target_date)
    
    center_x = 130 + TOP_LEFT_OFFSET_X
    M5.Lcd.setFont(Widgets.FONTS.DejaVu40); M5.Lcd.setTextColor(0x000000, 0xffffff) 
    M5.Lcd.drawString(d_name, center_x - (M5.Lcd.textWidth(d_name) // 2), 32)
    M5.Lcd.setFont(Widgets.FONTS.DejaVu72); tw = M5.Lcd.textWidth(d_num)
    try: Widgets.Label(d_num, center_x - int(tw * 1.3), 91, 1.0, 0x000000, 0xffffff, '/flash/res/font/Oxanium-SemiBold-190px.vlw')
    except: M5.Lcd.drawString(d_num, center_x - (tw // 2), 91)
    
    update_ui_events(cached_json.get("events", []) if cached_json else [], target_date, clean=False)
    update_ui_weather(target_date, clean=False)
    update_ui_footer(cached_json.get("generated_at", "") if cached_json else "")
    update_ui_status_icons()
    
    if all_available_dates and current_date_idx > 0: draw_day_button(BTN_L_X, BTN_Y, all_available_dates[current_date_idx-1])
    target_today_idx = all_available_dates.index(today_iso) if (all_available_dates and today_iso in all_available_dates) else 0
    if all_available_dates and current_date_idx != target_today_idx: Widgets.Image("/flash/res/img/img_back_today.png", BTN_C_X, BTN_Y)
    if all_available_dates and current_date_idx < len(all_available_dates) - 1: draw_day_button(BTN_R_X, BTN_Y, all_available_dates[current_date_idx+1])
    
    M5.update()

# ---------- Shared Utils ----------

def update_ui_status_icons():
    global last_wifi_state, last_batt_lvl
    wlan = network.WLAN(network.STA_IF)
    curr_wifi = wlan.isconnected()
    lvl = M5.Power.getBatteryLevel()
    curr_batt_bracket = 3 if lvl > 80 else 2 if lvl > 40 else 1 if lvl > 5 else 0
    
    if curr_wifi != last_wifi_state or curr_batt_bracket != last_batt_lvl:
        if curr_wifi:
            try: Widgets.Image("/flash/res/img/img_wifi.png", WIFI_X, ICON_Y)
            except: pass
        else:
            M5.Lcd.fillRect(WIFI_X + 5, ICON_Y + 6, 40, 40, 0xdddddd)
            
        b = "img_battery_3.png" if curr_batt_bracket == 3 else "img_battery_2.png" if curr_batt_bracket == 2 else "img_battery_1.png" if curr_batt_bracket == 1 else "img_battery_0.png"
        try: Widgets.Image("/flash/res/img/" + b, BATT_X, ICON_Y)
        except: pass
        
        last_wifi_state = curr_wifi
        last_batt_lvl = curr_batt_bracket

def extract_date_info(iso):
    p = iso.split('-')
    return str(int(p[2])), WEEKDAY_NAMES[_weekday_from_ymd(int(p[0]), int(p[1]), int(p[2]))]

def draw_day_button(x, y, date_str):
    d, name = extract_date_info(date_str)
    M5.Lcd.setTextColor(0x000000, 0xffffff); M5.Lcd.setFont(Widgets.FONTS.DejaVu24)
    M5.Lcd.drawString(name[:3], x + (BTN_W - M5.Lcd.textWidth(name[:3])) // 2, y)
    M5.Lcd.setFont(FONT_BTN_NUM); M5.Lcd.drawString(d, x + (BTN_W - M5.Lcd.textWidth(d)) // 2, y + 28)

def update_ui_footer(gen_at, is_pressed=False):
    bg_color = 0x000000 if is_pressed else 0xaaaaaa
    msg = "Update: " + (gen_at.replace('T', ' ')[:16] if gen_at else "Waiting...")
    M5.Lcd.fillRect(UPD_X - 20, UPD_Y - 5, UPD_W + 40, UPD_H + 10, bg_color)
    M5.Lcd.setFont(Widgets.FONTS.DejaVu18); M5.Lcd.setTextColor(0xffffff, bg_color); M5.Lcd.drawString(msg, UPD_X, UPD_Y)

def play_click_sound():
    try: M5.Speaker.tone(2000, 50) 
    except: pass

# ---------- Lifecycle ----------

def setup():
    global cached_json, last_activity_time
    M5.begin()
    wlan = network.WLAN(network.STA_IF); wlan.active(True)
    try:
        with open('/flash/calendar.json', 'r') as f: cached_json = json.load(f)
        update_state_from_json(); refresh_view(full=True)
    except: pass
    timeout = 10
    while not wlan.isconnected() and timeout > 0: time.sleep(1); timeout -= 1
    if wlan.isconnected():
        try: ntptime.settime()
        except: pass
        start_server()
    
    _, _, lt = get_local_now()
    if lt[3] == 0 and lt[4] < (MAINTENANCE_WINDOW // 60):
        last_activity_time = time.ticks_ms()
    else:
        last_activity_time = time.ticks_ms()

def loop():
    global current_date_idx, last_activity_time, full_refresh_done
    M5.update(); handle_incoming_request()
    
    elapsed = time.ticks_diff(time.ticks_ms(), last_activity_time)
    
    # 1. Maintenance Window Check (Midnight Update)
    _, _, lt = get_local_now()
    if lt[3] == 0 and lt[4] < (MAINTENANCE_WINDOW // 60):
        # We are in the window, keep server alive
        last_activity_time = time.ticks_ms()
        # Perform ONE full refresh at midnight to roll over grid
        if not full_refresh_done:
            refresh_view(full=True)
            full_refresh_done = True
    else:
        # Outside window, reset flag for next midnight
        full_refresh_done = False

    # 2. Idle Return Logic (Return to today if idle for 30s)
    today_iso, _, _ = get_local_now()
    target_today_idx = all_available_dates.index(today_iso) if (all_available_dates and today_iso in all_available_dates) else 0
    if current_date_idx != target_today_idx and elapsed > IDLE_TIMEOUT * 1000:
        current_date_idx = target_today_idx
        refresh_view(full=False)
        last_activity_time = time.ticks_ms()

    # 3. Deep Sleep Check (After 60s of true inactivity)
    if elapsed > SLEEP_TIMEOUT * 1000:
        enter_deep_sleep()

    # 4. Touch Logic
    if M5.Touch.getCount() > 0:
        last_activity_time = time.ticks_ms()
        tx, ty = M5.Touch.getX(), M5.Touch.getY(); clicked = False
        if BTN_Y <= ty <= BTN_Y + BTN_H:
            if BTN_L_X <= tx <= BTN_L_X + BTN_W and current_date_idx > 0: current_date_idx -= 1; clicked = True
            elif current_date_idx != target_today_idx and BTN_C_X <= tx <= BTN_C_X + BTN_W: current_date_idx = target_today_idx; clicked = True
            elif BTN_R_X <= tx <= BTN_R_X + BTN_W and current_date_idx < len(all_available_dates) - 1: current_date_idx += 1; clicked = True
        
        if clicked:
            play_click_sound()
            while M5.Touch.getCount() > 0: M5.update(); time.sleep(0.01)
            refresh_view(full=False)
            
    time.sleep(0.05)

if __name__ == "__main__":
    setup()
    while True: loop()
