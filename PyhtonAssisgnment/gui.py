import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import tkinter as tk
from tkinter import messagebox, filedialog
from datetime import datetime, timedelta
import threading, time, os, sys
from plyer import notification
import pygame
import pystray
from PIL import Image, ImageDraw, ImageFont
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import db
import tzlocal
import webbrowser
import requests, geocoder  # For weather lookup

CHECK_INTERVAL = 1.5
AUTO_REFRESH_INTERVAL = 60000  # 60 sec
WEATHER_REFRESH_INTERVAL = 900000  # 15 min

pygame.mixer.init()
is_playing = {"normal": False, "urgent": False}


# ---------------- SOUND HELPERS ----------------
def get_sound_path(urgent=False):
    key = 'sound_urgent' if urgent else 'sound_normal'
    path = db.get_setting(key, "")
    if path and os.path.exists(path):
        return path
    default = os.path.join(os.path.dirname(__file__), "urgent.wav" if urgent else "notify.wav")
    return default if os.path.exists(default) else None


def play_sound(urgent=False, loop=False):
    try:
        path = get_sound_path(urgent)
        if path and os.path.exists(path):
            pygame.mixer.music.load(path)
            pygame.mixer.music.play(-1 if loop or urgent else 0)
            is_playing["urgent" if urgent else "normal"] = True
        else:
            root = tk._default_root
            if root:
                root.bell()
    except Exception as e:
        print("[sound] play error:", e)


def stop_sound():
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass
    is_playing["normal"] = False
    is_playing["urgent"] = False


def toggle_test_sound(urgent, btn):
    tag = "urgent" if urgent else "normal"
    if is_playing[tag]:
        stop_sound()
        btn.config(text=f"Test {tag.capitalize()} Sound", bootstyle=INFO)
        return
    path = get_sound_path(urgent)
    if not path or not os.path.exists(path):
        messagebox.showerror("Error", f"No {tag.capitalize()} sound set. Use 'Set {tag.capitalize()} Sound'.")
        return
    play_sound(urgent)
    btn.config(text=f"Stop {tag.capitalize()} Sound", bootstyle=DANGER)

    def monitor():
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        is_playing[tag] = False
        btn.config(text=f"Test {tag.capitalize()} Sound", bootstyle=INFO)

    threading.Thread(target=monitor, daemon=True).start()


# ---------------- NOTIFICATIONS ----------------
def popup_alert(title, message, urgent=False):
    win = tk.Toplevel()
    win.title("TEND Notification")
    win.geometry("420x220")
    win.attributes("-topmost", True)
    frame = ttk.Frame(win, padding=16)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text=title, font=("Segoe UI", 14, "bold")).pack(pady=(2, 8))
    ttk.Label(frame, text=message, wraplength=380, justify="center").pack(pady=(0, 8))
    if urgent:
        ttk.Label(frame, text="URGENT ALERT", bootstyle=(DANGER, INVERSE)).pack(pady=(0, 8))

    def stop_all():
        stop_sound()
        try:
            win.destroy()
        except Exception:
            pass

    ttk.Button(frame, text="Stop Alert", bootstyle=(DANGER if urgent else INFO, OUTLINE), command=stop_all).pack(pady=6)
    play_sound(urgent, loop=urgent)
    win.protocol("WM_DELETE_WINDOW", stop_all)


def notify_desktop(title, message, urgent=False):
    try:
        notification.notify(
            title=("[URGENT] " + title) if urgent else title,
            message=message,
            app_name="TEND",
            timeout=6
        )
    except Exception:
        print("[notify] fallback:", title, message)
    threading.Thread(target=lambda: popup_alert(title, message, urgent), daemon=True).start()


