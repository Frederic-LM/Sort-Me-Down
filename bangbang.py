# bangbang.py
"""
BangBang - Core Engine
===============================

This file contains the core, reusable logic for the SortMeDown media sorter.
It is designed to be a self-contained "engine" that can be controlled by any
frontend, such as a command-line interface (cli.py) or a graphical user 
interface (gui.py).

This engine is UI-agnostic. It does not contain any `print` statements or
argument parsing. It communicates its state and progress via `logging` and
its public methods.

Version 5.1
rafinement with auto creation of missmatched folder and ignore func

Version 5.0
Vastly improved inteligent sorting of missmatched item by the API
will decide it it's a movie or a show, move to a mismatched folder or to a default dir tv or anime 
"""

from pathlib import Path
import re
import shutil
import requests
import logging
import threading
from time import sleep
from typing import Optional, Dict, Any, Set, List
import json
from dataclasses import dataclass
from enum import Enum
import os
import sys
from datetime import datetime

# --- Public Classes & Enums ---

class MediaType(Enum):
    MOVIE = "movie"; TV_SERIES = "series"; ANIME_MOVIE = "anime_movie"; ANIME_SERIES = "anime_series"; UNKNOWN = "unknown"

@dataclass
class MediaInfo:
    title: str; year: Optional[str]; media_type: MediaType; language: Optional[str]; genre: Optional[str]; season: Optional[int] = None
    def get_folder_name(self) -> str:
        if not self.title: return "Unknown"
        folder_title = re.sub(r'[<>:"/\\|?*]', '', self.title).strip()
        if self.year: return f"{folder_title} ({self.year})"
        return folder_title

class Config:
    def __init__(self):
        self.SOURCE_DIR = ""
        self.MOVIES_DIR = ""
        self.FRENCH_MOVIES_DIR = ""
        self.TV_SHOWS_DIR = ""
        self.ANIME_MOVIES_DIR = ""
        self.ANIME_SERIES_DIR = ""
        self.MISMATCHED_DIR = ""
        self.SUPPORTED_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp', '.ogv', '.ts', '.m2ts', '.mts'}
        self.SIDECAR_EXTENSIONS = {'.srt', '.sub', '.nfo', '.txt', '.jpg', '.png'}
        self.CUSTOM_STRINGS_TO_REMOVE = {'FRENCH', 'TRUEFRENCH', 'VOSTFR', 'MULTI', 'SUBFRENCH'}
        self.OMDB_API_KEY = "yourkey"
        self.OMDB_URL = "http://www.omdbapi.com/"
        self.ANILIST_URL = "https://graphql.anilist.co"
        self.REQUEST_DELAY = 1.0
        self.WATCH_INTERVAL = 15 * 60
        self.FALLBACK_SHOW_DESTINATION = "mismatched" # "mismatched", "tv", "anime", "ignore"
        self.FRENCH_MODE_ENABLED = False
        self.MOVIES_ENABLED = True
        self.TV_SHOWS_ENABLED = True
        self.ANIME_MOVIES_ENABLED = True
        self.ANIME_SERIES_ENABLED = True
        self.CLEANUP_MODE_ENABLED = False

    def get_path(self, key: str) -> Optional[Path]:
        p = getattr(self, key)
        return Path(p) if p else None
    def to_dict(self):
        d = {};
        for k, v in self.__dict__.items():
            if not k.startswith('_'): d[k] = list(v) if isinstance(v, set) else v
        return d
    @classmethod
    def from_dict(cls, data):
        config = cls()
        for k, v in data.items():
            if hasattr(config, k):
                if isinstance(getattr(config, k), set): setattr(config, k, set(v))
                else: setattr(config, k, v)
        return config
    def save(self, path: Path):
        try:
            with open(path, 'w') as f: json.dump(self.to_dict(), f, indent=4)
        except Exception as e: logging.error(f"Failed to save config to '{path}': {e}")
    @classmethod
    def load(cls, path: Path):
        if not path.exists(): return cls()
        try:
            with open(path, 'r') as f: content = f.read()
            if not content.strip(): return cls()
            return cls.from_dict(json.loads(content))
        except (json.JSONDecodeError, Exception) as e: logging.error(f"Error loading config from '{path}': {e}. Loading defaults."); return cls()
    def validate(self) -> (bool, str):
        if not self.OMDB_API_KEY or self.OMDB_API_KEY == "yourkey": return False, "OMDb API key is not configured."
        source_dir = self.get_path('SOURCE_DIR')
        if not source_dir or not source_dir.exists(): return False, f"Source directory not found or not set: {source_dir}"
        return True, "Validation successful."

