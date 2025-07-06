# gui.py
"""
SortMeDown Media Sorter - GUI (gui.py) for bang bang 
================================

v6.2.5.0
- FEATURE: Implemented pagination in the Reorganize tab for large libraries.
- FIXED: A bug where the about tab could cause a crash.

v6.2
- FEATURE: new Reorganize tab 

v6.1.0.1
- Release
 
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
from typing import List
import math

import bangbang as backend

CONFIG_FILE = Path("config.json")

def get_version_info():
    """Parses the module's docstring to get version and history."""
    doc = __doc__ or ""
    lines = doc.strip().split('\n')
    version = "v?.?.?"; history_content = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('v'): version = stripped.split()[0]; break
    changelog_started = False
    for line in lines:
        if line.strip().startswith('v'): changelog_started = True
        if changelog_started: history_content.append(line)
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
        self.title(f"SortMeDown Media Sorter {self.version}"); self.geometry("900x900"); ctk.set_appearance_mode("Dark")
        self.after(200, self._set_window_icon)
        
        self.config = backend.Config.load(CONFIG_FILE)
        self.sorter_thread = None; self.sorter_instance = None; self.tray_icon = None; self.tray_thread = None; self.tab_view = None
        self.is_quitting = False; self.path_entries = {}; self.mismatch_buttons = {}; self.default_button_color = None; self.default_hover_color = None
        self.is_watching = False; self.log_is_visible = True; self.selected_mismatched_file = None
        
        # --- START: Variables for Reorganize Tab Pagination ---
        self.reorganize_all_files = []
        self.reorganize_selection_state = {}
        self.reorganize_current_page = 0
        self.reorganize_items_per_page = 200 # Manageable number of widgets
        # --- END: Reorganize Tab Pagination Variables ---

        self.api_provider_var = ctk.StringVar(value="TMDB" if self.config.API_PROVIDER == "tmdb" else "OMDb")
        self.enabled_vars = {
            'MOVIES_ENABLED': ctk.BooleanVar(value=self.config.MOVIES_ENABLED),
            'TV_SHOWS_ENABLED': ctk.BooleanVar(value=self.config.TV_SHOWS_ENABLED),
            'ANIME_MOVIES_ENABLED': ctk.BooleanVar(value=self.config.ANIME_MOVIES_ENABLED),
            'ANIME_SERIES_ENABLED': ctk.BooleanVar(value=self.config.ANIME_SERIES_ENABLED),
        }
        self.dry_run_var = ctk.BooleanVar(value=False)
        self.fallback_var = ctk.StringVar(value=self.config.FALLBACK_SHOW_DESTINATION)
        
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(0, weight=0); self.grid_rowconfigure(1, weight=1); self.grid_rowconfigure(2, weight=0)
        self.controls_frame = ctk.CTkFrame(self); self.controls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.create_controls()
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", font=("Courier New", 12)); self.log_textbox.grid(row=1, column=0, padx=10, pady=(0,5), sticky="nsew")
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent"); self.progress_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10)); self.progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_label = ctk.CTkLabel(self.progress_frame, text=""); self.progress_label.grid(row=0, column=0, sticky="w", padx=5)
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame); self.progress_bar.set(0); self.progress_bar.grid(row=1, column=0, sticky="ew", padx=5)
        self.version_label = ctk.CTkLabel(self.progress_frame, text=self.version, text_color="gray50"); self.version_label.grid(row=0, column=1, rowspan=2, padx=(10, 5), sticky="e")
        self.progress_frame.grid_remove()

        self.setup_logging(); self.protocol("WM_DELETE_WINDOW", self.quit_app); self.bind("<Unmap>", self.on_minimize); self.setup_tray_icon(); self.update_fallback_ui_state()
        self.after(500, self.check_api_keys_on_startup)

    def check_api_keys_on_startup(self):
        if not (self.config.OMDB_API_KEY and self.config.OMDB_API_KEY != "yourkey") and not (self.config.TMDB_API_KEY and self.config.TMDB_API_KEY != "yourkey"):
            logging.warning("⚠️ No API Key Found! Please add at least one key in the 'Settings' tab.")
    
    def _set_window_icon(self):
        try:
            if sys.platform == "win32": self.iconbitmap(str(resource_path("icon.ico")))
            else: self.iconphoto(True, tkinter.PhotoImage(file=str(resource_path("icon.png"))))
        except Exception as e: logging.warning(f"Could not set window icon: {e}")

    def setup_logging(self):
        log_handler = GuiLoggingHandler(self.log_textbox)
        log_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s", "%H:%M:%S"))
        logging.basicConfig(level=logging.INFO, handlers=[log_handler], force=True)
        
    def create_controls(self):
        self.tab_view = ctk.CTkTabview(self.controls_frame); self.tab_view.pack(expand=True, fill="both", padx=5, pady=5)
        self.create_actions_tab(self.tab_view.add("Actions")); self.create_settings_tab(self.tab_view.add("Settings"))
        self.create_reorganize_tab(self.tab_view.add("Reorganize")); self.create_mismatch_tab(self.tab_view.add("Review"))
        self.create_about_tab(self.tab_view.add("About")); self.tab_view.configure(command=self.on_tab_selected); self.tab_view.set("Actions")

    def on_tab_selected(self):
        tab_name = self.tab_view.get()
        if tab_name == "Review": self.scan_mismatched_files()
        if tab_name == "About": self.log_textbox.grid_remove(); self.grid_rowconfigure(0, weight=1); self.grid_rowconfigure(1, weight=0)
        else: self.grid_rowconfigure(0, weight=0); self.grid_rowconfigure(1, weight=1);
        if self.log_is_visible: self.log_textbox.grid()
        else: self.log_textbox.grid_remove()

    def create_actions_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        bf = ctk.CTkFrame(parent, fg_color="transparent"); bf.grid(row=0, column=0, sticky="ew"); bf.grid_columnconfigure((0, 2), weight=1); bf.grid_columnconfigure(1, weight=0)
        self.sort_now_button = ctk.CTkButton(bf, text="Single Shot Sort", command=self.start_sort_now); self.sort_now_button.grid(row=0, column=0, padx=(0, 5), pady=10, sticky="ew")
        self.default_button_color = self.sort_now_button.cget("fg_color"); self.default_hover_color = self.sort_now_button.cget("hover_color")
        self.stop_button = ctk.CTkButton(bf, text="", width=60, command=self.stop_running_task, fg_color="gray25", border_width=0, state="disabled"); self.stop_button.grid(row=0, column=1, padx=5, pady=10)
        self.watch_button = ctk.CTkButton(bf, text="Launch Watchdog", command=self.toggle_watch_mode); self.watch_button.grid(row=0, column=2, padx=(5, 0), pady=10, sticky="ew")
        of = ctk.CTkFrame(parent, fg_color="transparent"); of.grid(row=2, column=0, columnspan=3, sticky="ew"); of.grid_columnconfigure((0,1), weight=1)
        self.dry_run_checkbox = ctk.CTkCheckBox(of, text="Dry Run", variable=self.dry_run_var); self.dry_run_checkbox.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        wif = ctk.CTkFrame(of, fg_color="transparent"); wif.grid(row=0, column=1, padx=5, pady=5, sticky="e")
        ctk.CTkLabel(wif, text="Check every").pack(side="left", padx=(0,5)); self.watch_interval_entry = ctk.CTkEntry(wif, width=40); self.watch_interval_entry.pack(side="left"); self.watch_interval_entry.insert(0, str(self.config.WATCH_INTERVAL // 60)); ctk.CTkLabel(wif, text="minutes").pack(side="left", padx=(5,0))
        self.toggle_log_button = ctk.CTkButton(of, text="Hide Log", width=100, command=self.toggle_log_visibility); self.toggle_log_button.grid(row=1, column=1, sticky="e", padx=5, pady=5)
        ctk.CTkFrame(parent, height=2, fg_color="gray25").grid(row=3, column=0, pady=(10, 5), sticky="ew")
        tf = ctk.CTkFrame(parent, fg_color="transparent"); tf.grid(row=4, column=0, sticky="ew", pady=(0, 5)); tf.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.toggles_map = {}; am = {'Movies': 'MOVIES_ENABLED', 'TV Shows': 'TV_SHOWS_ENABLED', 'Anime Movies': 'ANIME_MOVIES_ENABLED', 'Anime': 'ANIME_SERIES_ENABLED'}
        for i, (label, key) in enumerate(am.items()): cb = ctk.CTkCheckBox(tf, text=label, variable=self.enabled_vars[key], command=self.on_media_type_toggled); cb.grid(row=0, column=i, padx=5, pady=5); self.toggles_map[key] = cb
        ff = ctk.CTkFrame(parent, fg_color="transparent"); ff.grid(row=5, column=0, pady=5, sticky="ew"); ctk.CTkLabel(ff, text="For mismatched shows, default to:").pack(side="left", padx=(5,10))
        self.ignore_radio = ctk.CTkRadioButton(ff, text="Do Nothing", variable=self.fallback_var, value="ignore"); self.ignore_radio.pack(side="left", padx=5)
        self.mismatch_radio = ctk.CTkRadioButton(ff, text="Mismatched Folder", variable=self.fallback_var, value="mismatched"); self.mismatch_radio.pack(side="left", padx=5)
        self.tv_radio = ctk.CTkRadioButton(ff, text="TV Shows Folder", variable=self.fallback_var, value="tv"); self.tv_radio.pack(side="left", padx=5)
        self.anime_radio = ctk.CTkRadioButton(ff, text="Anime Folder", variable=self.fallback_var, value="anime"); self.anime_radio.pack(side="left", padx=5)
        self.update_fallback_ui_state()

    # --- START: REWRITTEN Reorganize Tab with Pagination ---
    def create_reorganize_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        # --- Top Controls ---
        top_frame = ctk.CTkFrame(parent); top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew"); top_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(top_frame, text="Target Library:").grid(row=0, column=0, padx=(10, 5), pady=10)
        self.reorganize_path_entry = ctk.CTkEntry(top_frame, placeholder_text="Select a library folder to scan..."); self.reorganize_path_entry.grid(row=0, column=1, padx=5, pady=10, sticky="ew")
        ctk.CTkButton(top_frame, text="Browse...", width=80, command=lambda: self.browse_folder(self.reorganize_path_entry)).grid(row=0, column=2, padx=5, pady=10)
        ctk.CTkButton(top_frame, text="Scan for Files", width=100, command=self.scan_reorganize_folder).grid(row=0, column=3, padx=(5, 10), pady=10)

        # --- File List Frame ---
        self.reorganize_files_frame = ctk.CTkScrollableFrame(parent, label_text="Files Found in Target Library"); self.reorganize_files_frame.grid(row=2, column=0, padx=10, pady=(0,5), sticky="nsew")

        # --- Middle Controls (Pagination & Selection) ---
        check_frame = ctk.CTkFrame(parent, fg_color="transparent"); check_frame.grid(row=1, column=0, padx=10, pady=0, sticky="ew"); check_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(check_frame, text="Select Page", command=self.reorganize_select_page).pack(side="left")
        ctk.CTkButton(check_frame, text="Deselect Page", command=lambda: self.reorganize_select_page(select=False)).pack(side="left", padx=5)
        ctk.CTkButton(check_frame, text="Select All", command=self.reorganize_select_all).pack(side="left")
        self.reorganize_prev_button = ctk.CTkButton(check_frame, text="< Prev", width=60, command=self.reorganize_previous_page, state="disabled"); self.reorganize_prev_button.pack(side="left", padx=(20,5))
        self.reorganize_page_label = ctk.CTkLabel(check_frame, text="Page 0 of 0"); self.reorganize_page_label.pack(side="left")
        self.reorganize_next_button = ctk.CTkButton(check_frame, text="Next >", width=60, command=self.reorganize_next_page, state="disabled"); self.reorganize_next_button.pack(side="left", padx=5)
        self.reorganize_status_label = ctk.CTkLabel(check_frame, text="Selected: 0"); self.reorganize_status_label.pack(side="right")
        
        # --- Bottom Action Buttons ---
        bottom_frame = ctk.CTkFrame(parent); bottom_frame.grid(row=3, column=0, padx=10, pady=10, sticky="ew"); bottom_frame.grid_columnconfigure((0, 1), weight=1)
        self.reorganize_folders_button = ctk.CTkButton(bottom_frame, text="Organize Folder Structure for Selected", command=self.start_folder_reorganization); self.reorganize_folders_button.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="ew")
        self.rename_files_button = ctk.CTkButton(bottom_frame, text="Rename Selected Files", command=self.start_file_renaming); self.rename_files_button.grid(row=0, column=1, padx=(5, 0), pady=5, sticky="ew")
        self.reorganize_dry_run_var = ctk.BooleanVar(value=False); ctk.CTkCheckBox(bottom_frame, text="Dry Run", variable=self.reorganize_dry_run_var).grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="w")
    # --- END: REWRITTEN Reorganize Tab ---
        
    def create_mismatch_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1); parent.grid_rowconfigure(1, weight=1)
        cf = ctk.CTkFrame(parent, fg_color="transparent"); cf.grid(row=0, column=0, sticky="ew", padx=5, pady=5); ctk.CTkButton(cf, text="Rescan for Files", command=self.scan_mismatched_files).pack(side="left")
        mf = ctk.CTkFrame(parent, fg_color="transparent"); mf.grid(row=1, column=0, sticky="nsew", padx=5, pady=5); mf.grid_columnconfigure(0, weight=1); mf.grid_columnconfigure(1, weight=1); mf.grid_rowconfigure(0, weight=1)
        self.mismatched_files_frame = ctk.CTkScrollableFrame(mf, label_text="Files Found in Mismatched Folder"); self.mismatched_files_frame.grid(row=0, column=0, sticky="nsew", padx=(0,5))
        ap = ctk.CTkFrame(mf); ap.grid(row=0, column=1, sticky="nsew", padx=(5,0)); ap.grid_columnconfigure(0, weight=1)
        self.mismatch_selected_label = ctk.CTkLabel(ap, text="No file selected.", wraplength=350, justify="left"); self.mismatch_selected_label.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        ctk.CTkLabel(ap, text="Enter correct name: Title (Year)").grid(row=1, column=0, sticky="w", padx=10)
        self.mismatch_name_entry = ctk.CTkEntry(ap); self.mismatch_name_entry.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        abf = ctk.CTkFrame(ap, fg_color="transparent"); abf.grid(row=3, column=0, sticky="ew", pady=10); abf.grid_columnconfigure((0,1), weight=1)
        self.mismatch_reprocess_button = ctk.CTkButton(abf, text="Re-process (API)", command=self.reprocess_selected_file); self.mismatch_reprocess_button.grid(row=0, column=0, padx=(10,5), sticky="ew")
        self.mismatch_delete_button = ctk.CTkButton(abf, text="Delete File", fg_color="#D32F2F", hover_color="#B71C1C", command=self.delete_selected_file); self.mismatch_delete_button.grid(row=0, column=1, padx=(5,10), sticky="ew")
        ff = ctk.CTkFrame(ap); ff.grid(row=4, column=0, sticky="ew", padx=10, pady=(20, 0)); ff.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(ff, text="Force as (bypasses API):").grid(row=0, column=0, sticky="w", padx=5)
        fbf = ctk.CTkFrame(ff, fg_color="transparent"); fbf.grid(row=1, column=0, sticky="ew", pady=5); fbf.grid_columnconfigure((0,1), weight=1)
        self.force_movie_btn = ctk.CTkButton(fbf, text="Movie", command=lambda: self.force_reprocess_file(backend.MediaType.MOVIE)); self.force_tv_btn = ctk.CTkButton(fbf, text="TV Show", command=lambda: self.force_reprocess_file(backend.MediaType.TV_SERIES))
        self.force_anime_series_btn = ctk.CTkButton(fbf, text="Anime", command=lambda: self.force_reprocess_file(backend.MediaType.ANIME_SERIES)); self.force_anime_movie_btn = ctk.CTkButton(fbf, text="Anime Movie", command=lambda: self.force_reprocess_file(backend.MediaType.ANIME_MOVIE))
        self.force_split_lang_movie_btn = ctk.CTkButton(fbf, text="Split Lang Movie", command=lambda: self.force_reprocess_file(backend.MediaType.MOVIE, is_split_lang_override=True))
        self.force_movie_btn.grid(row=0, column=0, padx=2, pady=2, sticky="ew"); self.force_tv_btn.grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        self.force_anime_series_btn.grid(row=1, column=0, padx=2, pady=2, sticky="ew"); self.force_anime_movie_btn.grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        self.force_split_lang_movie_btn.grid(row=2, column=0, padx=2, pady=2, sticky="ew"); self._update_mismatch_panel_state()
        
    def create_settings_tab(self, parent):
        parent.grid_columnconfigure(1, weight=1); self.path_entries = {}; row = 0
        pm = {'SOURCE_DIR': 'Source Directory (for Actions tab)', 'MOVIES_DIR': 'Movies Directory', 'TV_SHOWS_DIR': 'TV Shows Directory', 'ANIME_MOVIES_DIR': 'Anime Movies Directory', 'ANIME_SERIES_DIR': 'Anime Series Directory', 'MISMATCHED_DIR': 'Mismatched Files Directory'}
        for key, label in pm.items(): row = self._create_path_entry_row(parent, row, key, label)
        ctk.CTkLabel(parent, text="Split Language Movies Dir").grid(row=row, column=0, padx=5, pady=5, sticky="w"); self.split_movies_dir_entry = ctk.CTkEntry(parent, width=400); self.split_movies_dir_entry.insert(0, getattr(self.config, "SPLIT_MOVIES_DIR", "")); self.path_entries["SPLIT_MOVIES_DIR"] = self.split_movies_dir_entry; ctk.CTkButton(parent, text="Browse...", width=80, command=lambda e=self.split_movies_dir_entry: self.browse_folder(e)).grid(row=row, column=2, padx=5, pady=5); self.split_movies_dir_entry.grid(row=row, column=1, padx=5, pady=5, sticky="ew"); row += 1
        ctk.CTkLabel(parent, text="Languages to Split").grid(row=row, column=0, padx=5, pady=5, sticky="w"); self.split_languages_entry = ctk.CTkEntry(parent, placeholder_text='e.g., fr, es, de, all'); self.split_languages_entry.grid(row=row, column=1, columnspan=2, padx=5, pady=5, sticky="ew");
        if self.config.LANGUAGES_TO_SPLIT: self.split_languages_entry.insert(0, ", ".join(self.config.LANGUAGES_TO_SPLIT)); row += 1
        ctk.CTkLabel(parent, text="Sidecar Extensions").grid(row=row, column=0, padx=5, pady=5, sticky="w"); self.sidecar_entry = ctk.CTkEntry(parent, placeholder_text=".srt, .nfo, .txt"); self.sidecar_entry.grid(row=row, column=1, columnspan=2, padx=5, pady=5, sticky="ew");
        if self.config.SIDECAR_EXTENSIONS: self.sidecar_entry.insert(0, ", ".join(self.config.SIDECAR_EXTENSIONS)); row += 1
        ctk.CTkLabel(parent, text="Custom Strings to Remove").grid(row=row, column=0, padx=5, pady=5, sticky="w"); self.custom_strings_entry = ctk.CTkEntry(parent, placeholder_text="FRENCH, VOSTFR"); self.custom_strings_entry.grid(row=row, column=1, columnspan=2, padx=5, pady=5, sticky="ew");
        if self.config.CUSTOM_STRINGS_TO_REMOVE: self.custom_strings_entry.insert(0, ", ".join(self.config.CUSTOM_STRINGS_TO_REMOVE)); row += 1
        ctk.CTkLabel(parent, text="Primary Provider").grid(row=row, column=0, padx=5, pady=5, sticky="w"); pf = ctk.CTkFrame(parent, fg_color="transparent"); pf.grid(row=row, column=1, columnspan=2, sticky="ew", padx=5, pady=5); ctk.CTkSegmentedButton(pf, values=["OMDb", "TMDB"], variable=self.api_provider_var).pack(side="left"); ctk.CTkLabel(pf, text="If both API keys are entered, the other will be used as a fallback.", text_color="gray50").pack(side="left", padx=(10,0)); row += 1
        ctk.CTkLabel(parent, text="OMDb API Key").grid(row=row, column=0, padx=5, pady=5, sticky="w"); oaf = ctk.CTkFrame(parent, fg_color="transparent"); oaf.grid(row=row, column=1, columnspan=2, sticky="ew"); oaf.grid_columnconfigure(0, weight=1); self.omdb_api_key_entry = ctk.CTkEntry(oaf, placeholder_text="Enter OMDb API key"); self.omdb_api_key_entry.grid(row=0, column=0, sticky="ew");
        if self.config.OMDB_API_KEY and self.config.OMDB_API_KEY != "yourkey": self.omdb_api_key_entry.insert(0, self.config.OMDB_API_KEY); self.omdb_api_key_entry.configure(show="*");
        self.omdb_api_key_entry.bind("<Key>", lambda e: self.omdb_api_key_entry.configure(show="*")); ctk.CTkButton(oaf, text="Test Key", width=80, command=lambda: self.test_api_key_clicked("omdb")).grid(row=0, column=1, padx=(10,0)); row += 1
        ctk.CTkLabel(parent, text="TMDB API Key").grid(row=row, column=0, padx=5, pady=5, sticky="w"); taf = ctk.CTkFrame(parent, fg_color="transparent"); taf.grid(row=row, column=1, columnspan=2, sticky="ew"); taf.grid_columnconfigure(0, weight=1); self.tmdb_api_key_entry = ctk.CTkEntry(taf, placeholder_text="Enter TMDB API key"); self.tmdb_api_key_entry.grid(row=0, column=0, sticky="ew");
        if self.config.TMDB_API_KEY and self.config.TMDB_API_KEY != "yourkey": self.tmdb_api_key_entry.insert(0, self.config.TMDB_API_KEY); self.tmdb_api_key_entry.configure(show="*");
        self.tmdb_api_key_entry.bind("<Key>", lambda e: self.tmdb_api_key_entry.configure(show="*")); ctk.CTkButton(taf, text="Test Key", width=80, command=lambda: self.test_api_key_clicked("tmdb")).grid(row=0, column=1, padx=(10,0)); row += 1
        ctk.CTkButton(parent, text="Save Settings", command=self.save_settings).grid(row=row, column=1, columnspan=2, padx=5, pady=10, sticky="e")

    def create_about_tab(self, parent):
        parent.grid_rowconfigure(0, weight=0); parent.grid_rowconfigure(1, weight=1); parent.grid_rowconfigure(2, weight=0); parent.grid_columnconfigure(0, weight=1)
        def open_url(url): webbrowser.open_new_tab(url)
        ascii_art = """    ██████  ▒█████   ██▀███  ▄▄▄█████▓    ███▄ ▄███▓▓█████    ▓█████▄  ▒█████   █     █░███▄    █ \n  ▒██    ▒ ▒██▒  ██▒▓██ ▒ ██▒▓  ██▒ ▓▒   ▓██▒▀█▀ ██▒▓█   ▀    ▒██▀ ██▌▒██▒  ██▒▓█░ █ ░█░██ ▀█   █ \n  ░ ▓██▄   ▒██░  ██▒▓██ ░▄█ ▒▒ ▓██░ ▒░   ▓██    ▓██░▒███      ░██   █▌▒██░  ██▒▒█░ █ ░█▓██  ▀█ ██▒\n    ▒   ██▒▒██   ██░▒██▀▀█▄  ░ ▓██▓ ░    ▒██    ▒██ ▒▓█  ▄    ░▓█▄   ▌▒██   ██░░█░ █ ░█▓██▒  ▐▌██▒\n  ▒██████▒▒░ ████▓▒░░██▓ ▒██▒  ▒██▒ ░    ▒██▒   ░██▒░▒████▒   ░▒████▓ ░ ████▓▒░░░██▒██▓▒██░   ▓██░\n  ▒ ▒▓▒ ▒ ░░ ▒░▒░▒░ ░ ▒▓ ░▒▓░  ▒ ░░      ░ ▒░   ░  ░░░ ▒░ ░    ▒▒▓  ▒ ░ ▒░▒░▒░ ░ ▓░▒ ▒ ░ ▒░   ▒ ▒ \n  ░ ░▒  ░ ░  ░ ▒ ▒░   ░▒ ░ ▒░    ░       ░  ░      ░ ░ ░  ░    ░ ▒  ▒   ░ ▒ ▒░   ▒ ░ ░ ░ ░░   ░ ▒░\n  ░  ░  ░  ░ ░ ░ ▒    ░░   ░   ░         ░      ░      ░       ░ ░  ░ ░ ░ ░ ▒    ░   ░    ░   ░ ░ \n        ░      ░ ░      ░                        ░      ░  ░      ░        ░ ░        ░        ░   \n                              a BangBang GUI                                                """
        ctk.CTkLabel(parent, text=ascii_art, font=ctk.CTkFont(family="Courier", size=8), justify="left").grid(row=0, column=0, padx=10, pady=(10,0), sticky="ew")
        ttb = ctk.CTkTextbox(parent, wrap="word", font=("Segoe UI", 14), corner_radius=6); ttb.grid(row=1, column=0, padx=10, pady=(5, 5), sticky="nsew")
        ttb.insert("end", "\n"); ttb.insert("end", "🗡️ Some tools aren't just built—they're forged. 🗡️\n\n"); ttb.insert("end", "Created with ❤️ by: Frederic LM\n\n"); ttb.insert("end", "If SortMeDown has saved you time, consider showing some support!\n\n")
        for i, (text, url) in enumerate([("🍺 Buy Me a beer", "https://coff.ee/drmcwormd")]): lt = f"link-{i}"; ttb.tag_config(lt, foreground="#6495ED", underline=True); ttb.tag_bind(lt, "<Button-1>", lambda e, u=url: open_url(u)); ttb.tag_bind(lt, "<Enter>", lambda e: ttb.configure(cursor="hand2")); ttb.tag_bind(lt, "<Leave>", lambda e: ttb.configure(cursor="")); ttb.insert("end", text, (lt, "center"))
        ttb.insert("end", "\n\nHappy sorting! 📁"); eut = "link-ee"; ttb.tag_config(eut, foreground="#6495ED", underline=True); ttb.tag_bind(eut, "<Button-1>", lambda e, u="https://youtu.be/HPCdBJMkN5A?si=UxQbUUR7x6T-EWSL": open_url(u)); ttb.tag_bind(eut, "<Enter>", lambda e: ttb.configure(cursor="hand2")); ttb.tag_bind(eut, "<Leave>", lambda e: ttb.configure(cursor="")); ttb.insert("end", "🎯", eut)
        ttb.tag_config("center", justify="center"); ttb.tag_add("center", "1.0", "end"); ttb.configure(state="disabled")
        hf = ctk.CTkFrame(parent); hf.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="nsew"); hf.grid_columnconfigure(0, weight=1); hf.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(hf, text="Version History", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=(5, 2), sticky="w")
        btb = ctk.CTkTextbox(hf, wrap="word", font=("Courier New", 12)); btb.grid(row=1, column=0, padx=10, pady=(2, 10), sticky="nsew"); btb.insert("1.0", self.version_history); btb.configure(state="disabled", height=200)

    def _set_options_state(self, state: str):
        self.dry_run_checkbox.configure(state=state); self.watch_interval_entry.configure(state=state)
        for cb in self.toggles_map.values(): cb.configure(state=state)
        for rb in [self.ignore_radio, self.mismatch_radio, self.tv_radio, self.anime_radio]: rb.configure(state=state)
        if state == "normal": self.update_fallback_ui_state()

    def _update_mismatch_panel_state(self):
        isfs = self.selected_mismatched_file is not None; s = "normal" if isfs else "disabled"
        self.mismatch_name_entry.configure(state=s); self.mismatch_reprocess_button.configure(state=s); self.mismatch_delete_button.configure(state=s)
        self.force_movie_btn.configure(state=s); self.force_tv_btn.configure(state=s); self.force_anime_series_btn.configure(state=s); self.force_anime_movie_btn.configure(state=s)
        sdp = self.path_entries.get('SPLIT_MOVIES_DIR', ctk.CTkEntry(self)).get(); ss = s if sdp else "disabled"; self.force_split_lang_movie_btn.configure(state=ss)
        if not isfs: self.mismatch_selected_label.configure(text="No file selected."); self.mismatch_name_entry.delete(0, ctk.END)
        else: self.mismatch_selected_label.configure(text=f"Selected: {self.selected_mismatched_file.name}")

    def scan_mismatched_files(self):
        for w in self.mismatched_files_frame.winfo_children(): w.destroy()
        self.mismatch_buttons = {}; self.selected_mismatched_file = None; self._update_mismatch_panel_state()
        md = self.config.get_path('MISMATCHED_DIR') or (self.config.get_path('SOURCE_DIR') / '_Mismatched' if self.config.get_path('SOURCE_DIR') else None)
        if not md or not md.exists(): ctk.CTkLabel(self.mismatched_files_frame, text="Mismatched directory not configured or found.").pack(); return
        mfs = [p for ext in self.config.SUPPORTED_EXTENSIONS for p in md.glob(f'**/*{ext}') if p.is_file()]
        if not mfs: ctk.CTkLabel(self.mismatched_files_frame, text="No media files found.").pack(); return
        smfs = sorted(mfs, key=lambda p: p.name)
        for fp in smfs: btn = ctk.CTkButton(self.mismatched_files_frame, text=fp.name, command=lambda f=fp: self.select_mismatched_file(f), fg_color="transparent", anchor="w"); btn.pack(fill="x", padx=2, pady=2); self.mismatch_buttons[fp] = btn
        if smfs: self.after(50, lambda: self.select_mismatched_file(smfs[0]))

    def select_mismatched_file(self, file_path: Path):
        self.selected_mismatched_file = file_path
        for p, b in self.mismatch_buttons.items(): b.configure(fg_color=self.default_button_color if p == file_path else "transparent")
        self.update_config_from_ui(); fs = self.selected_mismatched_file.stem; ct = backend.TitleCleaner.clean_for_search(fs, self.config.CUSTOM_STRINGS_TO_REMOVE); y = backend.TitleCleaner.extract_year(fs)
        sn = f"{ct} ({y})" if y else ct; self.mismatch_name_entry.delete(0, ctk.END); self.mismatch_name_entry.insert(0, sn); self._update_mismatch_panel_state()
    
    def reprocess_selected_file(self):
        if not self.selected_mismatched_file: return
        nn = self.mismatch_name_entry.get().strip();
        if not nn: messagebox.showwarning("Input Required", "Please enter a corrected name for the file."); return
        threading.Thread(target=lambda: (backend.MediaSorter(self.config, self.dry_run_var.get()).sort_item(self.selected_mismatched_file, override_name=nn), self.after(0, self.scan_mismatched_files)), daemon=True).start()

    def force_reprocess_file(self, media_type: backend.MediaType, is_split_lang_override: bool = False):
        if not self.selected_mismatched_file: return
        fn = self.mismatch_name_entry.get().strip();
        if not fn: messagebox.showwarning("Input Required", "Please enter a name for the folder."); return
        threading.Thread(target=lambda: (backend.MediaSorter(self.config, self.dry_run_var.get()).force_move_item(self.selected_mismatched_file, fn, media_type, is_split_lang_override), self.after(0, self.scan_mismatched_files)), daemon=True).start()

    def delete_selected_file(self):
        if not self.selected_mismatched_file: return
        if not messagebox.askyesno("Confirm Deletion", f"Are you sure you want to permanently delete '{self.selected_mismatched_file.name}' and its sidecar files?"): return
        threading.Thread(target=lambda: (backend.FileManager(self.config, self.dry_run_var.get()).delete_file_group(self.selected_mismatched_file), self.after(0, self.scan_mismatched_files)), daemon=True).start()

    def toggle_log_visibility(self):
        self.log_is_visible = not self.log_is_visible
        if self.log_is_visible:
            if self.tab_view.get() != "About": self.log_textbox.grid()
            self.toggle_log_button.configure(text="Hide Log")
        else: self.log_textbox.grid_remove(); self.toggle_log_button.configure(text="Show Log")

    def on_media_type_toggled(self): self.update_fallback_ui_state()
    def update_fallback_ui_state(self):
        tv_on, an_on = self.enabled_vars['TV_SHOWS_ENABLED'].get(), self.enabled_vars['ANIME_SERIES_ENABLED'].get()
        self.tv_radio.configure(state="normal" if tv_on else "disabled"); self.anime_radio.configure(state="normal" if an_on else "disabled")
        if not tv_on and self.fallback_var.get() == "tv": self.fallback_var.set("mismatched")
        if not an_on and self.fallback_var.get() == "anime": self.fallback_var.set("mismatched")
        
    def stop_running_task(self):
        if self.sorter_instance: logging.warning("🛑 User initiated stop..."); self.sorter_instance.signal_stop()

    def _create_path_entry_row(self, parent, row, key, label):
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, padx=5, pady=5, sticky="w"); e = ctk.CTkEntry(parent, width=400); e.grid(row=row, column=1, padx=5, pady=5, sticky="ew")
        e.insert(0, getattr(self.config, key, "")); self.path_entries[key] = e; ctk.CTkButton(parent, text="Browse...", width=80, command=lambda e=e: self.browse_folder(e)).grid(row=row, column=2, padx=5, pady=5)
        return row + 1

    def _test_api_key_task(self, p: str):
        key = self.omdb_api_key_entry.get() if p == "omdb" else self.tmdb_api_key_entry.get(); tf = getattr(backend.APIClient(self.config), f"test_{p}_api_key"); v, m = tf(key); messagebox.showinfo(f"{p.upper()} Test", m)

    def test_api_key_clicked(self, p: str): threading.Thread(target=self._test_api_key_task, args=(p,), daemon=True).start()
            
    def browse_folder(self, e):
        if fp := filedialog.askdirectory(initialdir=e.get() or str(Path.home())): e.delete(0, ctk.END); e.insert(0, fp)
            
    def save_settings(self):
        self.update_config_from_ui(); self.config.save(CONFIG_FILE); logging.info("✅ Settings saved to config.json")
        if self.tray_icon: self.tray_icon.update_menu()

    def update_config_from_ui(self):
        for k, e in self.path_entries.items(): setattr(self.config, k, e.get())
        for k, v in self.enabled_vars.items(): setattr(self.config, k, v.get())
        self.config.API_PROVIDER = self.api_provider_var.get().lower()
        if key := self.omdb_api_key_entry.get(): self.config.OMDB_API_KEY = key
        if key := self.tmdb_api_key_entry.get(): self.config.TMDB_API_KEY = key
        self.config.LANGUAGES_TO_SPLIT = [l.strip().lower() for l in self.split_languages_entry.get().split(',') if l.strip()]
        self.config.SIDECAR_EXTENSIONS = {f".{e.strip().lstrip('.')}" for e in self.sidecar_entry.get().split(',') if e.strip()}
        self.config.CUSTOM_STRINGS_TO_REMOVE = {s.strip().upper() for s in self.custom_strings_entry.get().split(',') if s.strip()}
        self.config.FALLBACK_SHOW_DESTINATION = self.fallback_var.get()
        try: self.config.WATCH_INTERVAL = int(self.watch_interval_entry.get()) * 60
        except (ValueError, TypeError): self.config.WATCH_INTERVAL = 15 * 60
    
    def _update_progress(self, cs: int, ts: int): self.after(0, self._update_progress_ui, cs, ts)
    def _update_progress_ui(self, cs: int, ts: int):
        if ts > 0: self.progress_bar.set(cs / ts); self.progress_label.configure(text=f"Processing: {cs} / {ts}")
        else: self.progress_bar.set(0); self.progress_label.configure(text="No files to process.")
            
    def start_task(self, task_function, is_watcher=False):
        if self.is_quitting or (self.sorter_thread and self.sorter_thread.is_alive()): return
        self.update_config_from_ui(); self.is_watching = is_watcher
        if not self.config.get_path('SOURCE_DIR'): messagebox.showerror("Config Error", "Source Directory is not set."); return
        if self.config.SPLIT_MOVIES_DIR and self.config.LANGUAGES_TO_SPLIT: logging.info(f"🔵⚪🔴 Language Split is ON for: {self.config.LANGUAGES_TO_SPLIT}")
        if self.dry_run_var.get(): logging.info("🧪 Dry Run is ENABLED for this task.")
        self.progress_frame.grid(); self.progress_bar.set(0); self.progress_label.configure(text="Initializing...")
        self.sorter_instance = backend.MediaSorter(self.config, self.dry_run_var.get(), self._update_progress)
        self.sorter_thread = threading.Thread(target=task_function, args=(self.sorter_instance,), daemon=True); self.sorter_thread.start()
        self.monitor_active_task()
        
    def start_sort_now(self): self.start_task(lambda s: s.process_source_directory())
    def toggle_watch_mode(self):
        if self.sorter_thread and self.sorter_thread.is_alive(): self.stop_running_task()
        else: self.start_task(lambda s: s.start_watch_mode(), True)

    def _start_reorganize_task(self, task_function, action_name: str):
        if self.sorter_thread and self.sorter_thread.is_alive(): logging.warning("A task is already running."); return
        target_path = Path(self.reorganize_path_entry.get().strip())
        selected_files = self._get_selected_reorganize_files()
        if not selected_files: messagebox.showwarning("No Files Selected", f"Please select files to {action_name}."); return
        self.update_config_from_ui(); self.progress_frame.grid(); self.progress_bar.set(0); self.progress_label.configure(text="Initializing...")
        dry_run = self.reorganize_dry_run_var.get()
        if dry_run: logging.info(f"🧪 DRY RUN MODE ENABLED for {action_name} task.")
        self.sorter_instance = backend.MediaSorter(self.config, dry_run, self._update_progress)
        self.sorter_thread = threading.Thread(target=task_function, args=(self.sorter_instance, target_path, selected_files), daemon=True); self.sorter_thread.start()
        self.monitor_active_task()

    def start_folder_reorganization(self): self._start_reorganize_task(lambda s, p, f: s.reorganize_folder_structure(p, file_list=f), "reorganize")
    def start_file_renaming(self): self._start_reorganize_task(lambda s, p, f: s.rename_files_in_library(p, file_list=f), "rename")

    def scan_reorganize_folder(self):
        target_path_str = self.reorganize_path_entry.get().strip()
        if not target_path_str: messagebox.showerror("Error", "Please select a target library folder to scan."); return
        target_path = Path(target_path_str)
        if not target_path.is_dir(): messagebox.showerror("Error", f"Path is not a valid folder:\n{target_path}"); return
        for widget in self.reorganize_files_frame.winfo_children(): widget.destroy()
        self.reorganize_all_files = []; self.reorganize_selection_state = {}; self.reorganize_current_page = 0
        self.reorganize_prev_button.configure(state="disabled"); self.reorganize_next_button.configure(state="disabled")
        logging.info(f"Scanning '{target_path}' for media files...")
        self.reorganize_page_label.configure(text="Scanning...")
        def _scan():
            files = sorted([p for ext in self.config.SUPPORTED_EXTENSIONS for p in target_path.glob(f'**/*{ext}') if p.is_file()], key=lambda p: str(p))
            self.after(0, self.finish_reorganize_scan, files, target_path)
        threading.Thread(target=_scan, daemon=True).start()

    def finish_reorganize_scan(self, media_files: List[Path], base_path: Path):
        self.reorganize_all_files = media_files
        self.reorganize_selection_state = {path: False for path in media_files}
        if not media_files:
            logging.warning("Scan complete. No media files found.")
            self.reorganize_display_page()
            return
        logging.info(f"Scan complete. Found {len(media_files)} media files.")
        self.reorganize_display_page()

    def reorganize_display_page(self):
        for widget in self.reorganize_files_frame.winfo_children(): widget.destroy()
        if not self.reorganize_all_files: ctk.CTkLabel(self.reorganize_files_frame, text="No media files found.").pack(); self.reorganize_page_label.configure(text="Page 0 of 0"); return
        
        start_index = self.reorganize_current_page * self.reorganize_items_per_page
        end_index = start_index + self.reorganize_items_per_page
        page_files = self.reorganize_all_files[start_index:end_index]
        base_path = Path(self.reorganize_path_entry.get())

        for file_path in page_files:
            var = ctk.BooleanVar(value=self.reorganize_selection_state.get(file_path, False))
            cb = ctk.CTkCheckBox(self.reorganize_files_frame, text=str(file_path.relative_to(base_path)), variable=var,
                                 command=lambda path=file_path, v=var: self.reorganize_toggle_selection(path, v))
            cb.pack(anchor="w", padx=5)
        self.update_reorganize_ui()

    def reorganize_toggle_selection(self, path: Path, var: ctk.BooleanVar):
        self.reorganize_selection_state[path] = var.get()
        self.update_reorganize_ui()

    def reorganize_select_page(self, select=True):
        start_index = self.reorganize_current_page * self.reorganize_items_per_page
        end_index = start_index + self.reorganize_items_per_page
        for i in range(start_index, min(end_index, len(self.reorganize_all_files))):
            self.reorganize_selection_state[self.reorganize_all_files[i]] = select
        self.reorganize_display_page()

    def reorganize_select_all(self):
        for path in self.reorganize_all_files: self.reorganize_selection_state[path] = True
        self.reorganize_display_page()

    def reorganize_previous_page(self):
        if self.reorganize_current_page > 0: self.reorganize_current_page -= 1; self.reorganize_display_page()
    def reorganize_next_page(self):
        if (self.reorganize_current_page + 1) * self.reorganize_items_per_page < len(self.reorganize_all_files):
            self.reorganize_current_page += 1; self.reorganize_display_page()

    def update_reorganize_ui(self):
        total_files = len(self.reorganize_all_files)
        total_pages = math.ceil(total_files / self.reorganize_items_per_page) if total_files > 0 else 0
        self.reorganize_page_label.configure(text=f"Page {self.reorganize_current_page + 1} of {total_pages}")
        self.reorganize_prev_button.configure(state="normal" if self.reorganize_current_page > 0 else "disabled")
        self.reorganize_next_button.configure(state="normal" if (self.reorganize_current_page + 1) < total_pages else "disabled")
        selected_count = sum(1 for v in self.reorganize_selection_state.values() if v)
        self.reorganize_status_label.configure(text=f"Selected: {selected_count}")
        
    def _get_selected_reorganize_files(self) -> List[Path]: return [p for p, v in self.reorganize_selection_state.items() if v]
        
    def monitor_active_task(self):
        is_running = self.sorter_thread and self.sorter_thread.is_alive()
        if is_running:
            self._set_options_state("disabled"); self.sort_now_button.configure(state="disabled")
            self.reorganize_folders_button.configure(state="disabled"); self.rename_files_button.configure(state="disabled")
            self.watch_button.configure(text="Stop Watchdog" if self.is_watching else "Running...", state="normal" if self.is_watching else "disabled")
            if self.sorter_instance and self.sorter_instance.is_processing: self.stop_button.configure(state="normal", text="STOP", fg_color="#D32F2F", hover_color="#B71C1C");
            elif self.is_watching: self.stop_button.configure(state="disabled", text="IDLE", fg_color="#FBC02D", text_color="black");
            if not self.progress_frame.winfo_viewable() and self.sorter_instance.is_processing : self.progress_frame.grid()
            self.after(500, self.monitor_active_task)
        else:
            self._set_options_state("normal"); self.reorganize_folders_button.configure(state="normal"); self.rename_files_button.configure(state="normal")
            if self.is_watching: logging.info("✅ Watchdog stopped.")
            else: logging.info("✅ Task finished.")
            self.sort_now_button.configure(state="normal"); self.watch_button.configure(text="Launch Watchdog", state="normal")
            self.stop_button.configure(state="disabled", text="", fg_color="gray25")
            self.progress_frame.grid_remove(); self.sorter_instance = None; self.sorter_thread = None; self.is_watching = False
            if self.tray_icon: self.tray_icon.update_menu()

    def create_tray_image(self):
        try: return Image.open(str(resource_path("icon.png")))
        except: img = Image.new('RGB', (64, 64), "#1F6AA5"); dc = ImageDraw.Draw(img); dc.rectangle(((32, 0), (64, 32)), fill="#144870"); dc.rectangle(((0, 32), (32, 64)), fill="#144870"); return img

    def quit_app(self):
        if self.is_quitting: return
        self.is_quitting = True; logging.info("Shutting down...")
        if self.tray_icon: self.tray_icon.stop()
        if self.sorter_instance: self.sorter_instance.signal_stop()
        if self.sorter_thread and self.sorter_thread.is_alive(): self.sorter_thread.join(2)
        if self.tray_thread and self.tray_thread.is_alive() and threading.current_thread() != self.tray_thread: self.tray_thread.join(1.0)
        self.after(0, self._perform_safe_shutdown)
        
    def _perform_safe_shutdown(self): self.save_settings(); self.destroy()
    def _show_and_focus_tab(self, tab_name: str): self.deiconify(); self.lift(); self.attributes('-topmost', True); self.tab_view.set(tab_name); self.after(100, lambda: self.attributes('-topmost', False))
    def show_window(self): self._show_and_focus_tab("Actions")
    def show_settings(self): self._show_and_focus_tab("Settings")
    def show_review(self): self._show_and_focus_tab("Review")
    def show_about(self): self._show_and_focus_tab("About")
    def hide_to_tray(self): self.withdraw(); self.tray_icon.notify('App is running in the background', 'SortMeDown')
    def on_minimize(self, event):
        if self.state() == 'iconic': self.hide_to_tray()
    def set_interval(self, minutes: int): self.watch_interval_entry.delete(0, ctk.END); self.watch_interval_entry.insert(0, str(minutes)); self.save_settings() 
        
    def setup_tray_icon(self):
        image = self.create_tray_image()
        menu = (pystray.MenuItem('Show', self.show_window, default=True), pystray.MenuItem('Settings', self.show_settings), pystray.MenuItem('Review Mismatches', self.show_review),
                pystray.MenuItem('About', self.show_about), pystray.Menu.SEPARATOR,
                pystray.MenuItem('Enable Watch', self.toggle_watch_mode, checked=lambda item: self.is_watching),
                pystray.MenuItem('Set Interval', pystray.Menu(pystray.MenuItem('5m', lambda: self.set_interval(5), radio=True, checked=lambda i: self.config.WATCH_INTERVAL == 300),
                                                              pystray.MenuItem('15m', lambda: self.set_interval(15), radio=True, checked=lambda i: self.config.WATCH_INTERVAL == 900),
                                                              pystray.MenuItem('30m', lambda: self.set_interval(30), radio=True, checked=lambda i: self.config.WATCH_INTERVAL == 1800),
                                                              pystray.MenuItem('60m', lambda: self.set_interval(60), radio=True, checked=lambda i: self.config.WATCH_INTERVAL == 3600))),
                pystray.Menu.SEPARATOR, pystray.MenuItem('Quit', self.quit_app))
        self.tray_icon = pystray.Icon("sortmedown", image, "SortMeDown Sorter", menu)
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True); self.tray_thread.start()

if __name__ == "__main__":
    app = App()
    app.mainloop()
