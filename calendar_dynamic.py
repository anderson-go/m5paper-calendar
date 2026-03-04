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
IDLE_TIMEOUT = 30  

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

# Colors
PERIOD_COLORS = [0xcccccc, 0xaaaaaa, 0x888888]
WEATHER_TEXT_COLOR = 0x777777

# Global State
all_available_dates = []  
current_date_idx = 0      
cached_json = None        
last_activity_time = 0    
server_socket = None

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
    refresh_view()

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

def show_debug_json():
    M5.Lcd.fillScreen(0xffffff)
    M5.Lcd.setFont(Widgets.FONTS.DejaVu12); M5.Lcd.setTextColor(0x000000, 0xffffff)
    try:
        with open('/flash/calendar.json', 'r') as f:
            content = f.read()
            line = 0
            for i in range(0, len(content), 65):
                M5.Lcd.drawString(content[i:i+65], 10, 30 + line*15)
                line += 1
                if line > 55: break
    except: M5.Lcd.drawString("File not found", 10, 30)
    M5.Lcd.drawString("--- TAP TO RETURN ---", 10, 920)
    M5.update()
    wait_for_tap_to_return()

# ---------- Networking ----------

def handle_incoming_request():
    global cached_json
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
                    play_click_sound(); refresh_view()
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
    if not cached_json: return
    today_iso, _, _ = get_local_now()
    dts = {today_iso}
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

def update_ui_weather(target_date):
    """Refactored to use Direct LCD drawing for speed and reliability."""
    y_base = 820 + WEATHER_Y_OFFSET
    M5.Lcd.fillRect(30, y_base, 480, 65, 0xffffff) # Background clear
    
    if not cached_json or "weather_ls" not in cached_json: return
    
    try:
        # Calculate Index relative to JSON generation date
        json_today = cached_json["generated_at"].split('T')[0]
        t_p, j_p = [int(x) for x in target_date.split('-')], [int(x) for x in json_today.split('-')]
        idx = int((_time.mktime((t_p[0],t_p[1],t_p[2],0,0,0,0,0)) - _time.mktime((j_p[0],j_p[1],j_p[2],0,0,0,0,0))) / 86400)
        
        w_ls = cached_json["weather_ls"][0]
        # Safety clamp to prevent crash if date is out of range
        idx = max(0, min(idx, len(w_ls["high_ls"]) - 1))
        
        hi = w_ls["high_ls"][idx].replace("°C", "").strip()
        lo = w_ls["low_ls"][idx].replace("°C", "").strip()
        rn = str(int(w_ls["rain_chance_ls"][idx] * 100)) + "%"
        
        M5.Lcd.setTextColor(WEATHER_TEXT_COLOR, 0xffffff)
        
        # Draw Min
        M5.Lcd.setFont(Widgets.FONTS.DejaVu24); M5.Lcd.drawString("min", 32, y_base + 8)
        M5.Lcd.setFont(Widgets.FONTS.DejaVu40); M5.Lcd.drawString(lo, 88, y_base + 5)
        M5.Lcd.setFont(Widgets.FONTS.DejaVu24); M5.Lcd.drawString("o", 146 if len(lo)>1 else 126, y_base + 4)
        
        # Draw Max
        M5.Lcd.setFont(Widgets.FONTS.DejaVu24); M5.Lcd.drawString("max", 188, y_base + 8)
        M5.Lcd.setFont(Widgets.FONTS.DejaVu40); M5.Lcd.drawString(hi, 249, y_base + 5)
        M5.Lcd.setFont(Widgets.FONTS.DejaVu24); M5.Lcd.drawString("o", 304 if len(hi)>1 else 284, y_base + 4)
        
        # Draw Rain
        M5.Lcd.setFont(Widgets.FONTS.DejaVu24); M5.Lcd.drawString("rain", 353, y_base + 8)
        M5.Lcd.setFont(Widgets.FONTS.DejaVu40); M5.Lcd.drawString(rn, 414, y_base + 5)
    except: pass

