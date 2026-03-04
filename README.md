# M5Paper S3 Dynamic Calendar & Planner

A sophisticated MicroPython-based calendar and event planner designed for the M5Paper S3 E-Ink display. This project features a dual-pane interface: a dynamic 7x5 month grid on the right and a detailed daily schedule on the left.

## 🚀 Key Features

- **Dual-Pane UI**: Displays a monthly overview and a detailed daily list of events simultaneously.
- **Dynamic Scheduling**: Supports both **All-Day** events and timed events categorized by period (Morning, Afternoon, Evening).
- **Weather Integration**: Displays high/low temperatures and rain chances for the selected date.
- **Direct Update via iPhone**: Runs a local HTTP server to receive JSON data directly from an iPhone Shortcut (no external API keys required on the device).
- **Smart Power & E-Ink Management**: 
  - Optimized rendering for fast screen refreshes.
  - Automatic return to "Today" view after 30 seconds of inactivity.
  - Long-press shortcuts for WiFi status and raw JSON debugging.
- **Hardware Integration**: Real-time battery level icons and WiFi connection status.

## 🛠 Setup & Installation

### 1. Hardware Preparation
Ensure your M5Paper S3 is running **MicroPython** (M5Stack official firmware).

### 2. Assets Upload
Upload the following files to your device's flash memory:
- **Fonts**: Place your `.vlw` fonts in `/flash/res/font/`.
- **Images**: Place your `.png` icons in `/flash/res/img/`.
  - `bg_two_blocks_w.png` (Background)
  - `img_back_today.png` (Home/Today Icon)
  - `img_wifi.png`
  - `img_battery_0.png` through `img_battery_3.png`

### 3. Deployment
Copy `calendar_dynamic.py` to your device and run it as `main.py` if you want it to start automatically on boot.

## 📲 Data Synchronization
Data is pushed to the device via a custom iPhone Shortcut. For detailed instructions on how to set up the automation, see:
👉 [**iPhone Shortcut Setup Guide**](docs/shortcut_setup.md)

## ⌨️ Shortcuts (On Device)
- **Navigation**: Use the bottom buttons to cycle through available dates.
- **Update Button (Long Press)**: View raw JSON data for debugging.
- **WiFi Icon (Long Press)**: View the device IP address and network status.
