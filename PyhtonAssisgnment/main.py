import importlib.util
import sys
import os
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import PhotoImage
import threading
import time
from gui import TendApp, get_weather_data
import db


# ---------- Splash Screen ----------
class SplashScreen:
    def __init__(self, parent):
        self.parent = parent
        self.splash = ttk.Toplevel()
        self.splash.overrideredirect(True)      # Hide window border
        self.splash.attributes("-topmost", True)
        self.splash.configure(cursor="watch")

        # Center window
        width, height = 480, 300
        screen_width = self.splash.winfo_screenwidth()
        screen_height = self.splash.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.splash.geometry(f"{width}x{height}+{x}+{y}")

        frame = ttk.Frame(self.splash, padding=20)
        frame.pack(fill="both", expand=True)

        # Load logo
        logo_path_jpg = os.path.join(os.path.dirname(__file__), "logo.jpeg")
        logo_path_png = os.path.join(os.path.dirname(__file__), "logo.png")
        logo_path = logo_path_png if os.path.exists(logo_path_png) else logo_path_jpg

        if os.path.exists(logo_path):
            try:
                self.logo = PhotoImage(file=logo_path)
                ttk.Label(frame, image=self.logo).pack(pady=8)
            except Exception:
                ttk.Label(frame, text="TEND", font=("Segoe UI", 28, "bold")).pack(pady=30)
        else:
            ttk.Label(frame, text="TEND", font=("Segoe UI", 28, "bold")).pack(pady=30)

        ttk.Label(frame, text="Temporal Event Notification Dispatcher",
                  font=("Segoe UI", 12, "italic")).pack(pady=4)

        # Progress bar and status text
        self.progress = ttk.Progressbar(frame, bootstyle=INFO, mode="determinate", length=300)
        self.progress.pack(pady=20)
        self.status_label = ttk.Label(frame, text="Initializing...", font=("Segoe UI", 10))
        self.status_label.pack(pady=4)

    # Start splash animation and preload tasks
    def start(self, on_complete, preload_fn=None, preload_timeout=8):
        def animate_and_preload():
            try:
                for i in range(101):
                    time.sleep(0.02)
                    self.progress["value"] = i
                    self.status_label.config(text=f"Loading... {i}%")
                    try:
                        self.splash.update_idletasks()
                    except Exception:
                        pass
                time.sleep(0.15)

                # Run preload function if provided
                if preload_fn:
                    finished = threading.Event()

                    def run_preload():
                        try:
                            preload_fn()
                        except Exception as e:
                            print("[preload] error:", e)
                        finally:
                            finished.set()

                    t = threading.Thread(target=run_preload, daemon=True)
                    t.start()
                    t.join(preload_timeout)
                    if not finished.is_set():
                        print(f"[preload] timed out after {preload_timeout}s")

            except Exception as e:
                print("[SplashScreen] Error:", e)

            finally:
                try:
                    self.splash.destroy()
                except Exception:
                    pass
                try:
                    on_complete()
                except Exception as e:
                    print("[SplashScreen] on_complete error:", e)

        threading.Thread(target=animate_and_preload, daemon=True).start()


# ---------- Launch Main GUI ----------
def launch_main_gui(root):
    try:
        app = TendApp(root)
        root.deiconify()
        root.focus_force()
    except Exception as e:
        print("❌ Error launching main GUI:", e)
        import traceback
        traceback.print_exc()


# ---------- Main Function ----------
def main():
    # Initialize database
    try:
        db.init_db()
        print("✅ Database initialized successfully at:", os.path.abspath(db.DB_PATH))
    except Exception as e:
        print("❌ Database initialization failed:", e)

    # Create hidden root window
    root = ttk.Window(themename="darkly")
    root.withdraw()

    # Show splash screen
    splash = SplashScreen(root)

    # Preload weather data
    def preload_weather():
        try:
            print("[preload] fetching weather for splash...")
            get_weather_data()
            print("[preload] weather fetched/cached")
        except Exception as e:
            print("[preload] weather error:", e)

    # Start splash and launch main window
    splash.start(lambda: launch_main_gui(root), preload_fn=preload_weather, preload_timeout=8)

    # Run main loop
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nApplication closed by user.")
        sys.exit(0)


# ---------- Entry Point ----------
if __name__ == "__main__":
    main()