def draw_month_grid(target_date_str):
    rtc_iso, _, _ = get_local_now()
    rtc_y, rtc_m, rtc_d = [int(x) for x in rtc_iso.split('-')]
    y, m, _ = [int(x) for x in target_date_str.split('-')]
    
    headers = ["日", "月", "火", "水", "木", "金", "土"]
    M5.Lcd.setFont(JP_FONT); M5.Lcd.setTextColor(0x000000, 0xffffff)
    for i, h in enumerate(headers):
        M5.Lcd.drawString(h, CAL_X + i * (CELL_W + CELL_GAP) + 4, CAL_Y - 35)

    first_wd = (_weekday_from_ymd(y, m, 1) + 1) % 7
    days_in_m = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m-1]
    if m == 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)): days_in_m = 29
    
    for i in range(35):
        col, row = i % 7, i // 7
        day_val = (i - first_wd) + 1
        x = CAL_X + col * (CELL_W + CELL_GAP)
        y_pos = CAL_Y + row * (CELL_H + CELL_GAP)
        bg, txt = CLR_MONTH_CELL, CLR_FUTURE
        if day_val <= 0:
            pm = m - 1 if m > 1 else 12
            py = y if m > 1 else y - 1
            dim_p = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][pm-1]
            if pm == 2 and (py % 4 == 0 and (py % 100 != 0 or py % 400 == 0)): dim_p = 29
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