def setup_logging(log_file: Path, log_to_console: bool = False):
    handlers = [logging.FileHandler(log_file, encoding='utf-8')]
    if log_to_console: handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=handlers, force=True)

class TitleCleaner:
    METADATA_BREAKPOINT_PATTERN = re.compile(r'('r'\s[\(\[]?\d{4}[\)\]]?\b'r'|\s[Ss]\d{1,2}[Ee]\d{1,2}\b'r'|\s[Ss]\d{1,2}\b'r'|\sSeason\s\d{1,2}\b'r'|\s\d{3,4}p\b'r'|\s(WEBRip|BluRay|BDRip|DVDRip|HDRip|WEB-DL|HDTV)\b'r'|\s(x264|x265|H\.?264|H\.?265|HEVC|AVC)\b'r')', re.IGNORECASE)
    @classmethod
    def clean_for_search(cls, name: str, custom_strings_to_remove: Set[str]) -> str:
        name_with_spaces = re.sub(r'[\._]', ' ', name); temp_title = name_with_spaces
        for s in custom_strings_to_remove: temp_title = re.sub(r'\b' + re.escape(s) + r'\b', ' ', temp_title, flags=re.IGNORECASE)
        title_part = temp_title[:match.start()] if (match := cls.METADATA_BREAKPOINT_PATTERN.search(temp_title)) else temp_title
        cleaned_title = re.sub(r'\[[^\]]+\]', '', title_part)
        return re.sub(r'\s+', ' ', cleaned_title).strip()
    @classmethod
    def extract_season_info(cls, filename: str) -> Optional[int]:
        for p in [r'[Ss](\d{1,2})[Ee]\d{1,2}', r'Season[ _-]?(\d{1,2})', r'[Ss](\d{1,2})']:
            if m:=re.search(p, filename, re.IGNORECASE): return int(m.group(1))
        return None
    @classmethod
    def extract_year(cls, filename: str) -> Optional[str]:
        matches = re.findall(r'\b(\d{4})\b', filename)
        if not matches: return None
        current_year = datetime.now().year
        plausible_years = [m for m in matches if 1900 <= int(m) <= current_year + 2]
        return plausible_years[-1] if plausible_years else None

class APIClient:
    def __init__(self, config: Config): self.config = config; self.session = requests.Session(); self.session.headers.update({'User-Agent': 'SortMeDown/Engine/4.0'})
    def query_omdb(self, title: str) -> Optional[Dict[str, Any]]:
        try:
            for params in [{"t": title}, {"s": title}]:
                full_params = {**params, "apikey": self.config.OMDB_API_KEY}; response = self.session.get(self.config.OMDB_URL, params=full_params, timeout=10)
                response.raise_for_status(); data = response.json()
                if data.get("Response") == "True":
                    if "Search" in data: id_params = {"i": data["Search"][0]["imdbID"], "apikey": self.config.OMDB_API_KEY}; id_response = self.session.get(self.config.OMDB_URL, params=id_params, timeout=10); return id_response.json()
                    return data
        except requests.RequestException as e: logging.error(f"OMDb API request failed for '{title}': {e}")
        return None
    def query_anilist(self, title: str) -> Optional[Dict[str, Any]]:
        query = '''query ($search: String) { Media(search: $search, type: ANIME) { title { romaji english native } format, genres, season, seasonYear, episodes } }'''
        try:
            response = self.session.post(self.config.ANILIST_URL, json={"query": query, "variables": {"search": title}}, timeout=10)
            response.raise_for_status(); media = response.json().get("data", {}).get("Media")
            if media: logging.info(f"AniList found match for: {title}"); return media
        except requests.RequestException as e: logging.error(f"AniList API request failed for '{title}': {e}")
        return None

