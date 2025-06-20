# gui.py
"""
SortMeDown Media Sorter - GUI (gui.py) for bang bang 
================================

v6.1 Release
 
v6.0.8
- BUG FIX: Corrected a race condition when using tray menu shortcuts,
  ensuring the correct tab is always displayed instead of a blank panel.
- ENHANCED: The "About" tab now automatically hides the main log panel,
  providing a cleaner, dedicated view for version information.

v6.0.7
- FEATURE: Replaced the "About" dialog with a dedicated "About" tab in the
  main interface for easier access to version history.
- FEATURE: Updated the system tray icon menu to include direct shortcuts
  to the "Review" and "About" tabs.
- ENHANCED: Cleaned up the main window's bottom bar layout.

v6.0.6
- FEATURE: Added version number to the main window title and a new status bar.
- FEATURE: Added an "About" dialog, accessible from the status bar, which
  displays the application's version history.

v6.0.5
- ENHANCED: The autofilled name in the 'Review' tab now correctly preserves
  the year from the filename while still removing other junk metadata. For
  example, 'My.Movie.2024.1080p.mkv' will now suggest 'My Movie (2024)'.

v6.0.4
- BUG FIX: Fixed a crash when switching to the 'Review' tab by correcting the
  on_tab_selected callback to properly get the current tab's name. This also
  ensures the automatic scan-on-entry feature works correctly.

v6.0.3
- ENHANCED: Major UX improvements to the 'Review' tab:
  - Tab now automatically scans for files upon entry.
  - Scan button renamed to 'Rescan for Files'.
  - File selection is now single-click and more reliable (switched to RadioButtons).
  - Selecting a file now autofills the entry box with a cleaned title,
    providing a much better starting point for corrections.

v6.0.2
- ENHANCED: Improved the UI in the 'Review' tab. The instruction label is
  clearer, and selecting a file now autofills the entry box with the file's
  name (stem) to provide a better starting point for corrections.

v6.0.1
- BUG FIX: Fixed a crash in the 'Review' tab when scanning for files, caused by
  an unsupported 'text_align' argument in the CTkButton widget.
...
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
import logging
import threading
from pathlib import Path
from PIL import Image, ImageDraw
import pystray
import sys
import tkinter
import os
import datetime
import webbrowser

import bangbang as backend

CONFIG_FILE = Path("config.json")

def get_version_info():
    """Parses the module's docstring to get version and history."""
    doc = __doc__ or ""
    lines = doc.strip().split('\n')
    
    version = "v?.?.?"
    history_content = []
    
    # Find the latest version (first one mentioned)
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('v'):
            version = stripped.split()[0]
            break
    
    # Find the start of the changelog section
    changelog_started = False
    for line in lines:
        if line.strip().startswith('v'):
            changelog_started = True
        if changelog_started:
            history_content.append(line)
            
    history = "\n".join(history_content) if history_content else "Version history not found."
        
    return version, history

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
        
        self.version, self.version_history = get_version_info()
        self.title(f"SortMeDown Media Sorter {self.version}"); self.geometry("900x850"); ctk.set_appearance_mode("Dark")
        self.after(200, self._set_window_icon)
        
        self.config = backend.Config.load(CONFIG_FILE)
        self.sorter_thread = None; self.sorter_instance = None; self.tray_icon = None; self.tray_thread = None; self.tab_view = None
        self.is_quitting = False; self.path_entries = {}; self.mismatch_buttons = {}; self.default_button_color = None; self.default_hover_color = None
        self.is_watching = False
        self.log_is_visible = True
        self.selected_mismatched_file = None
        
        self.api_provider_var = ctk.StringVar(value=self.config.API_PROVIDER)

        self.enabled_vars = {
            'MOVIES_ENABLED': ctk.BooleanVar(value=self.config.MOVIES_ENABLED),
            'TV_SHOWS_ENABLED': ctk.BooleanVar(value=self.config.TV_SHOWS_ENABLED),
            'ANIME_MOVIES_ENABLED': ctk.BooleanVar(value=self.config.ANIME_MOVIES_ENABLED),
            'ANIME_SERIES_ENABLED': ctk.BooleanVar(value=self.config.ANIME_SERIES_ENABLED),
        }
        self.dry_run_var = ctk.BooleanVar(value=False)
        self.cleanup_var = ctk.BooleanVar(value=self.config.CLEANUP_MODE_ENABLED)
        self.fallback_var = ctk.StringVar(value=self.config.FALLBACK_SHOW_DESTINATION)
        
        # Configure the main grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # Row for controls (non-expanding)
        self.grid_rowconfigure(1, weight=1)  # Row for log panel (expanding by default)
        self.grid_rowconfigure(2, weight=0)  # Row for progress bar (non-expanding)

        self.controls_frame = ctk.CTkFrame(self); self.controls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.create_controls()
        
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", font=("Courier New", 12))
        self.log_textbox.grid(row=1, column=0, padx=10, pady=(0,5), sticky="nsew")

        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.progress_frame.grid_columnconfigure(0, weight=1)
        
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="")
        self.progress_label.grid(row=0, column=0, sticky="w", padx=5)
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=5)

        self.version_label = ctk.CTkLabel(self.progress_frame, text=self.version, text_color="gray50")
        self.version_label.grid(row=0, column=1, rowspan=2, padx=(10, 5), sticky="e")
        
        self.progress_frame.grid_remove()

        self.setup_logging()
        self.protocol("WM_DELETE_WINDOW", self.quit_app)
        self.bind("<Unmap>", self.on_minimize)
        self.setup_tray_icon()
        self.update_fallback_ui_state()
        
    def _set_window_icon(self):
        try:
            if sys.platform == "win32":
                self.iconbitmap(str(resource_path("icon.ico")))
            else:
                self.iconphoto(True, tkinter.PhotoImage(file=str(resource_path("icon.png"))))
        except Exception as e:
            logging.warning(f"Could not set window icon: {e}")

    def setup_logging(self):
        log_handler = GuiLoggingHandler(self.log_textbox)
        log_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s", "%H:%M:%S"))
        logging.basicConfig(level=logging.INFO, handlers=[log_handler], force=True)
        
    def create_controls(self):
        self.tab_view = ctk.CTkTabview(self.controls_frame)
        self.tab_view.pack(expand=True, fill="both", padx=5, pady=5)
        
        self.create_actions_tab(self.tab_view.add("Actions"))
        self.create_settings_tab(self.tab_view.add("Settings"))
        self.create_mismatch_tab(self.tab_view.add("Review"))
        self.create_about_tab(self.tab_view.add("About"))
        
        self.tab_view.configure(command=self.on_tab_selected)
        self.tab_view.set("Actions")

    def on_tab_selected(self):
        tab_name = self.tab_view.get()
        if tab_name == "Review":
            self.scan_mismatched_files()
        
        # Dynamically change the main grid layout based on the selected tab
        if tab_name == "About":
            # Hide log panel
            self.log_textbox.grid_remove()
            # Make the controls_frame (row 0) expand, and the log's row (row 1) not expand
            self.grid_rowconfigure(0, weight=1)
            self.grid_rowconfigure(1, weight=0)
        else:
            # Restore default layout: controls fixed, log expands
            self.grid_rowconfigure(0, weight=0)
            self.grid_rowconfigure(1, weight=1)
            # Show the log panel if it's supposed to be visible
            if self.log_is_visible:
                self.log_textbox.grid()
            else:
                self.log_textbox.grid_remove()

    def create_actions_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        button_bar_frame = ctk.CTkFrame(parent, fg_color="transparent"); button_bar_frame.grid(row=0, column=0, sticky="ew")
        button_bar_frame.grid_columnconfigure((0, 2), weight=1); button_bar_frame.grid_columnconfigure(1, weight=0)
        
        self.sort_now_button = ctk.CTkButton(button_bar_frame, text="Single Shot Sort", command=self.start_sort_now)
        self.sort_now_button.grid(row=0, column=0, padx=(0, 5), pady=10, sticky="ew")
        self.default_button_color = self.sort_now_button.cget("fg_color"); self.default_hover_color = self.sort_now_button.cget("hover_color")
        
        self.stop_button = ctk.CTkButton(button_bar_frame, text="", width=60, command=self.stop_running_task, fg_color="gray25", border_width=0, state="disabled"); self.stop_button.grid(row=0, column=1, padx=5, pady=10)
        
        self.watch_button = ctk.CTkButton(button_bar_frame, text="Launch Watchdog", command=self.toggle_watch_mode)
        self.watch_button.grid(row=0, column=2, padx=(5, 0), pady=10, sticky="ew")
        
        options_frame = ctk.CTkFrame(parent, fg_color="transparent"); options_frame.grid(row=2, column=0, columnspan=3, sticky="ew")
        options_frame.grid_columnconfigure((0,1), weight=1)
        self.dry_run_checkbox = ctk.CTkCheckBox(options_frame, text="Dry Run", variable=self.dry_run_var)
        self.dry_run_checkbox.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.cleanup_checkbox = ctk.CTkCheckBox(options_frame, text="Clean Up Source (disables Watch & Fallback)", variable=self.cleanup_var, command=self.toggle_cleanup_mode_ui)
        self.cleanup_checkbox.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        
        watch_interval_frame = ctk.CTkFrame(options_frame, fg_color="transparent"); watch_interval_frame.grid(row=0, column=1, padx=5, pady=5, sticky="e")
        ctk.CTkLabel(watch_interval_frame, text="Check every").pack(side="left", padx=(0,5))
        self.watch_interval_entry = ctk.CTkEntry(watch_interval_frame, width=40); self.watch_interval_entry.pack(side="left"); self.watch_interval_entry.insert(0, str(self.config.WATCH_INTERVAL // 60))
        ctk.CTkLabel(watch_interval_frame, text="minutes").pack(side="left", padx=(5,0))
        
        self.toggle_log_button = ctk.CTkButton(options_frame, text="Hide Log", width=100, command=self.toggle_log_visibility)
        self.toggle_log_button.grid(row=1, column=1, sticky="e", padx=5, pady=5)
        
        ctk.CTkFrame(parent, height=2, fg_color="gray25").grid(row=3, column=0, pady=(10, 5), sticky="ew") 
        self.toggles_frame = ctk.CTkFrame(parent, fg_color="transparent"); self.toggles_frame.grid(row=4, column=0, sticky="ew", pady=(0, 5)) 
        self.toggles_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        self.toggles_map = {}
        action_toggles_map = {'Movies': 'MOVIES_ENABLED', 'TV Shows': 'TV_SHOWS_ENABLED', 'Anime Movies': 'ANIME_MOVIES_ENABLED', 'Anime': 'ANIME_SERIES_ENABLED'}
        for i, (label, enable_key) in enumerate(action_toggles_map.items()):
            cb = ctk.CTkCheckBox(self.toggles_frame, text=label, variable=self.enabled_vars[enable_key], command=self.on_media_type_toggled)
            cb.grid(row=0, column=i, padx=5, pady=5)
            self.toggles_map[enable_key] = cb
        
        self.fallback_frame = ctk.CTkFrame(parent, fg_color="transparent"); self.fallback_frame.grid(row=5, column=0, pady=5, sticky="ew")
        ctk.CTkLabel(self.fallback_frame, text="For mismatched shows, default to:").pack(side="left", padx=(5,10))
        self.ignore_radio = ctk.CTkRadioButton(self.fallback_frame, text="Do Nothing", variable=self.fallback_var, value="ignore"); self.ignore_radio.pack(side="left", padx=5)
        self.mismatch_radio = ctk.CTkRadioButton(self.fallback_frame, text="Mismatched Folder", variable=self.fallback_var, value="mismatched"); self.mismatch_radio.pack(side="left", padx=5)
        self.tv_radio = ctk.CTkRadioButton(self.fallback_frame, text="TV Shows Folder", variable=self.fallback_var, value="tv"); self.tv_radio.pack(side="left", padx=5)
        self.anime_radio = ctk.CTkRadioButton(self.fallback_frame, text="Anime Folder", variable=self.fallback_var, value="anime")
        self.anime_radio.pack(side="left", padx=5)
        self.toggle_cleanup_mode_ui()

    def create_mismatch_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        controls_frame = ctk.CTkFrame(parent, fg_color="transparent")
        controls_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        ctk.CTkButton(controls_frame, text="Rescan for Files", command=self.scan_mismatched_files).pack(side="left")

        main_frame = ctk.CTkFrame(parent, fg_color="transparent")
        main_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)
        
        self.mismatched_files_frame = ctk.CTkScrollableFrame(main_frame, label_text="Files Found in Mismatched Folder")
        self.mismatched_files_frame.grid(row=0, column=0, sticky="nsew", padx=(0,5))
        
        action_panel = ctk.CTkFrame(main_frame)
        action_panel.grid(row=0, column=1, sticky="nsew", padx=(5,0))
        action_panel.grid_columnconfigure(0, weight=1)
        
        self.mismatch_selected_label = ctk.CTkLabel(action_panel, text="No file selected.", wraplength=350, justify="left")
        self.mismatch_selected_label.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        ctk.CTkLabel(action_panel, text="Enter correct name: Title (Year)").grid(row=1, column=0, sticky="w", padx=10)
        self.mismatch_name_entry = ctk.CTkEntry(action_panel)
        self.mismatch_name_entry.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        
        action_button_frame = ctk.CTkFrame(action_panel, fg_color="transparent")
        action_button_frame.grid(row=3, column=0, sticky="ew", pady=10)
        action_button_frame.grid_columnconfigure((0,1), weight=1)
        
        self.mismatch_reprocess_button = ctk.CTkButton(action_button_frame, text="Re-process (API)", command=self.reprocess_selected_file)
        self.mismatch_reprocess_button.grid(row=0, column=0, padx=(10,5), sticky="ew")
        
        self.mismatch_delete_button = ctk.CTkButton(action_button_frame, text="Delete File", fg_color="#D32F2F", hover_color="#B71C1C", command=self.delete_selected_file)
        self.mismatch_delete_button.grid(row=0, column=1, padx=(5,10), sticky="ew")

        force_frame = ctk.CTkFrame(action_panel)
        force_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=(20, 0))
        force_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(force_frame, text="Force as (bypasses API):").grid(row=0, column=0, sticky="w", padx=5)
        force_buttons_frame = ctk.CTkFrame(force_frame, fg_color="transparent")
        force_buttons_frame.grid(row=1, column=0, sticky="ew", pady=5)
        force_buttons_frame.grid_columnconfigure((0,1), weight=1)
        
        self.force_movie_btn = ctk.CTkButton(force_buttons_frame, text="Movie", command=lambda: self.force_reprocess_file(backend.MediaType.MOVIE))
        self.force_tv_btn = ctk.CTkButton(force_buttons_frame, text="TV Show", command=lambda: self.force_reprocess_file(backend.MediaType.TV_SERIES))
        self.force_anime_series_btn = ctk.CTkButton(force_buttons_frame, text="Anime", command=lambda: self.force_reprocess_file(backend.MediaType.ANIME_SERIES))
        self.force_anime_movie_btn = ctk.CTkButton(force_buttons_frame, text="Anime Movie", command=lambda: self.force_reprocess_file(backend.MediaType.ANIME_MOVIE))
        self.force_split_lang_movie_btn = ctk.CTkButton(force_buttons_frame, text="Split Lang Movie", command=lambda: self.force_reprocess_file(backend.MediaType.MOVIE, is_split_lang_override=True))
        
        self.force_movie_btn.grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        self.force_tv_btn.grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        self.force_anime_series_btn.grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        self.force_anime_movie_btn.grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        self.force_split_lang_movie_btn.grid(row=2, column=0, padx=2, pady=2, sticky="ew")

        self._update_mismatch_panel_state()
        
    def create_settings_tab(self, parent):
        parent.grid_columnconfigure(1, weight=1); self.path_entries = {}
        row = 0
        
        path_map = {'SOURCE_DIR': 'Source Directory', 'MOVIES_DIR': 'Movies Directory', 'TV_SHOWS_DIR': 'TV Shows Directory', 'ANIME_MOVIES_DIR': 'Anime Movies Directory', 'ANIME_SERIES_DIR': 'Anime Series Directory', 'MISMATCHED_DIR': 'Mismatched Files Directory'}
        for key, label in path_map.items(): row = self._create_path_entry_row(parent, row, key, label)
        
        ctk.CTkLabel(parent, text="Split Language Movies Dir").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        self.split_movies_dir_entry = ctk.CTkEntry(parent, width=400)
        self.split_movies_dir_entry.insert(0, getattr(self.config, "SPLIT_MOVIES_DIR", ""))
        self.path_entries["SPLIT_MOVIES_DIR"] = self.split_movies_dir_entry
        ctk.CTkButton(parent, text="Browse...", width=80, command=lambda e=self.split_movies_dir_entry: self.browse_folder(e)).grid(row=row, column=2, padx=5, pady=5)
        self.split_movies_dir_entry.grid(row=row, column=1, padx=5, pady=5, sticky="ew")
        row += 1
        
        ctk.CTkLabel(parent, text="Languages to Split").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        self.split_languages_entry = ctk.CTkEntry(parent, placeholder_text='e.g., fr, es, de, all')
        self.split_languages_entry.grid(row=row, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        if self.config.LANGUAGES_TO_SPLIT:
            self.split_languages_entry.insert(0, ", ".join(self.config.LANGUAGES_TO_SPLIT))
        row += 1

        ctk.CTkLabel(parent, text="Sidecar Extensions").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        self.sidecar_entry = ctk.CTkEntry(parent, placeholder_text=".srt, .nfo, .txt"); self.sidecar_entry.grid(row=row, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        if self.config.SIDECAR_EXTENSIONS: self.sidecar_entry.insert(0, ", ".join(self.config.SIDECAR_EXTENSIONS))
        row += 1
        
        ctk.CTkLabel(parent, text="Custom Strings to Remove").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        self.custom_strings_entry = ctk.CTkEntry(parent, placeholder_text="FRENCH, VOSTFR"); self.custom_strings_entry.grid(row=row, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        if self.config.CUSTOM_STRINGS_TO_REMOVE: self.custom_strings_entry.insert(0, ", ".join(self.config.CUSTOM_STRINGS_TO_REMOVE))
        row += 1
        
        ctk.CTkLabel(parent, text="Primary Provider").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        ctk.CTkSegmentedButton(parent, values=["omdb", "tmdb"], variable=self.api_provider_var).grid(row=row, column=1, padx=5, pady=5, sticky="w")
        row += 1

        ctk.CTkLabel(parent, text="OMDb API Key").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        omdb_api_frame = ctk.CTkFrame(parent, fg_color="transparent")
        omdb_api_frame.grid(row=row, column=1, columnspan=2, sticky="ew")
        omdb_api_frame.grid_columnconfigure(0, weight=1)
        self.omdb_api_key_entry = ctk.CTkEntry(omdb_api_frame, placeholder_text="Enter OMDb API key"); self.omdb_api_key_entry.grid(row=0, column=0, sticky="ew")
        if self.config.OMDB_API_KEY and self.config.OMDB_API_KEY != "yourkey": self.omdb_api_key_entry.insert(0, self.config.OMDB_API_KEY); self.omdb_api_key_entry.configure(show="*")
        self.omdb_api_key_entry.bind("<Key>", lambda e: self.omdb_api_key_entry.configure(show="*"))
        ctk.CTkButton(omdb_api_frame, text="Test Key", width=80, command=lambda: self.test_api_key_clicked("omdb")).grid(row=0, column=1, padx=(10,0))
        row += 1

        ctk.CTkLabel(parent, text="TMDB API Key").grid(row=row, column=0, padx=5, pady=5, sticky="w")
        tmdb_api_frame = ctk.CTkFrame(parent, fg_color="transparent")
        tmdb_api_frame.grid(row=row, column=1, columnspan=2, sticky="ew")
        tmdb_api_frame.grid_columnconfigure(0, weight=1)
        self.tmdb_api_key_entry = ctk.CTkEntry(tmdb_api_frame, placeholder_text="Enter TMDB API key")
        self.tmdb_api_key_entry.grid(row=0, column=0, sticky="ew")
        if self.config.TMDB_API_KEY and self.config.TMDB_API_KEY != "yourkey":
            self.tmdb_api_key_entry.insert(0, self.config.TMDB_API_KEY)
            self.tmdb_api_key_entry.configure(show="*")
        self.tmdb_api_key_entry.bind("<Key>", lambda e: self.tmdb_api_key_entry.configure(show="*"))
        ctk.CTkLabel(tmdb_api_frame, text="(Optional, for fallback)", text_color="gray50").grid(row=0, column=1, padx=10)
        ctk.CTkButton(tmdb_api_frame, text="Test Key", width=80, command=lambda: self.test_api_key_clicked("tmdb")).grid(row=0, column=2)
        row += 1

        ctk.CTkButton(parent, text="Save Settings", command=self.save_settings).grid(row=row, column=1, columnspan=2, padx=5, pady=10, sticky="e")
    
    # --- START: MODIFIED METHOD ---
    def create_about_tab(self, parent):
        # Configure grid layout: 3 rows. ASCII (fixed), Main Info (expands), History (fixed)
        parent.grid_rowconfigure(0, weight=0) 
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_rowconfigure(2, weight=0)
        parent.grid_columnconfigure(0, weight=1)

        def open_url(url):
            webbrowser.open_new_tab(url)

        # --- ASCII Art Banner ---
        ascii_art = """    ██████  ▒█████   ██▀███  ▄▄▄█████▓    ███▄ ▄███▓▓█████    ▓█████▄  ▒█████   █     █░███▄    █ 
  ▒██    ▒ ▒██▒  ██▒▓██ ▒ ██▒▓  ██▒ ▓▒   ▓██▒▀█▀ ██▒▓█   ▀    ▒██▀ ██▌▒██▒  ██▒▓█░ █ ░█░██ ▀█   █ 
  ░ ▓██▄   ▒██░  ██▒▓██ ░▄█ ▒▒ ▓██░ ▒░   ▓██    ▓██░▒███      ░██   █▌▒██░  ██▒▒█░ █ ░█▓██  ▀█ ██▒
    ▒   ██▒▒██   ██░▒██▀▀█▄  ░ ▓██▓ ░    ▒██    ▒██ ▒▓█  ▄    ░▓█▄   ▌▒██   ██░░█░ █ ░█▓██▒  ▐▌██▒
  ▒██████▒▒░ ████▓▒░░██▓ ▒██▒  ▒██▒ ░    ▒██▒   ░██▒░▒████▒   ░▒████▓ ░ ████▓▒░░░██▒██▓▒██░   ▓██░
  ▒ ▒▓▒ ▒ ░░ ▒░▒░▒░ ░ ▒▓ ░▒▓░  ▒ ░░      ░ ▒░   ░  ░░░ ▒░ ░    ▒▒▓  ▒ ░ ▒░▒░▒░ ░ ▓░▒ ▒ ░ ▒░   ▒ ▒ 
  ░ ░▒  ░ ░  ░ ▒ ▒░   ░▒ ░ ▒░    ░       ░  ░      ░ ░ ░  ░    ░ ▒  ▒   ░ ▒ ▒░   ▒ ░ ░ ░ ░░   ░ ▒░
  ░  ░  ░  ░ ░ ░ ▒    ░░   ░   ░         ░      ░      ░       ░ ░  ░ ░ ░ ░ ▒    ░   ░    ░   ░ ░ 
        ░      ░ ░      ░                        ░      ░  ░      ░        ░ ░        ░        ░   
                              a BangBang GUI                                                """

        # --- FIX: Use a CTkLabel for the ASCII art with a monospace font ---
        ascii_label = ctk.CTkLabel(parent, text=ascii_art, font=ctk.CTkFont(family="Courier", size=8), justify="left")
        ascii_label.grid(row=0, column=0, padx=10, pady=(10,0), sticky="ew")

        # --- Middle Box: Creator & License Info ---
        top_textbox = ctk.CTkTextbox(parent, wrap="word", font=("Segoe UI", 14), corner_radius=6)
        top_textbox.grid(row=1, column=0, padx=10, pady=(5, 5), sticky="nsew")
        top_textbox.insert("end", "\n")

        top_textbox.insert("end", "🗡️ Some tools aren't just built—they're forged. 🗡️\n\n")
        top_textbox.insert("end", "Created with ❤️by: Frederic LM\n\n")
        top_textbox.insert("end", "This little tool was crafted with love during countless late nights ☕🌙\n")
        top_textbox.insert("end", "fueled by passion, persistence, and the dream of making our digital life smoother.\n\n")
        top_textbox.insert("end", "If SortMeDown has sorted you out, saved you time,\n")
        top_textbox.insert("end", "or simply made your day a bit brighter, consider spreading some joy back. \n\n")
        top_textbox.insert("end", "Every contribution—no matter how small—keeps the fire burning\n")
        top_textbox.insert("end", "and helps me build more tools with care and precision. 🚀\n\n")

        # Single-line contribution link
        contrib_texts = [
            ("🍺 Buy Me a beer", "https://coff.ee/drmcwormd"),
        ]

        for i, (text, url) in enumerate(contrib_texts):
            link_tag = f"link-{text.replace(' ', '').replace('(', '').replace(')', '').replace('!', '')}"
            top_textbox.tag_config(link_tag, foreground="#6495ED", underline=True)
            top_textbox.tag_bind(link_tag, "<Button-1>", lambda e, u=url: open_url(u))
            top_textbox.tag_bind(link_tag, "<Enter>", lambda e: top_textbox.configure(cursor="hand2"))
            top_textbox.tag_bind(link_tag, "<Leave>", lambda e: top_textbox.configure(cursor=""))
            top_textbox.insert("end", f"{text}", link_tag)
            if i < len(contrib_texts) - 1:
                top_textbox.insert("end", " | ")

        # Insert "Happy sorting! 📁" and clickable 🎯 icon separately
        top_textbox.insert("end", "\n\nHappy sorting! 📁")

        # Create 🎯 as an easter egg link
        easter_egg_url = "https://youtu.be/HPCdBJMkN5A?si=UxQbUUR7x6T-EWSL"
        easter_egg_tag = "link-easter-egg"
        top_textbox.tag_config(easter_egg_tag, foreground="#6495ED", underline=True)
        top_textbox.tag_bind(easter_egg_tag, "<Button-1>", lambda e: open_url(easter_egg_url))
        top_textbox.tag_bind(easter_egg_tag, "<Enter>", lambda e: top_textbox.configure(cursor="hand2"))
        top_textbox.tag_bind(easter_egg_tag, "<Leave>", lambda e: top_textbox.configure(cursor=""))
        top_textbox.insert("end", "🎯", easter_egg_tag)
        top_textbox.insert("end", "\n\n")

        # License text
        top_textbox.insert("end", f"This software is free and open-source. Apache-2.0 license, Copyright (c) {datetime.date.today().year}\n")

        # Center everything
        top_textbox.tag_config("center", justify="center")
        top_textbox.tag_add("center", "1.0", "end")

        # Make textbox read-only
        top_textbox.configure(state="disabled")
        

        # --- Bottom Box: Version History ---
        history_frame = ctk.CTkFrame(parent)
        history_frame.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="nsew")
        history_frame.grid_columnconfigure(0, weight=1)
        history_frame.grid_rowconfigure(1, weight=1)

        label = ctk.CTkLabel(history_frame, text="Version History", font=ctk.CTkFont(weight="bold"))
        label.grid(row=0, column=0, padx=10, pady=(5, 2), sticky="w")

        bottom_textbox = ctk.CTkTextbox(history_frame, wrap="word", font=("Courier New", 12))
        bottom_textbox.grid(row=1, column=0, padx=10, pady=(2, 10), sticky="nsew")
        bottom_textbox.insert("1.0", self.version_history)
        bottom_textbox.configure(state="disabled", height=200) # Adjusted height for better balance
    # --- END: MODIFIED METHOD ---

    def _set_options_state(self, state: str):
        self.dry_run_checkbox.configure(state=state)
        self.cleanup_checkbox.configure(state=state)
        self.watch_interval_entry.configure(state=state)
        for checkbox in self.toggles_map.values():
            checkbox.configure(state=state)
        for radio_button in [self.ignore_radio, self.mismatch_radio, self.tv_radio, self.anime_radio]:
            radio_button.configure(state=state)
        if state == "normal":
            self.update_fallback_ui_state()
            self.toggle_cleanup_mode_ui()

    def _update_mismatch_panel_state(self):
        is_file_selected = self.selected_mismatched_file is not None
        state = "normal" if is_file_selected else "disabled"
        self.mismatch_name_entry.configure(state=state)
        self.mismatch_reprocess_button.configure(state=state)
        self.mismatch_delete_button.configure(state=state)
        
        self.force_movie_btn.configure(state=state)
        self.force_tv_btn.configure(state=state)
        self.force_anime_series_btn.configure(state=state)
        self.force_anime_movie_btn.configure(state=state)
        split_dir_path = self.path_entries.get('SPLIT_MOVIES_DIR', ctk.CTkEntry(self)).get()
        split_state = state if split_dir_path else "disabled"
        self.force_split_lang_movie_btn.configure(state=split_state)

        if not is_file_selected:
            self.mismatch_selected_label.configure(text="No file selected.")
            self.mismatch_name_entry.delete(0, ctk.END)
        else:
            self.mismatch_selected_label.configure(text=f"Selected: {self.selected_mismatched_file.name}")

    def scan_mismatched_files(self):
        for widget in self.mismatched_files_frame.winfo_children():
            widget.destroy()
        
        self.mismatch_buttons = {}
        self.selected_mismatched_file = None
        self._update_mismatch_panel_state()

        mismatched_dir = self.config.get_path('MISMATCHED_DIR') or (self.config.get_path('SOURCE_DIR') / '_Mismatched' if self.config.get_path('SOURCE_DIR') else None)
        if not mismatched_dir or not mismatched_dir.exists():
            logging.warning("Mismatched directory not found or not set.")
            ctk.CTkLabel(self.mismatched_files_frame, text="Mismatched directory not configured or found.").pack()
            return

        media_files = [p for ext in self.config.SUPPORTED_EXTENSIONS for p in mismatched_dir.glob(f'**/*{ext}') if p.is_file()]
        if not media_files:
            ctk.CTkLabel(self.mismatched_files_frame, text="No media files found.").pack()
            return

        sorted_media_files = sorted(media_files, key=lambda p: p.name)
        for file_path in sorted_media_files:
            btn = ctk.CTkButton(self.mismatched_files_frame, text=file_path.name,
                                command=lambda f=file_path: self.select_mismatched_file(f),
                                fg_color="transparent", anchor="w")
            btn.pack(fill="x", padx=2, pady=2)
            self.mismatch_buttons[file_path] = btn
            
        if sorted_media_files:
            self.after(50, lambda: self.select_mismatched_file(sorted_media_files[0]))

    def select_mismatched_file(self, file_path: Path):
        """Callback for file selection. Updates state, autofills entry, and highlights button."""
        self.selected_mismatched_file = file_path
        
        for path, button in self.mismatch_buttons.items():
            if path == file_path:
                button.configure(fg_color=self.default_button_color)
            else:
                button.configure(fg_color="transparent")
        
        self.update_config_from_ui()
        
        file_stem = self.selected_mismatched_file.stem
        
        clean_title = backend.TitleCleaner.clean_for_search(file_stem, self.config.CUSTOM_STRINGS_TO_REMOVE)
        year = backend.TitleCleaner.extract_year(file_stem)

        if year:
            suggested_name = f"{clean_title} ({year})"
        else:
            suggested_name = clean_title
        
        self.mismatch_name_entry.delete(0, ctk.END)
        self.mismatch_name_entry.insert(0, suggested_name)
        
        self._update_mismatch_panel_state()
    
    def reprocess_selected_file(self):
        if not self.selected_mismatched_file: return
        new_name = self.mismatch_name_entry.get().strip()
        if not new_name:
            messagebox.showwarning("Input Required", "Please enter a corrected name for the file.")
            return

        def _task():
            temp_sorter = backend.MediaSorter(self.config, dry_run=self.dry_run_var.get())
            temp_sorter.sort_item(self.selected_mismatched_file, override_name=new_name)
            self.after(0, self.scan_mismatched_files)
        
        threading.Thread(target=_task, daemon=True).start()

    def force_reprocess_file(self, media_type: backend.MediaType, is_split_lang_override: bool = False):
        if not self.selected_mismatched_file: return
        folder_name = self.mismatch_name_entry.get().strip()
        if not folder_name:
            messagebox.showwarning("Input Required", "Please enter a name for the folder (e.g., 'My Movie (2024)').")
            return

        def _task():
            temp_sorter = backend.MediaSorter(self.config, dry_run=self.dry_run_var.get())
            temp_sorter.force_move_item(self.selected_mismatched_file, folder_name, media_type, is_split_lang_override=is_split_lang_override)
            self.after(0, self.scan_mismatched_files)

        threading.Thread(target=_task, daemon=True).start()

    def delete_selected_file(self):
        if not self.selected_mismatched_file: return
        if not messagebox.askyesno("Confirm Deletion", f"Are you sure you want to permanently delete '{self.selected_mismatched_file.name}' and its sidecar files?"):
            return

        def _task():
            fm = backend.FileManager(self.config, dry_run=self.dry_run_var.get())
            fm.delete_file_group(self.selected_mismatched_file)
            self.after(0, self.scan_mismatched_files)
            
        threading.Thread(target=_task, daemon=True).start()

    def toggle_log_visibility(self):
        if self.log_is_visible:
            self.log_textbox.grid_remove()
            self.toggle_log_button.configure(text="Show Log")
        else:
            # Only show log if not on About tab
            if self.tab_view.get() != "About":
                self.log_textbox.grid()
            self.toggle_log_button.configure(text="Hide Log")
        self.log_is_visible = not self.log_is_visible

    def on_media_type_toggled(self): self.update_fallback_ui_state()
    def update_fallback_ui_state(self):
        tv_enabled = self.enabled_vars['TV_SHOWS_ENABLED'].get(); anime_enabled = self.enabled_vars['ANIME_SERIES_ENABLED'].get()
        self.tv_radio.configure(state="normal" if tv_enabled else "disabled")
        self.anime_radio.configure(state="normal" if anime_enabled else "disabled")
        if not tv_enabled and self.fallback_var.get() == "tv": self.fallback_var.set("mismatched")
        if not anime_enabled and self.fallback_var.get() == "anime": self.fallback_var.set("mismatched")
        
    def _on_french_mode_toggled(self):
        self._update_mismatch_panel_state()

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
            self.sort_now_button.configure(text="Single Shot Sort", fg_color=self.default_button_color, hover_color=self.default_hover_color)
            if not is_running: self.watch_button.configure(state="normal")
    def _create_path_entry_row(self, parent, row, dir_key, label_text):
        ctk.CTkLabel(parent, text=label_text).grid(row=row, column=0, padx=5, pady=5, sticky="w")
        entry = ctk.CTkEntry(parent, width=400); entry.grid(row=row, column=1, padx=5, pady=5, sticky="ew")
        entry.insert(0, getattr(self.config, dir_key, "")); self.path_entries[dir_key] = entry
        ctk.CTkButton(parent, text="Browse...", width=80, command=lambda e=entry: self.browse_folder(e)).grid(row=row, column=2, padx=5, pady=5)
        return row + 1

    def _test_api_key_task(self, provider: str):
        api_client = backend.APIClient(self.config)
        if provider == "omdb":
            api_key = self.omdb_api_key_entry.get()
            is_valid, message = api_client.test_omdb_api_key(api_key)
        elif provider == "tmdb":
            api_key = self.tmdb_api_key_entry.get()
            is_valid, message = api_client.test_tmdb_api_key(api_key)
        else: return
        
        if is_valid: messagebox.showinfo(f"{provider.upper()} Test Success", message)
        else: messagebox.showerror(f"{provider.upper()} Test Failed", message)

    def test_api_key_clicked(self, provider: str):
        threading.Thread(target=self._test_api_key_task, args=(provider,), daemon=True).start()
            
    def browse_folder(self, entry_widget):
        if folder_path := filedialog.askdirectory(initialdir=entry_widget.get() or str(Path.home())): 
            entry_widget.delete(0, ctk.END)
            entry_widget.insert(0, folder_path)
            
    def save_settings(self): 
        self.update_config_from_ui()
        self.config.save(CONFIG_FILE)
        logging.info("✅ Settings saved to config.json")
        if self.tray_icon: self.tray_icon.update_menu()

    def update_config_from_ui(self):
        for key, entry in self.path_entries.items(): setattr(self.config, key, entry.get())
        for key, var in self.enabled_vars.items(): setattr(self.config, key, var.get())
        
        self.config.API_PROVIDER = self.api_provider_var.get()
        if omdb_key := self.omdb_api_key_entry.get(): self.config.OMDB_API_KEY = omdb_key
        if tmdb_key := self.tmdb_api_key_entry.get(): self.config.TMDB_API_KEY = tmdb_key

        self.config.LANGUAGES_TO_SPLIT = [lang.strip().lower() for lang in self.split_languages_entry.get().split(',') if lang.strip()]
        self.config.SIDECAR_EXTENSIONS = {f".{ext.strip().lstrip('.')}" for ext in self.sidecar_entry.get().split(',') if ext.strip()}
        self.config.CUSTOM_STRINGS_TO_REMOVE = {s.strip().upper() for s in self.custom_strings_entry.get().split(',') if s.strip()}
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
        if not is_valid: 
            logging.error(f"Configuration error: {message}")
            return
        if self.config.SPLIT_MOVIES_DIR and self.config.LANGUAGES_TO_SPLIT:
             logging.info(f"🔵⚪🔴 Language Split is ENABLED for: {self.config.LANGUAGES_TO_SPLIT}")
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
        self.sorter_thread.start()
        self.monitor_active_task()
        
    def start_sort_now(self): self.start_task(lambda sorter: sorter.process_source_directory(), is_watcher=False)
    def toggle_watch_mode(self):
        if self.sorter_thread and self.sorter_thread.is_alive(): self.stop_running_task()
        else: self.start_task(lambda sorter: sorter.start_watch_mode(), is_watcher=True)
        
    def monitor_active_task(self):
        if self.is_quitting: return
        is_running = self.sorter_thread and self.sorter_thread.is_alive()
        
        if is_running:
            self._set_options_state("disabled")
            self.sort_now_button.configure(state="disabled")
            self.watch_button.configure(text="Stop Watchdog" if self.is_watching else "Running...", state="normal" if self.is_watching else "disabled")
            if self.sorter_instance and self.sorter_instance.is_processing: 
                self.stop_button.configure(state="normal", text="STOP", fg_color="#D32F2F", hover_color="#B71C1C")
                if not self.progress_frame.winfo_viewable(): self.progress_frame.grid()
            elif self.is_watching: 
                self.stop_button.configure(state="disabled", text="IDLE", fg_color="#FBC02D", text_color="black")
                if self.progress_frame.winfo_viewable(): self.progress_frame.grid_remove()
            self.after(500, self.monitor_active_task)
        else:
            self._set_options_state("normal")
            if self.is_watching: logging.info("✅ Watchdog stopped.")
            else: logging.info("✅ Task finished.")
            self.sort_now_button.configure(state="normal")
            self.watch_button.configure(text="Launch Watchdog", state="normal")
            self.stop_button.configure(state="disabled", text="", fg_color="gray25")
            self.progress_frame.grid_remove()
            self.sorter_instance = None; self.sorter_thread = None; self.is_watching = False
            if self.tray_icon: self.tray_icon.update_menu()
            self.toggle_cleanup_mode_ui()

    def create_tray_image(self):
        try: return Image.open(str(resource_path("icon.png")))
        except Exception:
            image = Image.new('RGB', (64, 64), "#1F6AA5"); dc = ImageDraw.Draw(image)
            dc.rectangle((32, 0, 64, 32), fill="#144870"); dc.rectangle((0, 32, 32, 64), fill="#144870")
            return image

    def quit_app(self):
        if self.is_quitting: return
        self.is_quitting = True
        logging.info("Shutting down...")
        if self.tray_icon: self.tray_icon.stop()
        if self.sorter_instance: self.sorter_instance.signal_stop()
        if self.sorter_thread and self.sorter_thread.is_alive(): self.sorter_thread.join(timeout=2)
        
        if self.tray_thread and self.tray_thread.is_alive() and threading.current_thread() != self.tray_thread:
            self.tray_thread.join(timeout=1.0)
        
        if threading.current_thread() != self.tray_thread:
            self.after(0, self._perform_safe_shutdown)
        else:
            if self.winfo_exists():
                self.after(0, self._perform_safe_shutdown)
            else:
                self.save_settings()
                os._exit(0)
        
    def _perform_safe_shutdown(self): 
        self.save_settings()
        self.destroy()

    def _show_and_focus_tab(self, tab_name: str):
        """Brings the window to the front and focuses on a specific tab."""
        self.deiconify()
        self.lift()
        self.attributes('-topmost', True)
        self.tab_view.set(tab_name)
        # on_tab_selected will be called automatically by the .set() method
        self.after(100, lambda: self.attributes('-topmost', False))

    def show_window(self): self._show_and_focus_tab("Actions")
    def show_settings(self): self._show_and_focus_tab("Settings")
    def show_review(self): self._show_and_focus_tab("Review")
    def show_about(self): self._show_and_focus_tab("About")

    def hide_to_tray(self): self.withdraw(); self.tray_icon.notify('App is running in the background', 'SortMeDown')
    def on_minimize(self, event):
        if self.state() == 'iconic': self.hide_to_tray()
    def set_interval(self, minutes: int):
        logging.info(f"Watch interval set to {minutes} minutes.")
        self.watch_interval_entry.delete(0, ctk.END); self.watch_interval_entry.insert(0, str(minutes)); self.save_settings() 
        
    def setup_tray_icon(self):
        image = self.create_tray_image()
        menu = (
            pystray.MenuItem('Show', self.show_window, default=True),
            pystray.MenuItem('Settings', self.show_settings),
            pystray.MenuItem('Review Mismatches', self.show_review),
            pystray.MenuItem('About', self.show_about),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Enable Watch', self.toggle_watch_mode, checked=lambda item: self.is_watching),
            pystray.MenuItem('Set Interval', pystray.Menu(
                pystray.MenuItem('5 minutes', lambda: self.set_interval(5), radio=True, checked=lambda i: self.config.WATCH_INTERVAL == 300),
                pystray.MenuItem('15 minutes', lambda: self.set_interval(15), radio=True, checked=lambda i: self.config.WATCH_INTERVAL == 900),
                pystray.MenuItem('30 minutes', lambda: self.set_interval(30), radio=True, checked=lambda i: self.config.WATCH_INTERVAL == 1800),
                pystray.MenuItem('60 minutes', lambda: self.set_interval(60), radio=True, checked=lambda i: self.config.WATCH_INTERVAL == 3600))),
            pystray.Menu.SEPARATOR, pystray.MenuItem('Quit', self.quit_app)
        )
        self.tray_icon = pystray.Icon("sortmedown", image, "SortMeDown Sorter", menu)
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()

if __name__ == "__main__":
    app = App()
    app.mainloop()
