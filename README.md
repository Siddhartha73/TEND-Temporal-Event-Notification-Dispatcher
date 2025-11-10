TEND — Temporal Event Notification Dispatcher

TEND is a desktop-based smart notification manager that helps you organize and manage time-bound reminders, alerts, and events with real-time notifications, sound alerts, and weather integration.  
It’s designed for productivity enthusiasts, students, and professionals who want a lightweight yet intelligent alerting system.

---
 🌟 Key Features

**Smart Notifications**  
  Schedule alerts with title, message, time, and urgency level.

- **Urgent vs Normal Alerts**  
  Urgent notifications bypass meeting mode (Do Not Disturb) and repeat until dismissed.

- **Custom Sounds**  
  Set custom `.wav` or `.mp3` alert sounds for both normal and urgent events.

- **Meeting Mode (DND)**  
  Quickly enable/disable meeting mode to temporarily mute non-urgent alerts.

- **Weather Integration**  
  Automatically detects your location and displays live weather updates using Open-Meteo API.

- **Analytics Dashboard**  
  Visual chart of your scheduled notifications over the past 7 days.

- **Upcoming & 24-Hour View**  
  Easily browse or search all pending notifications and events.

- **System Tray Integration**  
  Background tray icon for quick actions (Show, Toggle Meeting Mode, Exit).

- **Persistent Data**  
  All reminders and settings are stored locally using SQLite — no internet required.

---

## 🧰 Tech Stack

| Component | Technology |
|------------|-------------|
| **Language** | Python 3.10+ |
| **GUI Framework** | [ttkbootstrap](https://ttkbootstrap.readthedocs.io/en/latest/) |
| **Database** | SQLite (via `sqlite3`) |
| **Notification System** | [plyer](https://github.com/kivy/plyer) + Tkinter popup |
| **Sound System** | [pygame](https://www.pygame.org/) |
| **System Tray** | [pystray](https://pypi.org/project/pystray/) |
| **Weather API** | [Open-Meteo](https://open-meteo.com/) |
| **Graphs/Charts** | Matplotlib |

---

## 🖥️ Project Structure

TEND/
│
├── main.py # Entry point (launches splash + main GUI)
├── gui.py # Full GUI and event dispatcher logic
├── db.py # Database helper module (SQLite)
├── notify.wav # Default normal alert sound
├── urgent.wav # Default urgent alert sound
├── logo.png / logo.jpeg # App logo (optional)
├── tray_icon.png # Generated system tray icon
├── requirements.txt # Python dependencies
└── README.md # Documentation