class MediaClassifier:
    def __init__(self, api_client: APIClient): self.api_client = api_client
    def classify_media(self, name: str, custom_strings: Set[str]) -> MediaInfo:
        clean_name = TitleCleaner.clean_for_search(name, custom_strings); logging.info(f"Classifying: '{name}' -> Clean search: '{clean_name}'")
        if not clean_name: logging.warning(f"Could not extract a clean name from '{name}'. Skipping."); return MediaInfo(title=name, year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)
        anilist_data = self.api_client.query_anilist(clean_name); sleep(self.api_client.config.REQUEST_DELAY); omdb_data = self.api_client.query_omdb(clean_name)
        if anilist_data and omdb_data and "animation" not in omdb_data.get("Genre","").lower() and "japan" not in omdb_data.get("Country","").lower(): return self._classify_from_omdb(omdb_data)
        if anilist_data: return self._classify_from_anilist(anilist_data)
        if omdb_data: return self._classify_from_omdb(omdb_data)
        logging.warning(f"No API results found for: {clean_name}"); return MediaInfo(title=name, year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)
    def _classify_from_anilist(self, data: Dict[str, Any]) -> MediaInfo:
        f_type = data.get("format", "").upper(); m_type = MediaType.ANIME_MOVIE if f_type == "MOVIE" else MediaType.ANIME_SERIES if f_type in ["TV", "TV_SHORT", "ONA", "OVA", "SPECIAL"] else MediaType.UNKNOWN
        title = data.get('title', {}).get('english') or data.get('title', {}).get('romaji'); return MediaInfo(title=title, year=str(data.get("seasonYear", "")), media_type=m_type, language="Japanese", genre=", ".join(data.get("genres", [])))
    def _classify_from_omdb(self, data: Dict[str, Any]) -> MediaInfo:
        type_ = data.get("Type", "").lower(); m_type = MediaType.MOVIE if type_ == "movie" else MediaType.TV_SERIES if type_ in ["series", "tv series"] else MediaType.UNKNOWN
        return MediaInfo(title=data.get("Title"), year=(data.get("Year", "") or "").split('–')[0], media_type=m_type, language=data.get("Language", ""), genre=data.get("Genre", ""))

class FileManager:
    def __init__(self, cfg: Config, dry_run: bool): self.cfg, self.dry_run = cfg, dry_run
    def _find_sidecar_files(self, primary_file: Path) -> List[Path]:
        sidecars = []; stem = primary_file.stem
        for sibling in primary_file.parent.iterdir():
            if sibling != primary_file and sibling.stem == stem and sibling.suffix.lower() in self.cfg.SIDECAR_EXTENSIONS: sidecars.append(sibling)
        return sidecars
    def ensure_dir(self, p: Path) -> bool:
        if not p: logging.error("Destination directory path is not set."); return False
        if not p.exists():
            if self.dry_run: logging.info(f"DRY RUN: Would create dir '{p}'")
            else:
                try: p.mkdir(parents=True, exist_ok=True)
                except Exception as e: logging.error(f"Could not create directory '{p}': {e}"); return False
        return True
    def move_file_group(self, file_group: List[Path], dest_dir: Path) -> bool:
        if not self.ensure_dir(dest_dir): return False
        primary_file = file_group[0]; all_moved_successfully = True
        for file_to_move in file_group:
            target = dest_dir / file_to_move.name
            if str(file_to_move.resolve()) == str(target.resolve()): logging.info(f"Skipping move: '{file_to_move.name}' is already in correct location."); continue
            if target.exists(): logging.warning(f"SKIPPED: File '{target.name}' already exists in '{dest_dir.name}'."); continue
            log_prefix = "DRY RUN:" if self.dry_run else "Moved"
            if file_to_move != primary_file: log_prefix += " (sidecar)"
            logging.info(f"{log_prefix}: '{file_to_move.name}' -> '{dest_dir.name}'")
            if not self.dry_run:
                try: shutil.move(str(file_to_move), str(target))
                except Exception as e: logging.error(f"ERROR moving file '{file_to_move.name}': {e}"); all_moved_successfully = False
        return all_moved_successfully

