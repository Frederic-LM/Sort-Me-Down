# gui.py
"""
SortMeDown Media Sorter - GUI (gui.py) for bang bang 
================================

This file contains the Graphical User Interface for the SortMeDown media sorter.
It is built using the CustomTkinter library and provides a user-friendly way
to interact with the sorting logic defined in `bangbang.py`.

v5.4
include progress bar and show/hide logs, reduce default windows side 
"""

import customtkinter as ctk
from tkinter import filedialog
import logging
import threading
from pathlib import Path
from PIL import Image, ImageDraw
import pystray
import sys
import tkinter
import os

import bangbang as backend

CONFIG_FILE = Path("config.json")

def resource_path(relative_path):
    try: base_path = Path(sys._MEIPASS)
    except Exception: base_path = Path(__file__).parent.absolute()
    return base_path / relative_path

class GuiLoggingHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__(); self.text_widget = text_widget
        self.text_widget.tag_config("INFO", foreground="white"); self.text_widget.tag_config("DRYRUN", foreground="#00FFFF")
        self.text_widget.tag_config("WARNING", foreground="orange"); self.text_widget.tag_config("ERROR", foreground="#FF5555")
        self.text_widget.tag_config("SUCCESS", foreground="#00FF7F"); self.text_widget.tag_config("FRENCH", foreground="#6495ED")
    def emit(self, record):
        msg = self.format(record); tag = "INFO"
        if "🔵⚪🔴" in msg: tag = "FRENCH"
        elif "DRY RUN:" in msg or "Dry Run is ENABLED" in msg: tag = "DRYRUN"
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
            try: self.text_widget.after(0, insert_text)
            except Exception: pass

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SortMeDown Media Sorter"); self.geometry("800x400"); ctk.set_appearance_mode("Dark")
        try:
            if sys.platform == "win32": self.iconbitmap(str(resource_path("icon.ico")))
            else: self.iconphoto(True, tkinter.PhotoImage(file=str(resource_path("icon.png"))))
        except Exception as e: logging.warning(f"Could not set window icon: {e}")
        self.config = backend.Config.load(CONFIG_FILE)
        self.sorter_thread = None; self.sorter_instance = None; self.tray_icon = None; self.tab_view = None
        self.is_quitting = False; self.path_entries = {}; self.default_button_color = None; self.default_hover_color = None
        self.is_watching = False
        # --- ADDED: State for log visibility ---
        self.log_is_visible = True
        self.enabled_vars = {
            'MOVIES_ENABLED': ctk.BooleanVar(value=self.config.MOVIES_ENABLED),
            'TV_SHOWS_ENABLED': ctk.BooleanVar(value=self.config.TV_SHOWS_ENABLED),
            'ANIME_MOVIES_ENABLED': ctk.BooleanVar(value=self.config.ANIME_MOVIES_ENABLED),
            'ANIME_SERIES_ENABLED': ctk.BooleanVar(value=self.config.ANIME_SERIES_ENABLED),
        }
        self.fr_sauce_var = ctk.BooleanVar(value=self.config.FRENCH_MODE_ENABLED)
        self.dry_run_var = ctk.BooleanVar(value=False)
        self.cleanup_var = ctk.BooleanVar(value=self.config.CLEANUP_MODE_ENABLED)
        self.fallback_var = ctk.StringVar(value=self.config.FALLBACK_SHOW_DESTINATION)
        
        # --- MODIFIED: Main window grid layout to accommodate progress bar at the bottom ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # Controls row (fixed)
        self.grid_rowconfigure(1, weight=1)  # Log row (expandable)
        self.grid_rowconfigure(2, weight=0)  # Progress row (fixed)

        self.controls_frame = ctk.CTkFrame(self); self.controls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="new")
        self.create_controls()
        
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", font=("Courier New", 12))
        self.log_textbox.grid(row=1, column=0, padx=10, pady=(0,5), sticky="nsew")

        # --- MOVED: Progress bar is now a child of the main window, placed in the new row 2 ---
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="")
        self.progress_label.grid(row=0, column=0, sticky="w", padx=5)
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=5)
        self.progress_frame.grid_remove()  # Start hidden

        self.setup_logging(); self.protocol("WM_DELETE_WINDOW", self.quit_app); self.bind("<Unmap>", self.on_minimize); self.setup_tray_icon()
        self.update_fallback_ui_state()

    def setup_logging(self):
        log_handler = GuiLoggingHandler(self.log_textbox)
        log_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s", "%H:%M:%S"))
        logging.basicConfig(level=logging.INFO, handlers=[log_handler], force=True)
        
    def create_controls(self):
        self.tab_view = ctk.CTkTabview(self.controls_frame); self.tab_view.pack(expand=True, fill="both", padx=5, pady=5)
        self.create_actions_tab(self.tab_view.add("Actions")); self.create_settings_tab(self.tab_view.add("Settings"))

    def create_actions_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        button_bar_frame = ctk.CTkFrame(parent, fg_color="transparent"); button_bar_frame.grid(row=0, column=0, sticky="ew")
        button_bar_frame.grid_columnconfigure((0, 2), weight=1); button_bar_frame.grid_columnconfigure(1, weight=0)
        self.sort_now_button = ctk.CTkButton(button_bar_frame, text="Sort Now", command=self.start_sort_now); self.sort_now_button.grid(row=0, column=0, padx=(0, 5), pady=10, sticky="ew")
        self.default_button_color = self.sort_now_button.cget("fg_color"); self.default_hover_color = self.sort_now_button.cget("hover_color")
        self.stop_button = ctk.CTkButton(button_bar_frame, text="", width=60, command=self.stop_running_task, fg_color="gray25", border_width=0, state="disabled"); self.stop_button.grid(row=0, column=1, padx=5, pady=10)
        self.watch_button = ctk.CTkButton(button_bar_frame, text="Start Watching", command=self.toggle_watch_mode); self.watch_button.grid(row=0, column=2, padx=(5, 0), pady=10, sticky="ew")
        
        # --- REMOVED progress bar creation from here ---

        options_frame = ctk.CTkFrame(parent, fg_color="transparent"); options_frame.grid(row=2, column=0, columnspan=3, sticky="ew")
        options_frame.grid_columnconfigure((0,1), weight=1)
        ctk.CTkCheckBox(options_frame, text="Dry Run", variable=self.dry_run_var).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ctk.CTkCheckBox(options_frame, text="Clean Up Source (disables Watch & Fallback)", variable=self.cleanup_var, command=self.toggle_cleanup_mode_ui).grid(row=1, column=0, padx=5, pady=5, sticky="w")
        
        watch_interval_frame = ctk.CTkFrame(options_frame, fg_color="transparent"); watch_interval_frame.grid(row=0, column=1, padx=5, pady=5, sticky="e")
        ctk.CTkLabel(watch_interval_frame, text="Check every").pack(side="left", padx=(0,5))
        self.watch_interval_entry = ctk.CTkEntry(watch_interval_frame, width=40); self.watch_interval_entry.pack(side="left"); self.watch_interval_entry.insert(0, str(self.config.WATCH_INTERVAL // 60))
        ctk.CTkLabel(watch_interval_frame, text="minutes").pack(side="left", padx=(5,0))
        
        # --- ADDED: Toggle Log button ---
        self.toggle_log_button = ctk.CTkButton(options_frame, text="Hide Log", width=100, command=self.toggle_log_visibility)
        self.toggle_log_button.grid(row=1, column=1, sticky="e", padx=5, pady=5)
        
        ctk.CTkFrame(parent, height=2, fg_color="gray25").grid(row=3, column=0, pady=(10, 5), sticky="ew") 
        toggles_frame = ctk.CTkFrame(parent, fg_color="transparent"); toggles_frame.grid(row=4, column=0, sticky="ew", pady=(0, 5)) 
        toggles_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        action_toggles_map = {'Movies': ('MOVIES_ENABLED', 'MOVIES_DIR'), 'TV Shows': ('TV_SHOWS_ENABLED', 'TV_SHOWS_DIR'), 'Anime Movies': ('ANIME_MOVIES_ENABLED', 'ANIME_MOVIES_DIR'), 'Anime Series': ('ANIME_SERIES_ENABLED', 'ANIME_SERIES_DIR'),}
        for i, (label, (enable_key, dir_key)) in enumerate(action_toggles_map.items()): ctk.CTkCheckBox(toggles_frame, text=label, variable=self.enabled_vars[enable_key], command=self.on_media_type_toggled).grid(row=0, column=i, padx=5, pady=5)
        ctk.CTkCheckBox(toggles_frame, text="French Mode", variable=self.fr_sauce_var, command=self._on_french_mode_toggled).grid(row=0, column=len(action_toggles_map), padx=5, pady=5)
        fallback_frame = ctk.CTkFrame(parent, fg_color="transparent"); fallback_frame.grid(row=5, column=0, pady=5, sticky="ew")
        ctk.CTkLabel(fallback_frame, text="For mismatched shows, default to:").pack(side="left", padx=(5,10))
        self.ignore_radio = ctk.CTkRadioButton(fallback_frame, text="Do Nothing", variable=self.fallback_var, value="ignore"); self.ignore_radio.pack(side="left", padx=5)
        self.mismatch_radio = ctk.CTkRadioButton(fallback_frame, text="Mismatched Folder", variable=self.fallback_var, value="mismatched"); self.mismatch_radio.pack(side="left", padx=5)
        self.tv_radio = ctk.CTkRadioButton(fallback_frame, text="TV", variable=self.fallback_var, value="tv"); self.tv_radio.pack(side="left", padx=5)
        self.anime_radio = ctk.CTkRadioButton(fallback_frame, text="Anime", variable=self.fallback_var, value="anime"); self.anime_radio.pack(side="left", padx=5)
        self.toggle_cleanup_mode_ui()

    # --- ADDED: Method to toggle log visibility ---
    def toggle_log_visibility(self):
        if self.log_is_visible:
            self.log_textbox.grid_remove()
            self.grid_rowconfigure(1, weight=0)  # Log's row no longer expands
            self.toggle_log_button.configure(text="Show Log")
        else:
            self.log_textbox.grid()  # grid() remembers previous settings
            self.grid_rowconfigure(1, weight=1)  # Log's row expands again
            self.toggle_log_button.configure(text="Hide Log")
        self.log_is_visible = not self.log_is_visible

    def on_media_type_toggled(self): self.update_fallback_ui_state()
    def update_fallback_ui_state(self):
        tv_enabled = self.enabled_vars['TV_SHOWS_ENABLED'].get(); anime_enabled = self.enabled_vars['ANIME_SERIES_ENABLED'].get()
        self.tv_radio.configure(state="normal" if tv_enabled else "disabled")
        self.anime_radio.configure(state="normal" if anime_enabled else "disabled")
        if not tv_enabled and self.fallback_var.get() == "tv": self.fallback_var.set("mismatched")
        if not anime_enabled and self.fallback_var.get() == "anime": self.fallback_var.set("mismatched")
    def _on_french_mode_toggled(self): self.toggle_french_dir_visibility(); self.check_and_prompt_for_path('FRENCH_MOVIES_DIR', self.fr_sauce_var)
    def check_and_prompt_for_path(self, dir_key: str, bool_var: ctk.BooleanVar):
        if bool_var.get() and dir_key in self.path_entries and not self.path_entries[dir_key].get().strip():
            logging.info(f"Path for {dir_key.replace('_', ' ').title()} is not set. Please select a folder.")
            self.browse_folder(self.path_entries[dir_key])
            if not self.path_entries[dir_key].get().strip(): logging.warning(f"No folder selected. Disabling feature."); bool_var.set(False)
    def stop_running_task(self):
        if self.sorter_instance: logging.warning("🛑 User initiated stop..."); self.sorter_instance.signal_stop()
    def toggle_cleanup_mode_ui(self):
        is_running = self.sorter_thread and self.sorter_thread.is_alive()
        if self.cleanup_var.get():
            self.sort_now_button.configure(text="Clean Up Source Directory", fg_color="#2E7D32", hover_color="#1B5E20"); self.watch_button.configure(state="disabled")
        else:
            self.sort_now_button.configure(text="Sort Now", fg_color=self.default_button_color, hover_color=self.default_hover_color)
            if not is_running: self.watch_button.configure(state="normal")
    def _create_path_entry_row(self, parent, row, dir_key, label_text):
        ctk.CTkLabel(parent, text=label_text).grid(row=row, column=0, padx=5, pady=5, sticky="w")
        entry = ctk.CTkEntry(parent, width=400); entry.grid(row=row, column=1, padx=5, pady=5, sticky="ew")
        entry.insert(0, getattr(self.config, dir_key, "")); self.path_entries[dir_key] = entry
        ctk.CTkButton(parent, text="Browse...", width=80, command=lambda e=entry: self.browse_folder(e)).grid(row=row, column=2, padx=5, pady=5)
        return row + 1
    def create_settings_tab(self, parent):
        parent.grid_columnconfigure(1, weight=1); self.path_entries = {}
        path_map = {'SOURCE_DIR': 'Source Directory', 'MOVIES_DIR': 'Movies Directory', 'TV_SHOWS_DIR': 'TV Shows Directory', 'ANIME_MOVIES_DIR': 'Anime Movies Directory', 'ANIME_SERIES_DIR': 'Anime Series Directory', 'MISMATCHED_DIR': 'Mismatched Files Directory'}
        row = 0
        for key, label in path_map.items(): row = self._create_path_entry_row(parent, row, key, label)
        self.fr_check = ctk.CTkCheckBox(parent, text="French Movies Directory", variable=self.fr_sauce_var, command=self._on_french_mode_toggled); self.fr_check.grid(row=row, column=0, padx=5, pady=5, sticky="w")
        self.french_dir_entry = ctk.CTkEntry(parent, width=400); self.french_dir_entry.insert(0, getattr(self.config, "FRENCH_MOVIES_DIR", "")); self.path_entries["FRENCH_MOVIES_DIR"] = self.french_dir_entry
        self.french_dir_browse = ctk.CTkButton(parent, text="Browse...", width=80, command=lambda e=self.french_dir_entry: self.browse_folder(e))
        self.toggle_french_dir_visibility(); row += 1
        ctk.CTkLabel(parent, text="Sidecar Extensions").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        self.sidecar_entry = ctk.CTkEntry(parent, placeholder_text=".srt, .nfo, .txt"); self.sidecar_entry.grid(row=row, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        if self.config.SIDECAR_EXTENSIONS: self.sidecar_entry.insert(0, ", ".join(self.config.SIDECAR_EXTENSIONS))
        row += 1
        ctk.CTkLabel(parent, text="Custom Strings to Remove").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        self.custom_strings_entry = ctk.CTkEntry(parent, placeholder_text="FRENCH, VOSTFR"); self.custom_strings_entry.grid(row=row, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        if self.config.CUSTOM_STRINGS_TO_REMOVE: self.custom_strings_entry.insert(0, ", ".join(self.config.CUSTOM_STRINGS_TO_REMOVE))
        row += 1
        ctk.CTkLabel(parent, text="OMDb API Key").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        self.api_key_entry = ctk.CTkEntry(parent, placeholder_text="Enter API key"); self.api_key_entry.grid(row=row, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        if self.config.OMDB_API_KEY and self.config.OMDB_API_KEY != "yourkey": self.api_key_entry.insert(0, self.config.OMDB_API_KEY); self.api_key_entry.configure(show="*")
        self.api_key_entry.bind("<Key>", lambda e: self.api_key_entry.configure(show="*")); row += 1
        ctk.CTkButton(parent, text="Save Settings", command=self.save_settings).grid(row=row, column=1, columnspan=2, padx=5, pady=10, sticky="e")
    def toggle_french_dir_visibility(self):
        row = 6
        if self.fr_sauce_var.get(): self.french_dir_entry.grid(row=row, column=1, padx=5, pady=5, sticky="ew"); self.french_dir_browse.grid(row=row, column=2, padx=5, pady=5)
        else: self.french_dir_entry.grid_remove(); self.french_dir_browse.grid_remove()
    def browse_folder(self, entry_widget):
        if folder_path := filedialog.askdirectory(initialdir=entry_widget.get() or str(Path.home())): entry_widget.delete(0, ctk.END); entry_widget.insert(0, folder_path)
    def save_settings(self): self.update_config_from_ui(); self.config.save(CONFIG_FILE); logging.info("✅ Settings saved to config.json"); self.tray_icon.update_menu()
    def update_config_from_ui(self):
        for key, entry in self.path_entries.items(): setattr(self.config, key, entry.get())
        for key, var in self.enabled_vars.items(): setattr(self.config, key, var.get())
        if api_key := self.api_key_entry.get(): self.config.OMDB_API_KEY = api_key
        self.config.SIDECAR_EXTENSIONS = {f".{ext.strip().lstrip('.')}" for ext in self.sidecar_entry.get().split(',') if ext.strip()}
        self.config.CUSTOM_STRINGS_TO_REMOVE = {s.strip().upper() for s in self.custom_strings_entry.get().split(',') if s.strip()}
        self.config.FRENCH_MODE_ENABLED = self.fr_sauce_var.get()
        self.config.CLEANUP_MODE_ENABLED = self.cleanup_var.get()
        self.config.FALLBACK_SHOW_DESTINATION = self.fallback_var.get()
        try: self.config.WATCH_INTERVAL = int(self.watch_interval_entry.get()) * 60
        except (ValueError, TypeError): self.config.WATCH_INTERVAL = 15 * 60
    
    def _update_progress(self, current_step: int, total_steps: int):
        self.after(0, self._update_progress_ui, current_step, total_steps)
    
    def _update_progress_ui(self, current_step: int, total_steps: int):
        if total_steps > 0:
            percentage = current_step / total_steps
            self.progress_bar.set(percentage)
            self.progress_label.configure(text=f"Processing: {current_step} / {total_steps}")
        else:
            self.progress_bar.set(0)
            self.progress_label.configure(text="No files to process.")

    def start_task(self, task_function, is_watcher=False):
        if self.is_quitting or (self.sorter_thread and self.sorter_thread.is_alive()): return
        self.update_config_from_ui(); self.is_watching = is_watcher
        is_valid, message = self.config.validate()
        if not is_valid: logging.error(f"Configuration error: {message}"); return
        if self.config.FRENCH_MODE_ENABLED and not self.config.CLEANUP_MODE_ENABLED: logging.info("🔵⚪🔴 French Mode is ENABLED.")
        if self.config.CLEANUP_MODE_ENABLED: logging.info("🧹 Clean Up Mode is ENABLED.")
        if self.dry_run_var.get(): logging.info("🧪 Dry Run is ENABLED for this task.")
        
        self.progress_frame.grid()
        self.progress_bar.set(0)
        self.progress_label.configure(text="Initializing...")
        
        self.sorter_instance = backend.MediaSorter(
            self.config, 
            dry_run=self.dry_run_var.get(),
            progress_callback=self._update_progress
        )
        self.sorter_thread = threading.Thread(target=task_function, args=(self.sorter_instance,), daemon=True)
        self.sorter_thread.start(); self.monitor_active_task()
        
    def start_sort_now(self): self.start_task(lambda sorter: sorter.process_source_directory(), is_watcher=False)
    def toggle_watch_mode(self):
        if self.sorter_thread and self.sorter_thread.is_alive(): self.stop_running_task()
        else: self.start_task(lambda sorter: sorter.start_watch_mode(), is_watcher=True)
    def monitor_active_task(self):
        if self.is_quitting: return
        is_running = self.sorter_thread and self.sorter_thread.is_alive()
        if is_running:
            self.sort_now_button.configure(state="disabled")
            self.watch_button.configure(text="Stop Watching" if self.is_watching else "Running...", state="normal" if self.is_watching else "disabled")
            if self.sorter_instance and self.sorter_instance.is_processing: 
                self.stop_button.configure(state="normal", text="STOP", fg_color="#D32F2F", hover_color="#B71C1C")
                if not self.progress_frame.winfo_viewable(): self.progress_frame.grid()
            elif self.is_watching: 
                self.stop_button.configure(state="disabled", text="IDLE", fg_color="#FBC02D", text_color="black")
                if self.progress_frame.winfo_viewable(): self.progress_frame.grid_remove()
            self.after(500, self.monitor_active_task)
        else:
            if self.is_watching: logging.info("✅ Watcher stopped.")
            else: logging.info("✅ Task finished.")
            self.sort_now_button.configure(state="normal"); self.watch_button.configure(text="Start Watching", state="normal")
            self.stop_button.configure(state="disabled", text="", fg_color="gray25")
            self.progress_frame.grid_remove()
            self.sorter_instance = None; self.sorter_thread = None; self.is_watching = False
            self.tray_icon.update_menu(); self.toggle_cleanup_mode_ui()
    
    def create_tray_image(self):
        try: return Image.open(str(resource_path("icon.png")))
        except Exception:
            image = Image.new('RGB', (64, 64), "#1F6AA5"); dc = ImageDraw.Draw(image)
            dc.rectangle((32, 0, 64, 32), fill="#144870"); dc.rectangle((0, 32, 32, 64), fill="#144870")
            return image
    def quit_app(self):
        if self.is_quitting: return
        self.is_quitting = True; logging.info("Shutting down...")
        self.tray_icon.stop()
        if self.sorter_instance: self.sorter_instance.signal_stop()
        if self.sorter_thread: self.sorter_thread.join(timeout=2)
        self.after(0, self._perform_safe_shutdown)
    def _perform_safe_shutdown(self): self.save_settings(); self.destroy()
    def show_window(self): self.deiconify(); self.lift(); self.attributes('-topmost', True); self.tab_view.set("Actions"); self.after(100, lambda: self.attributes('-topmost', False))
    def show_settings(self): self.show_window(); self.tab_view.set("Settings")
    def hide_to_tray(self): self.withdraw(); self.tray_icon.notify('App is running in the background', 'SortMeDown')
    def on_minimize(self, event):
        if self.state() == 'iconic': self.hide_to_tray()
    def set_interval(self, minutes: int):
        logging.info(f"Watch interval set to {minutes} minutes.")
        self.watch_interval_entry.delete(0, ctk.END); self.watch_interval_entry.insert(0, str(minutes)); self.save_settings() 
    def setup_tray_icon(self):
        image = self.create_tray_image()
        menu = (
            pystray.MenuItem('Show', self.show_window, default=True), pystray.MenuItem('Settings', self.show_settings), pystray.Menu.SEPARATOR,
            pystray.MenuItem('Enable Watch', self.toggle_watch_mode, checked=lambda item: self.is_watching),
            pystray.MenuItem('Set Interval', pystray.Menu(
                pystray.MenuItem('5 minutes', lambda: self.set_interval(5), radio=True, checked=lambda i: self.config.WATCH_INTERVAL == 300),
                pystray.MenuItem('15 minutes', lambda: self.set_interval(15), radio=True, checked=lambda i: self.config.WATCH_INTERVAL == 900),
                pystray.MenuItem('30 minutes', lambda: self.set_interval(30), radio=True, checked=lambda i: self.config.WATCH_INTERVAL == 1800),
                pystray.MenuItem('60 minutes', lambda: self.set_interval(60), radio=True, checked=lambda i: self.config.WATCH_INTERVAL == 3600))),
            pystray.Menu.SEPARATOR, pystray.MenuItem('Quit', self.quit_app)
        )
        self.tray_icon = pystray.Icon("sortmedown", image, "SortMeDown Sorter", menu); threading.Thread(target=self.tray_icon.run, daemon=True).start()

if __name__ == "__main__":
    app = App()
    app.mainloop()
