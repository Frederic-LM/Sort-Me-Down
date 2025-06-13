import customtkinter as ctk
from tkinter import filedialog
import logging
import threading
from pathlib import Path
from PIL import Image, ImageDraw
import pystray

import bangbang_backend as backend

CONFIG_FILE = Path("config.json")

class GuiLoggingHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.text_widget.tag_config("INFO", foreground="white")
        self.text_widget.tag_config("DRYRUN", foreground="#00FFFF")
        self.text_widget.tag_config("WARNING", foreground="orange")
        self.text_widget.tag_config("ERROR", foreground="#FF5555")
        self.text_widget.tag_config("SUCCESS", foreground="#00FF7F")
        self.text_widget.tag_config("FRENCH", foreground="#6495ED")

    def emit(self, record):
        msg = self.format(record)
        tag = "INFO"
        if "🔵⚪🔴" in msg: tag = "FRENCH"
        elif "DRY RUN:" in msg: tag = "DRYRUN"
        elif "✅" in msg or "Settings saved" in msg: tag = "SUCCESS"
        elif record.levelname == "WARNING": tag = "WARNING"
        elif record.levelname in ["ERROR", "CRITICAL"]: tag = "ERROR"
        def insert_text():
            if self.text_widget.winfo_exists():
                self.text_widget.configure(state="normal")
                self.text_widget.insert(ctk.END, msg + '\n', tag)
                self.text_widget.see(ctk.END)
                self.text_widget.configure(state="disabled")
        if hasattr(self.text_widget, 'after'):
            try:
                self.text_widget.after(0, insert_text)
            except Exception:
                pass

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SortMeDown Media Sorter")
        self.geometry("900x700")
        ctk.set_appearance_mode("Dark")

        self.config = backend.Config.load(CONFIG_FILE)
        self.sorter_thread = None
        self.sorter_instance = None 
        self.tray_icon = None
        self.tab_view = None
        self.is_quitting = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.controls_frame = ctk.CTkFrame(self)
        self.controls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="new")
        self.create_controls()
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", font=("Courier New", 12))
        self.log_textbox.grid(row=1, column=0, padx=10, pady=(0,10), sticky="nsew")

        self.setup_logging()
        self.protocol("WM_DELETE_WINDOW", self.quit_app)
        self.bind("<Unmap>", self.on_minimize)
        self.setup_tray_icon()
        
    def setup_logging(self):
        log_handler = GuiLoggingHandler(self.log_textbox)
        log_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s", "%H:%M:%S"))
        logging.basicConfig(level=logging.INFO, handlers=[log_handler], force=True)
        
    def create_controls(self):
        self.tab_view = ctk.CTkTabview(self.controls_frame)
        self.tab_view.pack(expand=True, fill="both", padx=5, pady=5)
        self.create_actions_tab(self.tab_view.add("Actions"))
        self.create_settings_tab(self.tab_view.add("Settings"))

    def create_actions_tab(self, parent):
        parent.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.sort_now_button = ctk.CTkButton(parent, text="Sort Now", command=self.start_sort_now)
        self.sort_now_button.grid(row=0, column=0, columnspan=2, padx=5, pady=10, sticky="ew")
        self.watch_button = ctk.CTkButton(parent, text="Start Watching", command=self.toggle_watch_mode)
        self.watch_button.grid(row=0, column=2, columnspan=2, padx=5, pady=10, sticky="ew")
        self.dry_run_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(parent, text="Dry Run (Preview changes)", variable=self.dry_run_var).grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="w")
        watch_interval_frame = ctk.CTkFrame(parent, fg_color="transparent")
        watch_interval_frame.grid(row=2, column=2, columnspan=2, padx=5, pady=5, sticky="e")
        ctk.CTkLabel(watch_interval_frame, text="Check every").pack(side="left", padx=(0,5))
        self.watch_interval_entry = ctk.CTkEntry(watch_interval_frame, width=40)
        self.watch_interval_entry.pack(side="left")
        self.watch_interval_entry.insert(0, str(self.config.WATCH_INTERVAL // 60))
        ctk.CTkLabel(watch_interval_frame, text="minutes").pack(side="left", padx=(5,0))

    def create_settings_tab(self, parent):
        parent.grid_columnconfigure(1, weight=1)
        self.path_entries = {}
        standard_path_keys = ['SOURCE_DIR', 'MOVIES_DIR', 'TV_SHOWS_DIR', 'ANIME_MOVIES_DIR', 'ANIME_SERIES_DIR']
        for i, key in enumerate(standard_path_keys):
            ctk.CTkLabel(parent, text=key.replace('_', ' ').title()).grid(row=i, column=0, padx=5, pady=5, sticky="w")
            entry = ctk.CTkEntry(parent, width=400); entry.grid(row=i, column=1, padx=5, pady=5, sticky="ew")
            entry.insert(0, getattr(self.config, key, "")); self.path_entries[key] = entry
            ctk.CTkButton(parent, text="Browse...", width=80, command=lambda e=entry: self.browse_folder(e)).grid(row=i, column=2, padx=5, pady=5)
        
        french_row = len(standard_path_keys)
        self.fr_sauce_var = ctk.BooleanVar(value=self.config.FRENCH_MODE_ENABLED)
        fr_check = ctk.CTkCheckBox(parent, text="French Mode", variable=self.fr_sauce_var, command=self.toggle_french_dir_visibility)
        fr_check.grid(row=french_row, column=0, padx=5, pady=5, sticky="w")
        self.french_dir_entry = ctk.CTkEntry(parent, width=400)
        self.french_dir_entry.insert(0, getattr(self.config, "FRENCH_MOVIES_DIR", ""))
        self.path_entries["FRENCH_MOVIES_DIR"] = self.french_dir_entry
        self.french_dir_browse = ctk.CTkButton(parent, text="Browse...", width=80, command=lambda e=self.french_dir_entry: self.browse_folder(e))
        
        api_row = french_row + 1
        ctk.CTkLabel(parent, text="OMDb API Key").grid(row=api_row, column=0, padx=5, pady=5, sticky="w")
        self.api_key_entry = ctk.CTkEntry(parent, placeholder_text="Enter your OMDb API key here")
        self.api_key_entry.grid(row=api_row, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        if self.config.OMDB_API_KEY and self.config.OMDB_API_KEY != "yourkey":
            self.api_key_entry.insert(0, self.config.OMDB_API_KEY)
            self.api_key_entry.configure(show="*")
        self.api_key_entry.bind("<Key>", self.on_api_key_type)
        self.toggle_french_dir_visibility()

    def toggle_french_dir_visibility(self):
        french_row = len(self.path_entries) - 1
        if self.fr_sauce_var.get():
            self.french_dir_entry.grid(row=french_row, column=1, padx=5, pady=5, sticky="ew")
            self.french_dir_browse.grid(row=french_row, column=2, padx=5, pady=5)
        else:
            self.french_dir_entry.grid_remove()
            self.french_dir_browse.grid_remove()

    def on_api_key_type(self, event=None):
        if self.api_key_entry.cget("show") == "": self.api_key_entry.configure(show="*")

    def browse_folder(self, entry_widget):
        if folder_path := filedialog.askdirectory(initialdir=entry_widget.get()):
            entry_widget.delete(0, ctk.END); entry_widget.insert(0, folder_path)
            
    def update_config_from_ui(self):
        for key, entry in self.path_entries.items(): setattr(self.config, key, entry.get())
        if api_key := self.api_key_entry.get(): self.config.OMDB_API_KEY = api_key
        self.config.FRENCH_MODE_ENABLED = self.fr_sauce_var.get()
        try:
            self.config.WATCH_INTERVAL = int(self.watch_interval_entry.get()) * 60
        except (ValueError, TypeError):
            self.config.WATCH_INTERVAL = 15 * 60

    def start_sort_now(self):
        if self.is_quitting: return
        self.update_config_from_ui()
        if not self.config.validate(): return
        if self.config.FRENCH_MODE_ENABLED: logging.info("🔵⚪🔴 French Sauce is ENABLED.")
        self.set_controls_state("disabled")
        sorter = backend.MediaSorter(self.config, dry=self.dry_run_var.get(), fr=self.config.FRENCH_MODE_ENABLED)
        self.sorter_thread = threading.Thread(target=sorter.process_source_directory, daemon=True)
        self.sorter_thread.start()
        self.monitor_thread(self.sorter_thread)
    
    def start_watcher(self):
        if self.is_quitting: return
        self.update_config_from_ui()
        if not self.config.validate(): return
        if self.config.FRENCH_MODE_ENABLED: logging.info("🔵⚪🔴 French Sauce is ENABLED.")
        logging.info(f"👁️ Watch mode started (refresh every {self.config.WATCH_INTERVAL // 60} minutes).")
        self.set_controls_state("disabled")
        self.watch_button.configure(text="Stop Watching", state="normal")
        self.sorter_instance = backend.MediaSorter(self.config, dry=self.dry_run_var.get(), fr=self.config.FRENCH_MODE_ENABLED)
        self.sorter_thread = threading.Thread(target=self.sorter_instance.start_watch_mode, daemon=True)
        self.sorter_thread.start()
        if self.tray_icon: self.tray_icon.update_menu()
    
    def stop_watcher(self):
        if self.is_quitting: return
        if self.sorter_instance and self.sorter_thread and self.sorter_thread.is_alive():
            logging.info("Sending stop signal to watcher...")
            self.sorter_instance.stop_watch_mode()
            self.watch_button.configure(state="disabled", text="Stopping...")
            self.monitor_stop()

    def toggle_watch_mode(self):
        if self.is_quitting: return
        if self.sorter_thread and self.sorter_thread.is_alive(): self.stop_watcher()
        else: self.start_watcher()
    
    def set_controls_state(self, state):
        if self.is_quitting: return
        self.sort_now_button.configure(state=state)
        if self.watch_button.cget("text") in ["Start Watching", "Stop Watching"]: self.watch_button.configure(state=state)

    def monitor_stop(self):
        if self.is_quitting: return
        if self.sorter_thread and self.sorter_thread.is_alive(): self.after(100, self.monitor_stop)
        else:
            if not self.is_quitting:
                logging.info("Watcher has stopped.")
                self.watch_button.configure(state="normal", text="Start Watching")
                self.set_controls_state("normal")
            self.sorter_instance = None
            self.sorter_thread = None
            if self.tray_icon: self.tray_icon.update_menu()

    def monitor_thread(self, thread):
        if self.is_quitting: return
        if thread.is_alive(): self.after(100, lambda: self.monitor_thread(thread))
        else:
            if not self.is_quitting:
                logging.info("✅ Task finished.")
                self.set_controls_state("normal")
    
    def create_tray_image(self):
        width, height = 64, 64; color1, color2 = "#1F6AA5", "#144870"
        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)
        dc.rectangle((width // 2, 0, width, height // 2), fill=color2)
        dc.rectangle((0, height // 2, width // 2, height), fill=color2)
        return image

    def show_window(self):
        self.deiconify(); self.lift()
        self.attributes('-topmost', True)
        if self.tab_view: self.tab_view.set("Actions")
        self.after(100, lambda: self.attributes('-topmost', False))

    def show_settings(self):
        self.show_window()
        if self.tab_view: self.tab_view.set("Settings")

    def hide_to_tray(self):
        self.withdraw()
        if self.tray_icon: self.tray_icon.notify('App is running in the background', 'SortMeDown')
    
    def on_minimize(self, event):
        if self.state() == 'iconic':
            self.hide_to_tray()

    def set_interval(self, minutes: int):
        logging.info(f"Watch interval set to {minutes} minutes.")
        self.config.WATCH_INTERVAL = minutes * 60
        self.watch_interval_entry.delete(0, ctk.END); self.watch_interval_entry.insert(0, str(minutes))
        if self.tray_icon: self.tray_icon.update_menu()

    def setup_tray_icon(self):
        image = self.create_tray_image()
        interval_menu = pystray.Menu(
            pystray.MenuItem('5 minutes', lambda: self.set_interval(5), radio=True, checked=lambda item: self.config.WATCH_INTERVAL == 5 * 60),
            pystray.MenuItem('15 minutes', lambda: self.set_interval(15), radio=True, checked=lambda item: self.config.WATCH_INTERVAL == 15 * 60),
            pystray.MenuItem('30 minutes', lambda: self.set_interval(30), radio=True, checked=lambda item: self.config.WATCH_INTERVAL == 30 * 60),
            pystray.MenuItem('60 minutes', lambda: self.set_interval(60), radio=True, checked=lambda item: self.config.WATCH_INTERVAL == 60 * 60)
        )
        menu = (
            pystray.MenuItem('Show', self.show_window, default=True),
            pystray.MenuItem('Settings', self.show_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Enable Watch', self.toggle_watch_mode, checked=lambda item: self.sorter_thread is not None and self.sorter_thread.is_alive()),
            pystray.MenuItem('Set Interval', interval_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', self.quit_app)
        )
        self.tray_icon = pystray.Icon("sortmedown", image, "SortMeDown Sorter", menu)
        tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        tray_thread.start()

    
    def _perform_safe_shutdown(self):
        """This part of the shutdown MUST run on the main GUI thread."""
        self.update_config_from_ui()
        self.config.save(CONFIG_FILE)
        self.destroy()

    def quit_app(self):
        """Initiates the shutdown sequence. Can be called from any thread."""
        if self.is_quitting: return
        self.is_quitting = True
        
        logging.info("Shutting down...")
        
        # Stop non-GUI threads first.
        if self.tray_icon: self.tray_icon.stop()
        if self.sorter_instance: self.sorter_instance.stop_watch_mode()
        if self.sorter_thread: self.sorter_thread.join(timeout=2)
            
        # Schedule the final GUI cleanup to happen on the main thread.
        self.after(0, self._perform_safe_shutdown)

if __name__ == "__main__":
    app = App()
    app.mainloop()