class DirectoryWatcher:
    def __init__(self, config: Config): self.config = config; self.last_mtime = 0; self._scan()
    def _scan(self):
        if (source_dir := self.config.get_path('SOURCE_DIR')) and source_dir.exists(): self.last_mtime = source_dir.stat().st_mtime
    def check_for_changes(self) -> bool:
        if (source_dir := self.config.get_path('SOURCE_DIR')) and source_dir.exists():
            mtime = source_dir.stat().st_mtime
            if mtime > self.last_mtime: self.last_mtime = mtime; return True
        return False

class MediaSorter:
    def __init__(self, cfg: Config, dry_run: bool = False):
        self.cfg = cfg; self.dry_run = dry_run; self.api_client = APIClient(cfg); self.classifier = MediaClassifier(self.api_client)
        self.fm = FileManager(cfg, self.dry_run); self.stats = {}; self.stop_event = threading.Event(); self.is_processing = False; self._watcher_thread = None
    def signal_stop(self): self.stop_event.set(); logging.info("Stop signal received. Finishing current item...")
    def _get_mismatched_path(self) -> Optional[Path]:
        if path := self.cfg.get_path('MISMATCHED_DIR'): return path
        if source_path := self.cfg.get_path('SOURCE_DIR'): return source_path / '_Mismatched'
        return None
    def ensure_target_dirs(self) -> bool:
        if self.cfg.CLEANUP_MODE_ENABLED: return True
        dirs_to_check = [self._get_mismatched_path()]
        if self.cfg.MOVIES_ENABLED: dirs_to_check.append(self.cfg.get_path('MOVIES_DIR'))
        if self.cfg.TV_SHOWS_ENABLED: dirs_to_check.append(self.cfg.get_path('TV_SHOWS_DIR'))
        if self.cfg.ANIME_MOVIES_ENABLED: dirs_to_check.append(self.cfg.get_path('ANIME_MOVIES_DIR'))
        if self.cfg.ANIME_SERIES_ENABLED: dirs_to_check.append(self.cfg.get_path('ANIME_SERIES_DIR'))
        if self.cfg.FRENCH_MODE_ENABLED: dirs_to_check.append(self.cfg.get_path('FRENCH_MOVIES_DIR'))
        return all(self.fm.ensure_dir(d) for d in dirs_to_check if d)
    def _validate_api_result(self, file_path: Path, folder_name: str, api_info: MediaInfo) -> MediaInfo:
        is_series_in_filename = TitleCleaner.extract_season_info(file_path.name) is not None
        is_movie_in_api = api_info.media_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]
        if is_series_in_filename and is_movie_in_api:
            logging.warning(f"CONFLICT: Filename '{file_path.name}' indicates series, but API classified '{api_info.title}' as a movie. Trusting filename.")
            new_type = MediaType.ANIME_SERIES if (api_info.language and "japanese" in api_info.language.lower()) else MediaType.TV_SERIES
            api_info.media_type = new_type
        year_in_filename = TitleCleaner.extract_year(file_path.name) or TitleCleaner.extract_year(folder_name)
        if year_in_filename and api_info.year and year_in_filename != api_info.year:
            logging.warning(f"CONFLICT: Filename year '{year_in_filename}' mismatches API year '{api_info.year}' for '{api_info.title}'. Reverting to safe fallback mode.")
            clean_title = TitleCleaner.clean_for_search(folder_name, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
            api_info.media_type = MediaType.UNKNOWN; api_info.title = clean_title; api_info.year = year_in_filename
        return api_info
    def sort_item(self, item: Path):
        if item.suffix.lower() in self.cfg.SIDECAR_EXTENSIONS: return
        name_to_classify = item.parent.name if item.parent != self.cfg.get_path('SOURCE_DIR') else item.stem
        initial_info = self.classifier.classify_media(name_to_classify, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
        info = self._validate_api_result(item, name_to_classify, initial_info)
        files_to_move = [item] + self.fm._find_sidecar_files(item)
        log_msg = f"Class: {info.media_type.value} | Title: '{info.get_folder_name()}'"; s = self.stats
        if len(files_to_move) > 1: log_msg += f" | Found {len(files_to_move) - 1} sidecar file(s)."
        logging.info(log_msg)
        if info.media_type == MediaType.UNKNOWN:
            s['unknown'] += 1
            if self.cfg.CLEANUP_MODE_ENABLED: logging.warning("Skipping fallback move in Cleanup Mode."); return
            if info.title and info.year:
                is_series = TitleCleaner.extract_season_info(item.name) is not None
                if is_series:
                    fallback_dest = self.cfg.FALLBACK_SHOW_DESTINATION
                    if fallback_dest == "ignore": logging.info("Fallback handler: Mismatched series set to 'ignore'. Leaving in place."); return
                    logging.info(f"Fallback handler: Mismatched series routing to '{fallback_dest}' destination.")
                    dest_map = {"tv": self.cfg.get_path('TV_SHOWS_DIR'), "anime": self.cfg.get_path('ANIME_SERIES_DIR'), "mismatched": self._get_mismatched_path()}
                    base_dir = dest_map.get(fallback_dest)
                    if not base_dir: logging.error(f"Fallback destination '{fallback_dest}' dir not set. Skipping."); s['errors'] += 1; return
                    season = TitleCleaner.extract_season_info(item.name) or 1
                    dest_folder = base_dir / info.get_folder_name() / f"Season {season:02d}"
                    if self.fm.move_file_group(files_to_move, dest_folder): s['unknown'] -=1; s['tv' if fallback_dest == 'tv' else 'anime_series' if fallback_dest == 'anime' else 'unknown'] +=1
                    else: s['errors'] += 1
                else: # Fallback for a movie
                    logging.info("Fallback handler: Mismatched movie routing to Mismatched folder.")
                    base_dir = self._get_mismatched_path()
                    if not base_dir: logging.error("Mismatched directory not set or determinable. Skipping."); s['errors'] += 1; return
                    if self.fm.move_file_group(files_to_move, base_dir / info.get_folder_name()): s['unknown'] -=1; s['movies'] +=1
                    else: s['errors'] += 1
            return
        type_enabled_map = {MediaType.MOVIE: self.cfg.MOVIES_ENABLED, MediaType.TV_SERIES: self.cfg.TV_SHOWS_ENABLED, MediaType.ANIME_MOVIE: self.cfg.ANIME_MOVIES_ENABLED, MediaType.ANIME_SERIES: self.cfg.ANIME_SERIES_ENABLED}
        if not type_enabled_map.get(info.media_type, True): logging.info(f"Skipping {info.media_type.value} sort (disabled in config)."); return
        base_dir = item.parent if self.cfg.CLEANUP_MODE_ENABLED else {MediaType.MOVIE: self.cfg.get_path('MOVIES_DIR'), MediaType.TV_SERIES: self.cfg.get_path('TV_SHOWS_DIR'), MediaType.ANIME_MOVIE: self.cfg.get_path('ANIME_MOVIES_DIR'), MediaType.ANIME_SERIES: self.cfg.get_path('ANIME_SERIES_DIR')}.get(info.media_type)
        if info.media_type == MediaType.MOVIE and self.cfg.FRENCH_MODE_ENABLED and "french" in (info.language or "").lower() and not self.cfg.CLEANUP_MODE_ENABLED: base_dir = self.cfg.get_path('FRENCH_MOVIES_DIR')
        if not base_dir: logging.error(f"Target directory for {info.media_type.value} is not set."); s['errors'] += 1; return
        if info.media_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]:
            key = 'anime_movies' if info.media_type == MediaType.ANIME_MOVIE else 'french_movies' if base_dir == self.cfg.get_path('FRENCH_MOVIES_DIR') else 'movies'
            if self.fm.move_file_group(files_to_move, base_dir / info.get_folder_name()): s[key] += 1
            else: s['errors'] += 1
        elif info.media_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
            key = 'anime_series' if info.media_type == MediaType.ANIME_SERIES else 'tv'
            season = TitleCleaner.extract_season_info(item.name) or 1
            if self.fm.move_file_group(files_to_move, base_dir / info.get_folder_name() / f"Season {season:02d}"): s[key] += 1
            else: s['errors'] += 1

    def process_source_directory(self):
        self.is_processing = True
        try:
            self.stop_event.clear(); self.stats = {k: 0 for k in ['processed','movies','tv','anime_movies','anime_series','french_movies','unknown','errors']}
            source_dir = self.cfg.get_path('SOURCE_DIR')
            if not source_dir or not source_dir.exists() or not self.ensure_target_dirs(): logging.error("Source/Target directory validation failed."); return
            logging.info("Starting deep scan of source directory...")
            all_files_found = [p for ext in self.cfg.SUPPORTED_EXTENSIONS.union(self.cfg.SIDECAR_EXTENSIONS) for p in source_dir.glob(f'**/*{ext}') if p.is_file()]
            mismatched_path = self._get_mismatched_path()
            if mismatched_path and mismatched_path.exists():
                mismatched_path_abs = mismatched_path.resolve()
                initial_count = len(all_files_found)
                all_files_found = [f for f in all_files_found if not str(f.resolve().parent).startswith(str(mismatched_path_abs))]
                excluded_count = initial_count - len(all_files_found)
                if excluded_count > 0: logging.info(f"Excluding {excluded_count} file(s) from the Mismatched directory.")
            media_files = [f for f in all_files_found if f.suffix.lower() in self.cfg.SUPPORTED_EXTENSIONS]
            if not media_files: logging.info("No primary media files found to process.")
            else:
                logging.info(f"Found {len(media_files)} primary media files to process.")
                for file_path in media_files:
                    if self.stop_event.is_set(): logging.warning("Sort run aborted by user."); break
                    self.stats['processed'] += 1
                    try: self.sort_item(file_path)
                    except Exception as e: self.stats['errors'] += 1; logging.error(f"Fatal error processing '{file_path.name}': {e}", exc_info=True)
            if not self.stop_event.is_set() and not self.cfg.CLEANUP_MODE_ENABLED: self.cleanup_empty_dirs(source_dir)
            self.log_summary()
        finally: self.is_processing = False
    def cleanup_empty_dirs(self, path: Path):
        if self.dry_run: logging.info("DRY RUN: Skipping cleanup of empty directories."); return
        logging.info("Sweeping for empty directories...")
        mismatched_path = self._get_mismatched_path()
        for dirpath, _, _ in os.walk(path, topdown=False):
            dp = Path(dirpath).resolve()
            if dp == path.resolve(): continue
            if mismatched_path and dp == mismatched_path.resolve(): continue
            try:
                if not os.listdir(dirpath): os.rmdir(dirpath); logging.info(f"Removed empty directory: {dirpath}")
            except OSError as e: logging.error(f"Error removing directory {dirpath}: {e}")
    def start_watch_mode(self):
        if self._watcher_thread and self._watcher_thread.is_alive(): logging.warning("Watch mode is already running."); return
        if self.cfg.CLEANUP_MODE_ENABLED: logging.error("FATAL: Watch mode cannot be started when 'Clean Up In Place' mode is enabled."); return
        def _watch_loop():
            self.is_processing = True; logging.info("Watch mode started. Press Ctrl+C in the terminal to stop."); logging.info("Performing initial sort...")
            self.process_source_directory()
            watcher = DirectoryWatcher(self.cfg)
            logging.info(f"Initial sort complete. Now watching for changes every {self.cfg.WATCH_INTERVAL // 60} minutes.")
            while not self.stop_event.wait(timeout=self.cfg.WATCH_INTERVAL):
                if watcher.check_for_changes(): logging.info("Changes detected! Starting new sort..."); self.process_source_directory(); logging.info("Processing complete. Resuming watch.")
            logging.info("Watch mode stopped."); self.is_processing = False
        self.stop_event.clear(); self._watcher_thread = threading.Thread(target=_watch_loop, daemon=True); self._watcher_thread.start()
    def log_summary(self):
        summary = f"\n\n--- PROCESSING SUMMARY ---\n";
        for k, v in self.stats.items(): summary += f"{k.replace('_',' ').title():<15}: {v}\n"
        summary += f"--------------------------\n"; logging.info(summary)
