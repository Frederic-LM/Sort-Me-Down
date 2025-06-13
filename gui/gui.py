"""
SortMeDown Media Sorter - GUI (gui.py) for bang bang 
================================

This file contains the Graphical User Interface for the SortMeDown media sorter.
It is built using the CustomTkinter library and provides a user-friendly way
to interact with the sorting logic defined in `bangbang_backend.py`.

Major Feature Iterations: 
-------------------------




version 1.14

- Conditional Path Prompt: When enabling a media type from the Actions tab,
  the app now checks if a destination path is set. If not, it automatically
  prompts the user to select a folder. If the user cancels, the option is
  disabled to prevent an invalid state.
- UI Spacing: Adjusted the vertical padding around the separator and toggles
  on the Actions tab for a cleaner, more balanced layout.
- (Previous features from 1.13 retained)

  version 1.13

- Actions Tab Toggles: Added copies of the enable/disable toggles (Movies, TV,
  etc.) from the Settings tab directly to the Actions tab for quick access.
  This was implemented by centralizing the state `BooleanVar`s in the `__init__`
  method, ensuring that toggles in both tabs are always synchronized. A visual
  separator was also added for better layout clarity.
  
version 1.12 

- Initial Setup: Basic layout with tabs for Actions and Settings.
- Configuration Management: Load/save settings from a `config.json` file.
- Live Logging: A custom logging handler redirects all backend output to a
  text box in the GUI, with color-coding for different message types (Info,
  Warning, Error, Dry Run).
- Threading for Responsiveness: All backend tasks (sorting, watching) are run
  in separate threads to keep the GUI from freezing.
- Watch Mode Control: Buttons to start and stop the continuous watching process.
- User-Customizable Options:
  - Checkboxes for "Dry Run", "French Mode", and "Clean Up Source Directory".
  - Checkboxes to enable/disable sorting for each media type (Movies, TV, etc.).
  - Input box to set the watch interval.
- Advanced UI/UX Refinements:
  - Conditional visibility for the "French Movies" directory field.
  - "Clean Up" button turns green to indicate a different mode.
  - A central, dynamic "STOP" button that appears only when a task is active.
  - Intelligent watcher state display ("STOP" vs. "IDLE").
- System Tray Integration:
  - Application minimizes to the system tray instead of closing.
  - Right-click menu on tray icon provides quick access to:
    - Show Window / Show Settings
    - Enable/Disable Watch Mode (with a checkbox)
    - Set Interval (via a sub-menu of common choices)
    - Quit Application
- Robust Shutdown: Graceful, thread-safe shutdown sequence to prevent errors
  when closing the application from the window or tray.

"""


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
        super().__init__(); self.text_widget = text_widget
        self.text_widget.tag_config("INFO", foreground="white"); self.text_widget.tag_config("DRYRUN", foreground="#00FFFF")
        self.text_widget.tag_config("WARNING", foreground="orange"); self.text_widget.tag_config("ERROR", foreground="#FF5555")
        self.text_widget.tag_config("SUCCESS", foreground="#00FF7F"); self.text_widget.tag_config("FRENCH", foreground="#6495ED")
    def emit(self, record):
        msg = self.format(record); tag = "INFO"
        if "🔵⚪🔴" in msg: tag = "FRENCH"
        elif "DRY RUN:" in msg: tag = "DRYRUN"
        elif "✅" in msg or "Settings saved" in msg: tag = "SUCCESS"
        elif record.levelname == "WARNING": tag = "WARNING"
        elif record.levelname in ["ERROR", "CRITICAL"]: tag = "ERROR"
        def insert_text():
            if self.text_widget.winfo_exists():
                self.text_widget.configure(state="normal"); self.text_widget.insert(ctk.END, msg + '\n', tag)
                self.text_widget.see(ctk.END); self.text_widget.configure(state="disabled")
        if hasattr(self.text_widget, 'after'):
            try: self.text_widget.after(0, insert_text)
            except Exception: pass

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SortMeDown Media Sorter"); self.geometry("900x750"); ctk.set_appearance_mode("Dark")
        self.config = backend.Config.load(CONFIG_FILE)
        self.sorter_thread = None; self.sorter_instance = None; self.tray_icon = None; self.tab_view = None
        self.is_quitting = False; self.path_entries = {}; self.default_button_color = None; self.default_hover_color = None
        self.is_watching = False 
        
        self.enabled_vars = {
            'MOVIES_ENABLED': ctk.BooleanVar(value=self.config.MOVIES_ENABLED),
            'TV_SHOWS_ENABLED': ctk.BooleanVar(value=self.config.TV_SHOWS_ENABLED),
            'ANIME_MOVIES_ENABLED': ctk.BooleanVar(value=self.config.ANIME_MOVIES_ENABLED),
            'ANIME_SERIES_ENABLED': ctk.BooleanVar(value=self.config.ANIME_SERIES_ENABLED),
        }
        self.fr_sauce_var = ctk.BooleanVar(value=self.config.FRENCH_MODE_ENABLED)
        self.dry_run_var = ctk.BooleanVar(value=False)
        self.cleanup_var = ctk.BooleanVar(value=self.config.CLEANUP_MODE_ENABLED)
        
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(1, weight=1)
        self.controls_frame = ctk.CTkFrame(self); self.controls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="new")
        self.create_controls()
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", font=("Courier New", 12))
        self.log_textbox.grid(row=1, column=0, padx=10, pady=(0,10), sticky="nsew")
        self.setup_logging(); self.protocol("WM_DELETE_WINDOW", self.quit_app); self.bind("<Unmap>", self.on_minimize); self.setup_tray_icon()
        
    def setup_logging(self):
        log_handler = GuiLoggingHandler(self.log_textbox)
        log_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s", "%H:%M:%S"))
        logging.basicConfig(level=logging.INFO, handlers=[log_handler], force=True)
        
    def create_controls(self):
        self.tab_view = ctk.CTkTabview(self.controls_frame); self.tab_view.pack(expand=True, fill="both", padx=5, pady=5)
        self.create_actions_tab(self.tab_view.add("Actions")); self.create_settings_tab(self.tab_view.add("Settings"))

    def create_actions_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        
        button_bar_frame = ctk.CTkFrame(parent, fg_color="transparent")
        button_bar_frame.grid(row=0, column=0, sticky="ew")
        button_bar_frame.grid_columnconfigure((0, 2), weight=1); button_bar_frame.grid_columnconfigure(1, weight=0)
        
        self.sort_now_button = ctk.CTkButton(button_bar_frame, text="Sort Now", command=self.start_sort_now)
        self.sort_now_button.grid(row=0, column=0, padx=(0, 5), pady=10, sticky="ew")
        self.default_button_color = self.sort_now_button.cget("fg_color"); self.default_hover_color = self.sort_now_button.cget("hover_color")
        
        self.stop_button = ctk.CTkButton(button_bar_frame, text="", width=60, command=self.stop_running_task, fg_color="gray25", border_width=0, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=5, pady=10)
        
        self.watch_button = ctk.CTkButton(button_bar_frame, text="Start Watching", command=self.toggle_watch_mode)
        self.watch_button.grid(row=0, column=2, padx=(5, 0), pady=10, sticky="ew")
        
        options_frame = ctk.CTkFrame(parent, fg_color="transparent")
        options_frame.grid(row=1, column=0, columnspan=3, sticky="ew")
        options_frame.grid_columnconfigure((0,1), weight=1)
        
        ctk.CTkCheckBox(options_frame, text="Dry Run", variable=self.dry_run_var).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ctk.CTkCheckBox(options_frame, text="Clean Up Source (disables Watch Mode)", variable=self.cleanup_var, command=self.toggle_cleanup_mode_ui).grid(row=1, column=0, padx=5, pady=5, sticky="w")
        
        watch_interval_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        watch_interval_frame.grid(row=0, column=1, padx=5, pady=5, sticky="e")
        ctk.CTkLabel(watch_interval_frame, text="Check every").pack(side="left", padx=(0,5))
        self.watch_interval_entry = ctk.CTkEntry(watch_interval_frame, width=40)
        self.watch_interval_entry.pack(side="left"); self.watch_interval_entry.insert(0, str(self.config.WATCH_INTERVAL // 60))
        ctk.CTkLabel(watch_interval_frame, text="minutes").pack(side="left", padx=(5,0))

        # --- MODIFIED: Adjusted padding for better spacing ---
        separator = ctk.CTkFrame(parent, height=2, fg_color="gray25")
        separator.grid(row=2, column=0, pady=(10, 10), sticky="ew")

        toggles_frame = ctk.CTkFrame(parent, fg_color="transparent")
        # --- MODIFIED: Added bottom padding to this frame ---
        toggles_frame.grid(row=3, column=0, sticky="ew", pady=(0, 5)) 
        toggles_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        # --- NEW: Defined a map to create toggles with commands ---
        action_toggles_map = {
            'Movies':       ('MOVIES_ENABLED', 'MOVIES_DIR'),
            'TV Shows':     ('TV_SHOWS_ENABLED', 'TV_SHOWS_DIR'),
            'Anime Movies': ('ANIME_MOVIES_ENABLED', 'ANIME_MOVIES_DIR'),
            'Anime Series': ('ANIME_SERIES_ENABLED', 'ANIME_SERIES_DIR'),
        }
        
        col_counter = 0
        for label, (enable_key, dir_key) in action_toggles_map.items():
            var = self.enabled_vars[enable_key]
            ctk.CTkCheckBox(
                toggles_frame, text=label, variable=var,
                command=lambda v=var, dk=dir_key: self.check_and_prompt_for_path(dk, v)
            ).grid(row=0, column=col_counter, padx=5, pady=5)
            col_counter += 1

        # Handle French Mode separately as it uses a different variable
        ctk.CTkCheckBox(
            toggles_frame, text="French Mode", variable=self.fr_sauce_var,
            command=lambda: self.check_and_prompt_for_path('FRENCH_MOVIES_DIR', self.fr_sauce_var)
        ).grid(row=0, column=col_counter, padx=5, pady=5)
        # --- END NEW / MODIFIED SECTION ---

        self.toggle_cleanup_mode_ui()

    # --- NEW: Method to handle the conditional folder prompt ---
    def check_and_prompt_for_path(self, dir_key: str, bool_var: ctk.BooleanVar):
        """Checks if a path is set when a feature is enabled. If not, prompts the user."""
        # Only act when the checkbox is ticked ON
        if bool_var.get():
            # Check if the corresponding path entry in the UI is empty
            if dir_key in self.path_entries and not self.path_entries[dir_key].get().strip():
                logging.info(f"Path for {dir_key.replace('_', ' ').title()} is not set. Please select a folder.")
                # Use the existing browse function to open a dialog
                self.browse_folder(self.path_entries[dir_key])
                
                # After the dialog, if the path is STILL empty (user cancelled), disable the feature
                if not self.path_entries[dir_key].get().strip():
                    logging.warning(f"No folder selected. Disabling the feature to prevent errors.")
                    bool_var.set(False)

    def stop_running_task(self):
        if self.sorter_instance:
            logging.warning("🛑 User initiated stop. Aborting current action...")
            self.sorter_instance.signal_stop()
        if self.is_watching:
            self.is_watching = False

    def toggle_cleanup_mode_ui(self):
        is_running = self.sorter_thread and self.sorter_thread.is_alive()
        if self.cleanup_var.get():
            self.sort_now_button.configure(text="Clean Up Source Directory", fg_color="#2E7D32", hover_color="#1B5E20")
            self.watch_button.configure(state="disabled")
        else:
            self.sort_now_button.configure(text="Sort Now", fg_color=self.default_button_color, hover_color=self.default_hover_color)
            if not is_running:
                self.watch_button.configure(state="normal")
    
    def create_settings_tab(self, parent):
        parent.grid_columnconfigure(1, weight=1)
        # --- MODIFIED: self.path_entries is now defined here before use ---
        self.path_entries = {}
        dir_map = {
            'SOURCE_DIR': ('Source Dir', None),
            'MOVIES_DIR': ('Enable Movies', 'MOVIES_ENABLED'),
            'TV_SHOWS_DIR': ('Enable TV Shows', 'TV_SHOWS_ENABLED'),
            'ANIME_MOVIES_DIR': ('Enable Anime Movies', 'ANIME_MOVIES_ENABLED'),
            'ANIME_SERIES_DIR': ('Enable Anime Series', 'ANIME_SERIES_ENABLED'),
        }
        row_counter = 0
        for dir_key, (label_text, enable_key) in dir_map.items():
            if enable_key:
                var = self.enabled_vars[enable_key]
                label_widget = ctk.CTkCheckBox(parent, text=label_text, variable=var)
            else: 
                label_widget = ctk.CTkLabel(parent, text=label_text)
            
            label_widget.grid(row=row_counter, column=0, padx=5, pady=5, sticky="w")
            entry = ctk.CTkEntry(parent, width=400); entry.grid(row=row_counter, column=1, padx=5, pady=5, sticky="ew")
            entry.insert(0, getattr(self.config, dir_key, "")); self.path_entries[dir_key] = entry
            ctk.CTkButton(parent, text="Browse...", width=80, command=lambda e=entry: self.browse_folder(e)).grid(row=row_counter, column=2, padx=5, pady=5)
            row_counter += 1
        
        self.fr_check = ctk.CTkCheckBox(parent, text="Enable French Mode", variable=self.fr_sauce_var, command=self.toggle_french_dir_visibility)
        self.fr_check.grid(row=row_counter, column=0, padx=5, pady=5, sticky="w")
        
        self.french_dir_entry = ctk.CTkEntry(parent, width=400)
        self.french_dir_entry.insert(0, getattr(self.config, "FRENCH_MOVIES_DIR", "")); self.path_entries["FRENCH_MOVIES_DIR"] = self.french_dir_entry
        self.french_dir_browse = ctk.CTkButton(parent, text="Browse...", width=80, command=lambda e=self.french_dir_entry: self.browse_folder(e))
        
        api_row = row_counter + 1
        ctk.CTkLabel(parent, text="OMDb API Key").grid(row=api_row, column=0, padx=5, pady=5, sticky="w")
        self.api_key_entry = ctk.CTkEntry(parent, placeholder_text="Enter API key"); self.api_key_entry.grid(row=api_row, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        if self.config.OMDB_API_KEY and self.config.OMDB_API_KEY != "yourkey":
            self.api_key_entry.insert(0, self.config.OMDB_API_KEY); self.api_key_entry.configure(show="*")
        self.api_key_entry.bind("<Key>", self.on_api_key_type)
        self.toggle_french_dir_visibility()

    def toggle_french_dir_visibility(self):
        french_row = 5
        if self.fr_sauce_var.get():
            self.french_dir_entry.grid(row=french_row, column=1, padx=5, pady=5, sticky="ew")
            self.french_dir_browse.grid(row=french_row, column=2, padx=5, pady=5)
        else: self.french_dir_entry.grid_remove(); self.french_dir_browse.grid_remove()

    def on_api_key_type(self, event=None):
        if self.api_key_entry.cget("show") == "": self.api_key_entry.configure(show="*")

    def browse_folder(self, entry_widget):
        if folder_path := filedialog.askdirectory(initialdir=entry_widget.get()):
            entry_widget.delete(0, ctk.END); entry_widget.insert(0, folder_path)

    def update_config_from_ui(self):
        for key, entry in self.path_entries.items(): setattr(self.config, key, entry.get())
        for key, var in self.enabled_vars.items(): setattr(self.config, key, var.get())
        if api_key := self.api_key_entry.get(): self.config.OMDB_API_KEY = api_key
        self.config.FRENCH_MODE_ENABLED = self.fr_sauce_var.get()
        self.config.CLEANUP_MODE_ENABLED = self.cleanup_var.get()
        try: self.config.WATCH_INTERVAL = int(self.watch_interval_entry.get()) * 60
        except (ValueError, TypeError): self.config.WATCH_INTERVAL = 15 * 60

    def start_task(self, task_function, is_watcher=False):
        if self.is_quitting or (self.sorter_thread and self.sorter_thread.is_alive()): return
        self.is_watching = is_watcher
        self.update_config_from_ui()
        if not self.config.validate(): return
        if self.config.FRENCH_MODE_ENABLED and not self.config.CLEANUP_MODE_ENABLED: logging.info("🔵⚪🔴 French Sauce is ENABLED.")
        if self.config.CLEANUP_MODE_ENABLED: logging.info("🧹 Clean Up Mode is ENABLED.")
        
        self.sorter_instance = backend.MediaSorter(self.config, dry=self.dry_run_var.get())
        self.sorter_thread = threading.Thread(target=task_function, args=(self.sorter_instance,), daemon=True)
        self.sorter_thread.start()
        self.monitor_active_task()

    def start_sort_now(self):
        self.start_task(lambda sorter: sorter.process_source_directory(), is_watcher=False)
    
    def toggle_watch_mode(self):
        if self.sorter_thread and self.sorter_thread.is_alive():
            self.stop_running_task()
        else:
            self.start_task(lambda sorter: sorter.start_watch_mode(), is_watcher=True)

    def monitor_active_task(self):
        if self.is_quitting: return

        is_running = self.sorter_thread and self.sorter_thread.is_alive()
        
        if is_running:
            self.sort_now_button.configure(state="disabled")
            self.watch_button.configure(text="Stop Watching" if self.is_watching else "Running...", state="disabled" if not self.is_watching else "normal")

            is_processing = self.sorter_instance and self.sorter_instance.is_processing
            if is_processing:
                self.stop_button.configure(state="normal", text="STOP", fg_color="#D32F2F", hover_color="#B71C1C")
            else: # Watcher is idle
                self.stop_button.configure(state="disabled", text="IDLE", fg_color="#FBC02D", text_color="black")
            
            self.after(500, self.monitor_active_task)
        else:
            logging.info("✅ Task finished.")
            self.sort_now_button.configure(state="normal")
            self.watch_button.configure(text="Start Watching", state="normal")
            self.stop_button.configure(state="disabled", text="", fg_color="gray25")
            
            self.sorter_instance = None
            self.sorter_thread = None
            self.is_watching = False
            if self.tray_icon: self.tray_icon.update_menu()
            self.toggle_cleanup_mode_ui()
    
    def create_tray_image(self):
        width, height = 64, 64; color1, color2 = "#1F6AA5", "#144870"
        image = Image.new('RGB', (width, height), color1)
        dc = ImageDraw.Draw(image)
        dc.rectangle((width // 2, 0, width, height // 2), fill=color2)
        dc.rectangle((0, height // 2, width // 2, height), fill=color2)
        return image
    def quit_app(self):
        if self.is_quitting: return
        self.is_quitting = True
        logging.info("Shutting down...")
        if self.tray_icon: self.tray_icon.stop()
        if self.sorter_instance: self.sorter_instance.signal_stop()
        if self.sorter_thread: self.sorter_thread.join(timeout=2)
        self.after(0, self._perform_safe_shutdown)
    def _perform_safe_shutdown(self):
        self.update_config_from_ui(); self.config.save(CONFIG_FILE); self.destroy()
    def show_window(self):
        self.deiconify(); self.lift(); self.attributes('-topmost', True)
        if self.tab_view: self.tab_view.set("Actions")
        self.after(100, lambda: self.attributes('-topmost', False))
    def show_settings(self):
        self.show_window()
        if self.tab_view: self.tab_view.set("Settings")
    def hide_to_tray(self):
        self.withdraw()
        if self.tray_icon: self.tray_icon.notify('App is running in the background', 'SortMeDown')
    def on_minimize(self, event):
        if self.state() == 'iconic': self.hide_to_tray()
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
            pystray.MenuItem('Show', self.show_window, default=True), pystray.MenuItem('Settings', self.show_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Enable Watch', self.toggle_watch_mode, checked=lambda item: self.is_watching),
            pystray.MenuItem('Set Interval', interval_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', self.quit_app)
        )
        self.tray_icon = pystray.Icon("sortmedown", image, "SortMeDown Sorter", menu)
        tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        tray_thread.start()

if __name__ == "__main__":
    app = App()
    app.mainloop()
