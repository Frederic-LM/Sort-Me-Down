# gui.py
"""
SortMeDown Media Sorter - GUI (gui.py) for bang bang 
================================

This file contains the Graphical User Interface for the SortMeDown media sorter.
It is built using the CustomTkinter library and provides a user-friendly way
to interact with the sorting logic defined in `bangbang.py`.

5.8.2
Lock Action setings while task is run to reflect the way the backend works
v5.8.1
Bug fix on close
v5.8
New settings for API Provider
v5.6
New review tab
v5.4
Include progress bar and show/hide logs, reduce default windows side 


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
        self.title("SortMeDown Media Sorter"); self.geometry("900x850"); ctk.set_appearance_mode("Dark")
        self.after(200, self._set_window_icon) # Delay icon setting
        
        self.config = backend.Config.load(CONFIG_FILE)
        self.sorter_thread = None; self.sorter_instance = None; self.tray_icon = None; self.tray_thread = None; self.tab_view = None
        self.is_quitting = False; self.path_entries = {}; self.default_button_color = None; self.default_hover_color = None
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
        self.fr_sauce_var = ctk.BooleanVar(value=self.config.FRENCH_MODE_ENABLED)
        self.dry_run_var = ctk.BooleanVar(value=False)
        self.cleanup_var = ctk.BooleanVar(value=self.config.CLEANUP_MODE_ENABLED)
        self.fallback_var = ctk.StringVar(value=self.config.FALLBACK_SHOW_DESTINATION)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)

        self.controls_frame = ctk.CTkFrame(self); self.controls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="new")
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
        self.progress_frame.grid_remove()

        self.setup_logging()
        self.protocol("WM_DELETE_WINDOW", self.quit_app)
        self.bind("<Unmap>", self.on_minimize)
        self.setup_tray_icon()
        self.update_fallback_ui_state()
        
    def _set_window_icon(self):
        """Sets the window icon after a short delay to ensure the window exists."""
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

        self.tab_view.set("Actions")

    def create_actions_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        button_bar_frame = ctk.CTkFrame(parent, fg_color="transparent"); button_bar_frame.grid(row=0, column=0, sticky="ew")
        button_bar_frame.grid_columnconfigure((0, 2), weight=1); button_bar_frame.grid_columnconfigure(1, weight=0)
        self.sort_now_button = ctk.CTkButton(button_bar_frame, text="Sort Now", command=self.start_sort_now); self.sort_now_button.grid(row=0, column=0, padx=(0, 5), pady=10, sticky="ew")
        self.default_button_color = self.sort_now_button.cget("fg_color"); self.default_hover_color = self.sort_now_button.cget("hover_color")
        self.stop_button = ctk.CTkButton(button_bar_frame, text="", width=60, command=self.stop_running_task, fg_color="gray25", border_width=0, state="disabled"); self.stop_button.grid(row=0, column=1, padx=5, pady=10)
        self.watch_button = ctk.CTkButton(button_bar_frame, text="Start Watching", command=self.toggle_watch_mode); self.watch_button.grid(row=0, column=2, padx=(5, 0), pady=10, sticky="ew")
        
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
        self.toggles_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        
        # --- Store references to these checkboxes to disable them later ---
        self.toggles_map = {}
        action_toggles_map = {'Movies': 'MOVIES_ENABLED', 'TV Shows': 'TV_SHOWS_ENABLED', 'Anime Movies': 'ANIME_MOVIES_ENABLED', 'Anime Series': 'ANIME_SERIES_ENABLED'}
        for i, (label, enable_key) in enumerate(action_toggles_map.items()):
            cb = ctk.CTkCheckBox(self.toggles_frame, text=label, variable=self.enabled_vars[enable_key], command=self.on_media_type_toggled)
            cb.grid(row=0, column=i, padx=5, pady=5)
            self.toggles_map[enable_key] = cb
            
        self.french_mode_checkbox = ctk.CTkCheckBox(self.toggles_frame, text="French Mode", variable=self.fr_sauce_var, command=self._on_french_mode_toggled)
        self.french_mode_checkbox.grid(row=0, column=len(action_toggles_map), padx=5, pady=5)
        
        self.fallback_frame = ctk.CTkFrame(parent, fg_color="transparent"); self.fallback_frame.grid(row=5, column=0, pady=5, sticky="ew")
        ctk.CTkLabel(self.fallback_frame, text="For mismatched shows, default to:").pack(side="left", padx=(5,10))
        self.ignore_radio = ctk.CTkRadioButton(self.fallback_frame, text="Do Nothing", variable=self.fallback_var, value="ignore"); self.ignore_radio.pack(side="left", padx=5)
        self.mismatch_radio = ctk.CTkRadioButton(self.fallback_frame, text="Mismatched Folder", variable=self.fallback_var, value="mismatched"); self.mismatch_radio.pack(side="left", padx=5)
        self.tv_radio = ctk.CTkRadioButton(self.fallback_frame, text="TV Shows Folder", variable=self.fallback_var, value="tv"); self.tv_radio.pack(side="left", padx=5)
        self.anime_radio = ctk.CTkRadioButton(self.fallback_frame, text="Anime Series Folder", variable=self.fallback_var, value="anime"); self.anime_radio.pack(side="left", padx=5)
        self.toggle_cleanup_mode_ui()

    # ... (Other create_* methods are unchanged) ...
    def create_mismatch_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        controls_frame = ctk.CTkFrame(parent, fg_color="transparent")
        controls_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        ctk.CTkButton(controls_frame, text="Scan for Files to Review", command=self.scan_mismatched_files).pack(side="left")

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
        
        ctk.CTkLabel(action_panel, text="Enter Correct Name (Title and Year):").grid(row=1, column=0, sticky="w", padx=10)
        self.mismatch_name_entry = ctk.CTkEntry(action_panel, placeholder_text="e.g., Blade Runner 2049")
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
        self.force_anime_series_btn = ctk.CTkButton(force_buttons_frame, text="Anime Series", command=lambda: self.force_reprocess_file(backend.MediaType.ANIME_SERIES))
        self.force_anime_movie_btn = ctk.CTkButton(force_buttons_frame, text="Anime Movie", command=lambda: self.force_reprocess_file(backend.MediaType.ANIME_MOVIE))
        self.force_french_movie_btn = ctk.CTkButton(force_buttons_frame, text="French Movie", command=lambda: self.force_reprocess_file(backend.MediaType.MOVIE, is_french=True))
        
        self.force_movie_btn.grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        self.force_tv_btn.grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        self.force_anime_series_btn.grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        self.force_anime_movie_btn.grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        self.force_french_movie_btn.grid(row=2, column=0, padx=2, pady=2, sticky="ew")

        self._update_mismatch_panel_state()
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
    
    # --- NEW METHOD to disable/enable options ---
    def _set_options_state(self, state: str):
        """Sets the state of all runtime options widgets. 'normal' or 'disabled'."""
        self.dry_run_checkbox.configure(state=state)
        self.cleanup_checkbox.configure(state=state)
        self.french_mode_checkbox.configure(state=state)
        self.watch_interval_entry.configure(state=state)
        for checkbox in self.toggles_map.values():
            checkbox.configure(state=state)
        for radio_button in [self.ignore_radio, self.mismatch_radio, self.tv_radio, self.anime_radio]:
            radio_button.configure(state=state)
        # Re-apply logic for TV/Anime radios if enabling
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
        french_state = state if self.config.FRENCH_MODE_ENABLED else "disabled"
        self.force_french_movie_btn.configure(state=french_state)

        if not is_file_selected:
            self.mismatch_selected_label.configure(text="No file selected.")
            self.mismatch_name_entry.delete(0, ctk.END)
        else:
            self.mismatch_selected_label.configure(text=f"Selected: {self.selected_mismatched_file.name}")

    def scan_mismatched_files(self):
        for widget in self.mismatched_files_frame.winfo_children():
            widget.destroy()
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

        for file_path in sorted(media_files, key=lambda p: p.name):
            btn = ctk.CTkButton(self.mismatched_files_frame, text=file_path.name,
                                command=lambda f=file_path: self.select_mismatched_file(f),
                                fg_color="transparent", anchor="w", text_align="left")
            btn.pack(fill="x", padx=2, pady=2)

    def select_mismatched_file(self, file_path: Path):
        self.selected_mismatched_file = file_path
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

    def force_reprocess_file(self, media_type: backend.MediaType, is_french: bool = False):
        if not self.selected_mismatched_file: return
        folder_name = self.mismatch_name_entry.get().strip()
        if not folder_name:
            messagebox.showwarning("Input Required", "Please enter a name for the folder (e.g., 'My Movie (2024)').")
            return

        def _task():
            temp_sorter = backend.MediaSorter(self.config, dry_run=self.dry_run_var.get())
            temp_sorter.force_move_item(self.selected_mismatched_file, folder_name, media_type, is_french_override=is_french)
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
            self.grid_rowconfigure(1, weight=0)
            self.toggle_log_button.configure(text="Show Log")
        else:
            self.log_textbox.grid()
            self.grid_rowconfigure(1, weight=1)
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
        self.toggle_french_dir_visibility()
        self.check_and_prompt_for_path('FRENCH_MOVIES_DIR', self.fr_sauce_var)
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
            self.sort_now_button.configure(text="Sort Now", fg_color=self.default_button_color, hover_color=self.default_hover_color)
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

    def toggle_french_dir_visibility(self):
        row_index_for_french_dir = 7 
        if self.fr_sauce_var.get(): 
            self.french_dir_entry.grid(row=row_index_for_french_dir, column=1, padx=5, pady=5, sticky="ew")
            self.french_dir_browse.grid(row=row_index_for_french_dir, column=2, padx=5, pady=5)
        else: 
            self.french_dir_entry.grid_remove()
            self.french_dir_browse.grid_remove()
            
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
        if not is_valid: 
            logging.error(f"Configuration error: {message}")
            return
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
            self._set_options_state("disabled") # Disable options while running
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
            self._set_options_state("normal") # Re-enable options when finished
            if self.is_watching: logging.info("✅ Watcher stopped.")
            else: logging.info("✅ Task finished.")
            self.sort_now_button.configure(state="normal"); self.watch_button.configure(text="Start Watching", state="normal")
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
        
        # Only join the tray thread if the current thread IS NOT the tray thread.
        if self.tray_thread and self.tray_thread.is_alive() and threading.current_thread() != self.tray_thread:
            self.tray_thread.join(timeout=1.0)
        
        if threading.current_thread() != self.tray_thread:
            self.after(0, self._perform_safe_shutdown)
        else:
            # When quitting from the tray, schedule the final actions on the main thread if it's still alive
            if self.winfo_exists():
                self.after(0, self._perform_safe_shutdown)
            else: # Fallback if GUI is gone
                self.save_settings()
                os._exit(0)
        
    def _perform_safe_shutdown(self): 
        self.save_settings()
        self.destroy()

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
        self.tray_icon = pystray.Icon("sortmedown", image, "SortMeDown Sorter", menu)
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()

if __name__ == "__main__":
    app = App()
    app.mainloop()