# ---------------- TRAY ICON ----------------
def generate_tray_icon(path="tray_icon.png"):
    if os.path.exists(path):
        return path
    size = 128
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((16, 16, size - 16, size - 16), fill=(30, 144, 255, 255))
    draw.text((size // 2 - 8, size // 2 - 10), "T", fill="white", font=ImageFont.load_default())
    img.save(path)
    return path


class TrayThread(threading.Thread):
    def __init__(self, gui):
        super().__init__(daemon=True)
        self.gui = gui
        self.icon = None

    def run(self):
        try:
            path = generate_tray_icon("tray_icon.png")
            image = Image.open(path)
            menu = pystray.Menu(
                pystray.MenuItem("Show", self.on_show),
                pystray.MenuItem("Toggle Meeting Mode", self.on_toggle),
                pystray.MenuItem("Exit", self.on_exit)
            )
            self.icon = pystray.Icon("TEND", image, "TEND", menu)
            self.icon.run()
        except Exception as e:
            print("[tray] error:", e)

    def on_show(self, icon, item):
        self.gui.root.after(0, self.gui.show_window)

    def on_toggle(self, icon, item):
        self.gui.root.after(0, self.gui.toggle_meeting_mode)

    def on_exit(self, icon, item):
        self.gui.root.after(0, self.gui.on_close)

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass


# ---------------- DISPATCHER ----------------
class Dispatcher(threading.Thread):
    def __init__(self, stop_event, gui_ref):
        super().__init__(daemon=True)
        self.stop_event = stop_event
        self.gui_ref = gui_ref

    def run(self):
        while not self.stop_event.is_set():
            try:
                now = datetime.now()
                pending = db.get_pending_notifications()
                meeting = db.get_meeting_mode()
                for n in pending:
                    try:
                        target = datetime.strptime(n['time'], "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        db.mark_delivered(n['id'])
                        continue
                    if now >= target:
                        if (not meeting) or n['urgent']:
                            notify_desktop(n['title'], n['message'], urgent=n['urgent'])
                        db.mark_delivered(n['id'])
                        self.gui_ref.safe_refresh()
            except Exception as e:
                print("[Dispatcher] error:", e)
            self.stop_event.wait(CHECK_INTERVAL)


# ---------------- WEATHER ----------------
def get_weather_data():
    try:
        g = geocoder.ip('me')
        latlon = getattr(g, "latlng", None)
        if not latlon:
            raise ValueError("No coordinates")
        lat, lon = latlon
        city = g.city or "Your Location"
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            cw = r.json().get("current_weather", {})
            temp = cw.get("temperature")
            condition = "Clear" if cw.get("weathercode", 0) == 0 else "Cloudy"
            db.save_weather_cache(city, temp, condition)
            return city, temp, condition
    except Exception:
        return db.load_weather_cache()
    return "Offline", "N/A", "Unknown"


# ---------------- MAIN GUI ----------------
class TendApp:
    def __init__(self, root):
        self.root = root
        self.style = ttk.Style("darkly")
        self.root.title("TEND — Temporal Event Notification Dispatcher")
        self.root.geometry("1100x720")
        self.root.minsize(760, 520)
        self.stop_event = threading.Event()
        self.is_fullscreen = False

        # Header
        header = ttk.Frame(self.root, padding=(12, 8))
        header.pack(fill='x')
        ttk.Label(
            header,
            text="TEND — Temporal Event Notification Dispatcher",
            font=("Segoe UI", 18, "bold"),
            anchor='center',
            justify='center'
        ).pack(fill='x', pady=8)

        right = ttk.Frame(header)
        right.pack(side='right', padx=10)
        self.time_label = ttk.Label(right, font=("Segoe UI", 11))
        self.weather_label = ttk.Label(right, font=("Segoe UI", 10), bootstyle=INFO)
        self.time_label.pack(anchor='e')
        self.weather_label.pack(anchor='e')
        self.update_time()
        self.update_weather()

        # --- Tabs ---
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=6)
        dashboard_tab = ttk.Frame(notebook)
        upcoming_tab = ttk.Frame(notebook)
        notebook.add(dashboard_tab, text="Dashboard")
        notebook.add(upcoming_tab, text="Next 24 Hours")

        # --- Controls ---
        ctrl = ttk.Frame(dashboard_tab, padding=10)
        ctrl.pack(fill='x', padx=12, pady=(4, 6))
        self.title_var = tk.StringVar()
        self.msg_var = tk.StringVar()
        self.time_var = tk.StringVar()
        self.urgent_var = tk.IntVar()
        self.title_entry = ttk.Entry(ctrl, textvariable=self.title_var, width=28)
        self.msg_entry = ttk.Entry(ctrl, textvariable=self.msg_var, width=48)
        self.time_entry = ttk.Entry(ctrl, textvariable=self.time_var, width=26)

        placeholders = {
            self.title_entry: "Enter Title...",
            self.msg_entry: "Enter Message...",
            self.time_entry: "YYYY-MM-DD HH:MM:SS"
        }
        for ent, pl in placeholders.items():
            ent.insert(0, pl)
            ent.bind("<FocusIn>", lambda e, p=pl: self._clear_placeholder(e.widget, p))
            ent.bind("<FocusOut>", lambda e, p=pl: self._add_placeholder(e.widget, p))

        self.title_entry.grid(row=0, column=0, padx=6, pady=6)
        self.msg_entry.grid(row=0, column=1, padx=6, pady=6)
        self.time_entry.grid(row=0, column=2, padx=6, pady=6)
        ttk.Checkbutton(ctrl, text="Urgent (bypass DND)", variable=self.urgent_var).grid(row=0, column=3, padx=6)

        # --- Action buttons ---
        actions = ttk.Frame(dashboard_tab, padding=(12, 6))
        actions.pack(fill='x')
        self.test_normal_btn = ttk.Button(actions, text="Test Normal Sound", bootstyle=INFO)
        self.test_urgent_btn = ttk.Button(actions, text="Test Urgent Sound", bootstyle=INFO)
        self.test_normal_btn.config(command=lambda: toggle_test_sound(False, self.test_normal_btn))
        self.test_urgent_btn.config(command=lambda: toggle_test_sound(True, self.test_urgent_btn))

        ttk.Button(actions, text="Add Notification", bootstyle=SUCCESS, command=self.add_notification).pack(side='left', padx=6)
        ttk.Button(actions, text="Clear All Fields", bootstyle=SECONDARY, command=self.clear_fields).pack(side='left', padx=6)
        ttk.Button(actions, text="Toggle Meeting Mode", bootstyle=WARNING, command=self.toggle_meeting_mode).pack(side='left', padx=6)
        ttk.Button(actions, text="Set Normal Sound", bootstyle=SECONDARY, command=lambda: self.set_sound(False)).pack(side='left', padx=6)
        ttk.Button(actions, text="Set Urgent Sound", bootstyle=DANGER, command=lambda: self.set_sound(True)).pack(side='left', padx=6)
        self.test_normal_btn.pack(side='left', padx=6)
        self.test_urgent_btn.pack(side='left', padx=6)
        ttk.Button(actions, text="Toggle Fullscreen", bootstyle=LIGHT, command=self.toggle_fullscreen).pack(side='left', padx=6)

        # --- Dashboard ---
        main = ttk.Frame(dashboard_tab, padding=8)
        main.pack(fill='both', expand=True, padx=12, pady=8)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        left = ttk.Labelframe(main, text="Analytics (last 7 days)")
        left.grid(row=0, column=0, sticky='nsew', padx=6, pady=6)
        self.fig = Figure(figsize=(6, 3), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=left)
        self.canvas.get_tk_widget().pack(fill='both', expand=True, padx=6, pady=6)

        right = ttk.Labelframe(main, text="Upcoming Notifications")
        right.grid(row=0, column=1, sticky='nsew', padx=6, pady=6)
        self.up_list = tk.Listbox(right, font=("Consolas", 10))
        self.up_list.pack(fill='both', expand=True, padx=6, pady=6)

        # --- Next 24h Tab ---
        search_frame = ttk.Frame(upcoming_tab, padding=6)
        search_frame.pack(fill='x')
        ttk.Label(search_frame, text="Search:", font=("Segoe UI", 10)).pack(side="left", padx=4)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=50)
        self.search_entry.pack(side="left", padx=4)
        ttk.Button(search_frame, text="Search", bootstyle=INFO, command=self.refresh_next_24h).pack(side="left", padx=4)
        ttk.Button(search_frame, text="Clear", bootstyle=SECONDARY, command=lambda: (self.search_var.set(""), self.refresh_next_24h())).pack(side="left")
        self.tree = ttk.Treeview(upcoming_tab, columns=("time", "title", "urgent"), show="headings", height=15)
        self.tree.heading("time", text="Time")
        self.tree.heading("title", text="Title / Message")
        self.tree.heading("urgent", text="Urgent")
        self.tree.column("time", width=220)
        self.tree.column("title", width=700)
        self.tree.column("urgent", width=80, anchor="center")
        self.tree.pack(fill='both', expand=True, padx=10, pady=10)
        vsb = ttk.Scrollbar(upcoming_tab, orient="vertical", command=self.tree.yview)
        vsb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=vsb.set)

        # --- Threads ---
        self.dispatcher = Dispatcher(self.stop_event, self)
        self.dispatcher.start()
        self.tray = TrayThread(self)
        self.tray.start()

        # --- Initial Refresh ---
        self.refresh_dashboard()
        self.refresh_upcoming()
        self.refresh_next_24h()
        self.auto_refresh()

        # --- Footer ---
        footer = ttk.Frame(self.root, padding=(10, 5))
        footer.pack(fill='x', side='bottom')
        ttk.Separator(footer, orient='horizontal').pack(fill='x', pady=3)

        def open_link_popup(event=None):
            p = tk.Toplevel()
            p.title("Authors / LinkedIn")
            p.geometry("420x120")
            p.attributes("-topmost", True)
            f = ttk.Frame(p, padding=12)
            f.pack(fill='both', expand=True)
            ttk.Label(f, text="Made by Siddhartha and Piyush", font=("Segoe UI", 11, "italic")).pack(pady=(0, 8))
            btn_frame = ttk.Frame(f)
            btn_frame.pack()
            ttk.Button(btn_frame, text="Siddhartha - LinkedIn", command=lambda: webbrowser.open_new_tab("https://www.linkedin.com/in/siddhartha-raj23/"), bootstyle=INFO).pack(side='left', padx=8)
            ttk.Button(btn_frame, text="Piyush - LinkedIn", command=lambda: webbrowser.open_new_tab("https://www.linkedin.com/in/piyushnarayan/"), bootstyle=INFO).pack(side='left', padx=8)
            ttk.Button(f, text="Close", command=p.destroy, bootstyle=SECONDARY).pack(pady=(8, 0))
            p.transient(self.root)
            p.grab_set()

        footer_label = ttk.Label(
            footer,
            text="Made by Siddhartha and Piyush",
            font=("Segoe UI", 10, "italic", "underline"),
            anchor='center',
            justify='center',
            foreground="white",
            cursor="hand2"
        )
        footer_label.pack(fill='x')
        footer_label.bind("<Button-1>", open_link_popup)

        # --- Bindings ---
        self.root.bind("<Escape>", lambda e: self._exit_fullscreen_if_needed())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- Live clock ---
    def update_time(self):
        try:
            tz_name = tzlocal.get_localzone_name()
        except Exception:
            tz_name = "Local"
        now = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        self.time_label.config(text=f"{now}  ({tz_name})")
        self.root.after(1000, self.update_time)

    # --- Weather update ---
    def update_weather(self):
        try:
            city, temp, cond = get_weather_data()
            self.weather_label.config(text=f"{city}: {temp}°C, {cond}")
        except Exception:
            self.weather_label.config(text="Offline Weather")
        self.root.after(WEATHER_REFRESH_INTERVAL, self.update_weather)

    # --- Refreshers / Helpers ---
    def auto_refresh(self):
        self.safe_refresh()
        self.root.after(AUTO_REFRESH_INTERVAL, self.auto_refresh)

    def safe_refresh(self):
        self.root.after(0, lambda: (self.refresh_dashboard(), self.refresh_upcoming(), self.refresh_next_24h()))

    def refresh_dashboard(self):
        data = db.notifications_count_last_n_days(7)
        self.ax.clear()
        self.ax.bar(list(data.keys()), list(data.values()), color="#4cc3f8")
        self.ax.set_ylabel("Count")
        self.ax.tick_params(axis='x', rotation=45)
        self.fig.tight_layout()
        self.canvas.draw()

    def refresh_upcoming(self):
        self.up_list.delete(0, tk.END)
        events = db.upcoming_events(50)
        if not events:
            self.up_list.insert(tk.END, "No upcoming notifications")
        else:
            for e in events:
                tag = "[URGENT] " if e['urgent'] else ""
                self.up_list.insert(tk.END, f"{e['time']}  {tag}{e['title']}")

    def refresh_next_24h(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        now = datetime.now()
        next_24h = now + timedelta(hours=24)
        events = db.get_notifications_between(now, next_24h)
        q = (self.search_var.get() or "").lower().strip()
        if q:
            events = [e for e in events if q in e['title'].lower() or q in e['message'].lower()]
        if not events:
            self.tree.insert("", "end", values=("—", "No matching notifications", "—"))
            return
        for e in events:
            self.tree.insert("", "end", values=(e["time"], e["title"], "Yes" if e["urgent"] else "No"))

    # --- Actions ---
    def add_notification(self):
        title = self.title_entry.get().strip()
        msg = self.msg_entry.get().strip()
        time_input = self.time_entry.get().strip()
        for e in [self.title_entry, self.msg_entry, self.time_entry]:
            e.configure(bootstyle="default")
        errors = []
        if not title or title.lower().startswith("enter title"):
            self.title_entry.configure(bootstyle="danger")
            errors.append("Title")
        if not msg or msg.lower().startswith("enter message"):
            self.msg_entry.configure(bootstyle="danger")
            errors.append("Message")
        try:
            dt = datetime.strptime(time_input, "%Y-%m-%d %H:%M:%S")
        except Exception:
            self.time_entry.configure(bootstyle="danger")
            errors.append("Time Format (YYYY-MM-DD HH:MM:SS)")
        if errors:
            messagebox.showerror("Missing or Invalid Fields", "Please fill correctly:\n- " + "\n- ".join(errors))
            return
        db.add_notification(title, msg, dt.strftime("%Y-%m-%d %H:%M:%S"), bool(self.urgent_var.get()))
        messagebox.showinfo("Scheduled", f"Notification set for {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        self.clear_fields()
        self.safe_refresh()

    def clear_fields(self):
        self.title_var.set(""); self.msg_var.set(""); self.time_var.set(""); self.urgent_var.set(0)
        self.title_entry.delete(0, tk.END); self.msg_entry.delete(0, tk.END); self.time_entry.delete(0, tk.END)
        self.title_entry.insert(0, "Enter Title..."); self.msg_entry.insert(0, "Enter Message..."); self.time_entry.insert(0, "YYYY-MM-DD HH:MM:SS")

    def _clear_placeholder(self, widget, text):
        if widget.get() == text:
            widget.delete(0, tk.END)

    def _add_placeholder(self, widget, text):
        if not widget.get().strip():
            widget.insert(0, text)

    def set_sound(self, urgent=False):
        path = filedialog.askopenfilename(title="Select Audio File",
                                          filetypes=[("Audio Files", "*.wav *.mp3 *.ogg *.flac *.aac *.m4a"), ("All Files", "*.*")])
        if not path: return
        db.set_setting('sound_urgent' if urgent else 'sound_normal', path)
        messagebox.showinfo("Saved", f"{'Urgent' if urgent else 'Normal'} sound set!\n{path}")

    def toggle_meeting_mode(self):
        db.set_meeting_mode(not db.get_meeting_mode())
        messagebox.showinfo("Meeting Mode", f"Meeting Mode: {'ON' if db.get_meeting_mode() else 'OFF'}")
        self.safe_refresh()

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)

    def _exit_fullscreen_if_needed(self):
        if self.is_fullscreen:
            self.is_fullscreen = False
            self.root.attributes("-fullscreen", False)

    def show_window(self):
        self.root.deiconify(); self.root.lift(); self.root.focus_force()

    def on_close(self):
        self.stop_event.set()
        stop_sound()
        try:
            self.tray.stop()
        except Exception:
            pass
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        sys.exit(0)
