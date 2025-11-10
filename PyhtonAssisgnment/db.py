import sqlite3
from datetime import datetime, timedelta
import os

# Database file path (SQLite will auto-create)
DB_PATH = os.path.join(os.path.dirname(__file__), "tend.db")


# ---------- DATABASE CONNECTION ----------
def get_conn():
    return sqlite3.connect(DB_PATH)


# ---------- INITIALIZE DATABASE ----------
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Table for notifications (alerts/reminders)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            message TEXT,
            time TEXT,
            urgent INTEGER DEFAULT 0,
            delivered INTEGER DEFAULT 0
        )
    """)

    # Table for global settings / preferences
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Table for calendar events (future integration)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            uid TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            start TEXT,
            end TEXT
        )
    """)

    conn.commit()
    conn.close()


# ---------- SETTINGS (GENERIC) ----------
def get_setting(key, default=None):
    """Get stored setting by key, or default if not set."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key, value):
    """Insert or update a setting key-value pair."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


# ---------- NOTIFICATIONS ----------
def add_notification(title, message, time_str, urgent=False):
    """Add a new notification to DB."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO notifications (title, message, time, urgent, delivered)
        VALUES (?, ?, ?, ?, 0)
    """, (title, message, time_str, int(urgent)))
    conn.commit()
    nid = cur.lastrowid
    conn.close()
    return nid


def get_pending_notifications():
    """Get all notifications not yet delivered."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, title, message, time, urgent FROM notifications WHERE delivered=0 ORDER BY time ASC")
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": r[0], "title": r[1], "message": r[2], "time": r[3], "urgent": bool(r[4])}
        for r in rows
    ]


def mark_delivered(notification_id):
    """Mark notification as delivered."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE notifications SET delivered=1 WHERE id=?", (notification_id,))
    conn.commit()
    conn.close()


def notifications_count_last_n_days(days=7):
    """Return count of notifications created per day for last N days."""
    conn = get_conn()
    cur = conn.cursor()
    data = {}
    for i in range(days - 1, -1, -1):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        cur.execute("SELECT COUNT(*) FROM notifications WHERE date(time)=?", (date,))
        data[date] = cur.fetchone()[0]
    conn.close()
    return data


def upcoming_events(limit=50):
    """List next N upcoming undelivered notifications."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT title, time, urgent FROM notifications WHERE delivered=0 ORDER BY time ASC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return [{"title": r[0], "time": r[1], "urgent": bool(r[2])} for r in rows]


def get_notifications_between(start_dt, end_dt):
    """Get undelivered notifications within given datetime range."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, message, time, urgent FROM notifications "
        "WHERE delivered=0 AND datetime(time) BETWEEN ? AND ? ORDER BY time ASC",
        (start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S"))
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": r[0], "title": r[1], "message": r[2], "time": r[3], "urgent": bool(r[4])}
        for r in rows
    ]


# ---------- MEETING MODE ----------
def get_meeting_mode():
    """Return True if meeting mode is ON, else False."""
    return bool(int(get_setting("meeting_mode", "0")))


def set_meeting_mode(val: bool):
    """Turn meeting mode ON or OFF."""
    set_setting("meeting_mode", "1" if val else "0")


# ---------- WEATHER CACHE ----------
def save_weather_cache(city, temp, condition):
    """Save last known weather info for offline use."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("weather_cache_city", city or "Unknown"))
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("weather_cache_temp", str(temp) if temp is not None else "N/A"))
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("weather_cache_condition", condition or "Unknown"))
        conn.commit()
        conn.close()
    except Exception as e:
        print("[weather-cache] save error:", e)


def load_weather_cache():
    """Return cached weather info tuple (city, temp, condition)."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM settings WHERE key LIKE 'weather_cache_%'")
        data = dict(cur.fetchall())
        conn.close()
        return (
            data.get("weather_cache_city", "Offline Mode"),
            data.get("weather_cache_temp", "N/A"),
            data.get("weather_cache_condition", "Unknown")
        )
    except Exception as e:
        print("[weather-cache] load error:", e)
        return "Offline Mode", "N/A", "Unknown"


# ---------- SOUND SETTINGS ----------
def get_sound_setting(urgent=False):
    """Retrieve sound file path for normal or urgent alerts."""
    key = "sound_urgent" if urgent else "sound_normal"
    return get_setting(key, "")


def set_sound_setting(path, urgent=False):
    """Save sound file path for normal or urgent alerts."""
    key = "sound_urgent" if urgent else "sound_normal"
    set_setting(key, path)