def update_ui_events(events, target_date):
    M5.Lcd.fillRect(35, Y_START_BASE, 480, 450, 0xffffff)
    day_evs = [e for e in events if target_date in str(e.get('start_date', '')).strip()]
    all_day = [e for e in day_evs if str(e.get('all_day', '')).strip().lower() == "yes"]
    timed = sorted([e for e in day_evs if str(e.get('all_day', '')).strip().lower() != "yes"], key=lambda x: str(x.get('start_date', '')))
    if not day_evs:
        M5.Lcd.setFont(Widgets.FONTS.DejaVu40); M5.Lcd.setTextColor(0x888888, 0xffffff)
        M5.Lcd.drawString("No events", (SCREEN_WIDTH - M5.Lcd.textWidth("No events")) // 2, Y_START_BASE + 180)
        return
    y_off, rect_h = (45, RECT_H_BASE - 15) if all_day else (0, RECT_H_BASE)
    y_cursor = Y_START_BASE + y_off
    for color in [0xcccccc, 0xaaaaaa, 0x888888]:
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
            M5.Lcd.setFont(TIME_FONT); M5.Lcd.setTextColor(0x000000, [0xcccccc, 0xaaaaaa, 0x888888][p_idx])
            M5.Lcd.drawString(t_str, L_RECT_X + 5, final_y)
            M5.Lcd.setFont(JP_FONT); M5.Lcd.setTextColor(0x000000, 0xffffff); M5.Lcd.drawString(e.get('title', ''), L_RECT_X + L_RECT_W + 15, final_y)
        except: pass

def refresh_view():
    if not cached_json or not all_available_dates: return
    Widgets.Image("/flash/res/img/bg_two_blocks_w.png", 0, 0)
    today_iso, _, _ = get_local_now()
    target_date = all_available_dates[current_date_idx]
    d_num, d_name = extract_date_info(target_date)
    center_x = 130 + TOP_LEFT_OFFSET_X
    M5.Lcd.setFont(Widgets.FONTS.DejaVu40); M5.Lcd.setTextColor(0x000000, 0xffffff) 
    M5.Lcd.drawString(d_name, center_x - (M5.Lcd.textWidth(d_name) // 2), 32)
    M5.Lcd.setFont(Widgets.FONTS.DejaVu72); tw = M5.Lcd.textWidth(d_num)
    try: Widgets.Label(d_num, center_x - int(tw * 1.3), 91, 1.0, 0x000000, 0xffffff, '/flash/res/font/Oxanium-SemiBold-190px.vlw')
    except: M5.Lcd.drawString(d_num, center_x - (tw // 2), 91)
    draw_month_grid(target_date)
    update_ui_events(cached_json.get("events", []), target_date)
    update_ui_weather(target_date)
    update_ui_footer(cached_json.get("generated_at", ""))
    update_ui_status_icons()
    M5.Lcd.fillRect(BTN_L_X, BTN_Y, 480, BTN_H, 0xffffff)
    if current_date_idx > 0: draw_day_button(BTN_L_X, BTN_Y, all_available_dates[current_date_idx-1])
    target_today_idx = all_available_dates.index(today_iso) if today_iso in all_available_dates else 0
    if current_date_idx != target_today_idx: Widgets.Image("/flash/res/img/img_back_today.png", BTN_C_X, BTN_Y)
    if current_date_idx < len(all_available_dates) - 1: draw_day_button(BTN_R_X, BTN_Y, all_available_dates[current_date_idx+1])
    M5.update()

# ---------- Shared Utils ----------

def update_ui_status_icons():
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        try: Widgets.Image("/flash/res/img/img_wifi.png", WIFI_X, ICON_Y)
        except: pass
    try:
        lvl = M5.Power.getBatteryLevel()
        b = "img_battery_3.png" if lvl > 80 else "img_battery_2.png" if lvl > 40 else "img_battery_1.png" if lvl > 5 else "img_battery_0.png"
        Widgets.Image("/flash/res/img/" + b, BATT_X, ICON_Y)
    except: pass

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

# ---------- Setup / Loop ----------

def setup():
    global cached_json, last_activity_time
    M5.begin()
    wlan = network.WLAN(network.STA_IF); wlan.active(True)
    try:
        with open('/flash/calendar.json', 'r') as f: cached_json = json.load(f)
        update_state_from_json(); refresh_view()
    except: pass
    timeout = 15
    while not wlan.isconnected() and timeout > 0: time.sleep(1); timeout -= 1
    if wlan.isconnected():
        try: ntptime.settime()
        except: pass
        start_server()
    last_activity_time = time.ticks_ms()

def play_click_sound():
    try: M5.Speaker.tone(2000, 50) 
    except: pass

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

def loop():
    global current_date_idx, last_activity_time
    M5.update(); handle_incoming_request()
    today_iso, _, _ = get_local_now()
    target_today_idx = all_available_dates.index(today_iso) if (cached_json and today_iso in all_available_dates) else 0
    if current_date_idx != target_today_idx and time.ticks_diff(time.ticks_ms(), last_activity_time) > IDLE_TIMEOUT * 1000:
        current_date_idx = target_today_idx; refresh_view(); last_activity_time = time.ticks_ms()
    if M5.Touch.getCount() > 0:
        last_activity_time = time.ticks_ms(); tx, ty = M5.Touch.getX(), M5.Touch.getY(); clicked = False
        if BTN_Y <= ty <= BTN_Y + BTN_H:
            if BTN_L_X <= tx <= BTN_L_X + BTN_W and current_date_idx > 0: current_date_idx -= 1; clicked = True
            elif current_date_idx != target_today_idx and BTN_C_X <= tx <= BTN_C_X + BTN_W: current_date_idx = target_today_idx; clicked = True
            elif BTN_R_X <= tx <= BTN_R_X + BTN_W and current_date_idx < len(all_available_dates) - 1: current_date_idx += 1; clicked = True
        elif UPD_Y - 10 <= ty <= UPD_Y + UPD_H and UPD_X <= tx <= UPD_X + UPD_W:
            start_p = time.ticks_ms()
            while M5.Touch.getCount() > 0:
                M5.update(); handle_incoming_request()
                if time.ticks_diff(time.ticks_ms(), start_p) > 2000: play_click_sound(); show_debug_json(); return
                time.sleep(0.05)
        elif ICON_Y - 10 <= ty <= 960 and WIFI_X - 10 <= tx <= 540:
            start_p = time.ticks_ms()
            while M5.Touch.getCount() > 0:
                M5.update(); handle_incoming_request()
                if time.ticks_diff(time.ticks_ms(), start_p) > 2000: play_click_sound(); show_wifi_info(); return
                time.sleep(0.05)
        if clicked:
            play_click_sound()
            while M5.Touch.getCount() > 0: M5.update(); handle_incoming_request(); time.sleep(0.01)
            refresh_view()
    time.sleep(0.05)

if __name__ == "__main__":
    setup()
    while True: loop()