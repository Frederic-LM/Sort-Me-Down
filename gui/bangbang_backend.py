"""
SortMeDown Sorter - Backend Logic (bangbang_backend.py)  
======================================================

This file contains the core logic for the SortMeDown media sorter. It is
designed to be a self-contained "engine" that can be controlled by any
frontend, such as the command-line interface or `gui.py`.

Major Feature Iterations & Architectural Changes:
-------------------------------------------------
version 1.11

- Sidecar File Handling: Re-architected the file moving logic to intelligently
  detect and move "sidecar" files (e.g., .srt, .sub, .nfo) along with their
  primary media file. The sorter now processes file *groups* instead of
  individual files, preventing subtitles and metadata from being left behind.
  This was achieved by adding a `_find_sidecar_files` method to the
  FileManager and updating the `sort_item` logic.

version 1.10

- Initial Refactor: Separated from the original `bangbang.py` script to remove
  all `print()` statements and argument parsing, relying on `logging` and a
  `Config` class instead.
- Config Management: The `Config` class can be saved to and loaded from a
  `config.json` file, making settings persistent.
- Modular Sorting: Added enable/disable flags to the `Config` class and logic
  in the `MediaSorter` to selectively process different media types (Movies,
  TV Shows, etc.).
- "Clean Up Mode": Implemented logic to allow sorting/renaming files and folders
  *in place* within the source directory, rather than moving them to an
  external library.
- Recursive Deep Scan: Re-architected the file discovery process to perform a
  deep, recursive scan of the source directory. This makes the sorter
  item-based (processing one file at a time) instead of folder-based, which
  prevents data loss and allows it to correctly handle complex, pre-organized
  nested subdirectories.
- Safety and Robustness:
  - Added a "final sweep" to clean up all newly-emptied directories at the
    end of a run.
  - The `FileManager` can now detect if a file is already in its correct
    final destination and will skip it to prevent unnecessary operations.
- Interruptible Tasks & State Management:
  - Implemented a universal `stop_event` system in the `MediaSorter` class,
    allowing any running task (one-shot sort or watcher) to be safely
    interrupted.
  - Added an `is_processing` flag to provide real-time status updates to the
    frontend, enabling a more intelligent and responsive UI (e.g., the
    "IDLE" state).

"""

from pathlib import Path
import re
import shutil
import requests
import logging
from time import sleep
from typing import Optional, Dict, Any, Set, List
import json
import threading
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import os


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
        self.SOURCE_DIR = ""; self.MOVIES_DIR = ""; self.FRENCH_MOVIES_DIR = ""
        self.TV_SHOWS_DIR = ""; self.ANIME_MOVIES_DIR = ""; self.ANIME_SERIES_DIR = ""
        # <<< CHANGE: Added common sidecar file extensions
        self.SUPPORTED_EXTENSIONS = [
            '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', 
            '.mpg', '.mpeg', '.3gp', '.ogv', '.ts', '.m2ts', '.mts'
        ]
        self.SIDECAR_EXTENSIONS = ['.srt', '.sub', '.nfo', '.txt', '.jpg', '.png']
        self.CUSTOM_STRINGS_TO_REMOVE = ['FRENCH', 'TRUEFRENCH', 'VOSTFR', 'MULTI', 'SUBFRENCH']
        self.OMDB_API_KEY = "yourkey"; self.OMDB_URL = "http://www.omdbapi.com/"; self.ANILIST_URL = "https://graphql.anilist.co"
        self.REQUEST_DELAY = 1.0; self.WATCH_INTERVAL = 15 * 60
        self.FRENCH_MODE_ENABLED = False
        self.MOVIES_ENABLED = True; self.TV_SHOWS_ENABLED = True
        self.ANIME_MOVIES_ENABLED = True; self.ANIME_SERIES_ENABLED = True
        self.CLEANUP_MODE_ENABLED = False
    def get_path(self, key: str) -> Optional[Path]:
        p = getattr(self, key)
        return Path(p) if p else None
    def get_set(self, key: str) -> Set[str]:
        return set(getattr(self, key))
    def to_dict(self):
        return {key: value for key, value in self.__dict__.items() if not key.startswith('_')}
    @classmethod
    def from_dict(cls, data):
        config = cls()
        for key, value in data.items():
            if hasattr(config, key): setattr(config, key, value)
        return config
    def save(self, path: Path):
        with open(path, 'w') as f: json.dump(self.to_dict(), f, indent=4)
    @classmethod
    def load(cls, path: Path):
        if not path.exists(): return cls()
        try:
            with open(path, 'r') as f:
                content = f.read()
                if not content: return cls()
                return cls.from_dict(json.loads(content))
        except (json.JSONDecodeError, Exception) as e:
            logging.error(f"Error loading '{path}': {e}. Loading defaults.")
            return cls()
    def validate(self) -> bool:
        if not self.OMDB_API_KEY or self.OMDB_API_KEY == "yourkey":
            logging.warning("OMDb API key not configured."); return False
        source_dir = self.get_path('SOURCE_DIR')
        if not source_dir or not source_dir.exists():
            logging.error(f"Source directory not found or not set: {source_dir}"); return False
        return True
class TitleCleaner:
    METADATA_BREAKPOINT_PATTERN = re.compile(r'('r'\s[\(\[]?\d{4}[\)\]]?\b'r'|\s[Ss]\d{1,2}[Ee]\d{1,2}\b'r'|\s[Ss]\d{1,2}\b'r'|\sSeason\s\d{1,2}\b'r'|\s\d{3,4}p\b'r'|\s(WEBRip|BluRay|BDRip|DVDRip|HDRip|WEB-DL|HDTV)\b'r'|\s(x264|x265|H\.?264|H\.?265|HEVC|AVC)\b'r')', re.IGNORECASE)
    @classmethod
    def clean_for_search(cls, name: str, custom_strings_to_remove: Set[str]) -> str:
        name_with_spaces = re.sub(r'[\._]', ' ', name)
        temp_title = name_with_spaces
        for s in custom_strings_to_remove: temp_title = re.sub(r'\b' + re.escape(s) + r'\b', ' ', temp_title, flags=re.IGNORECASE)
        title_part = temp_title[:match.start()] if (match := cls.METADATA_BREAKPOINT_PATTERN.search(temp_title)) else temp_title
        cleaned_title = re.sub(r'\[[^\]]+\]', '', title_part)
        return re.sub(r'\s+', ' ', cleaned_title).strip()
    @classmethod
    def extract_season_info(cls, filename: str) -> Optional[int]:
        for p in [r'[Ss](\d{1,2})[Ee]\d{1,2}', r'Season[ _-]?(\d{1,2})', r'[Ss](\d{1,2})']:
            if m:=re.search(p, filename, re.IGNORECASE): return int(m.group(1))
        return None
class APIClient:
    def __init__(self, config: Config):
        self.config = config; self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'SortMeDown/GUI'})
    def query_omdb(self, title: str) -> Optional[Dict[str, Any]]:
        try:
            for params in [{"t": title}, {"s": title}]:
                full_params = {**params, "apikey": self.config.OMDB_API_KEY}
                response = self.session.get(self.config.OMDB_URL, params=full_params, timeout=10)
                response.raise_for_status(); data = response.json()
                if data.get("Response") == "True":
                    if "Search" in data:
                        id_params = {"i": data["Search"][0]["imdbID"], "apikey": self.config.OMDB_API_KEY}
                        id_response = self.session.get(self.config.OMDB_URL, params=id_params, timeout=10)
                        return id_response.json()
                    return data
        except requests.RequestException as e: logging.error(f"OMDb API request failed for '{title}': {e}")
        return None
    def query_anilist(self, title: str) -> Optional[Dict[str, Any]]:
        query = '''query ($search: String) { Media(search: $search, type: ANIME) { title { romaji english native } format, genres, season, seasonYear, episodes } }'''
        try:
            response = self.session.post(self.config.ANILIST_URL, json={"query": query, "variables": {"search": title}}, timeout=10)
            response.raise_for_status()
            media = response.json().get("data", {}).get("Media")
            if media: logging.info(f"AniList found match for: {title}"); return media
        except requests.RequestException as e: logging.error(f"AniList API request failed for '{title}': {e}")
        return None
class MediaClassifier:
    def __init__(self, api_client: APIClient): self.api_client = api_client
    def classify_media(self, name: str, custom_strings: Set[str]) -> MediaInfo:
        clean_name = TitleCleaner.clean_for_search(name, custom_strings)
        logging.info(f"\n🔍 Processing: '{name}' -> Clean search: '{clean_name}'")
        if not clean_name:
            logging.warning(f"Could not extract a clean name from '{name}'. Skipping.")
            return MediaInfo(title=name, year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)
        anilist_data = self.api_client.query_anilist(clean_name)
        sleep(self.api_client.config.REQUEST_DELAY)
        omdb_data = self.api_client.query_omdb(clean_name)
        if anilist_data:
            if omdb_data and "animation" not in omdb_data.get("Genre","").lower() and "japan" not in omdb_data.get("Country","").lower():
                return self._classify_from_omdb(omdb_data)
            return self._classify_from_anilist(anilist_data)
        if omdb_data: return self._classify_from_omdb(omdb_data)
        logging.warning(f"No API results found for: {clean_name}")
        return MediaInfo(title=name, year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)
    def _classify_from_anilist(self, data: Dict[str, Any]) -> MediaInfo:
        f_type = data.get("format", "").upper()
        m_type = MediaType.ANIME_MOVIE if f_type == "MOVIE" else MediaType.ANIME_SERIES if f_type in ["TV", "TV_SHORT", "ONA", "OVA", "SPECIAL"] else MediaType.UNKNOWN
        title = data.get('title', {}).get('english') or data.get('title', {}).get('romaji')
        return MediaInfo(title=title, year=str(data.get("seasonYear", "")), media_type=m_type, language="Japanese", genre=", ".join(data.get("genres", [])))
    def _classify_from_omdb(self, data: Dict[str, Any]) -> MediaInfo:
        type_ = data.get("Type", "").lower()
        m_type = MediaType.MOVIE if type_ == "movie" else MediaType.TV_SERIES if type_ in ["series", "tv series"] else MediaType.UNKNOWN
        return MediaInfo(title=data.get("Title"), year=(data.get("Year", "") or "").split('–')[0], media_type=m_type, language=data.get("Language", ""), genre=data.get("Genre", ""))

class FileManager:
    def __init__(self, cfg: Config, dry: bool): self.cfg, self.dry = cfg, dry

    def _find_sidecar_files(self, primary_file: Path) -> List[Path]:
        # <<< CHANGE: New method to find associated files (subtitles, nfo, etc.)
        sidecars = []
        stem = primary_file.stem
        for sibling in primary_file.parent.iterdir():
            if sibling != primary_file and sibling.stem == stem and sibling.suffix.lower() in self.cfg.SIDECAR_EXTENSIONS:
                sidecars.append(sibling)
        return sidecars

    def ensure_dir(self, p: Path) -> bool:
        if not p: logging.error("❌ ERROR: Destination directory path is not set."); return False
        if not p.exists():
            if self.dry: logging.info(f"📁 DRY RUN: Would create dir '{p}'")
            else:
                try: p.mkdir(parents=True, exist_ok=True)
                except Exception as e: logging.error(f"❌ ERROR: Could not create directory '{p}': {e}"); return False
        return True

    def move_file_group(self, file_group: List[Path], dest_dir: Path) -> bool:
        # <<< CHANGE: Method now handles a group of files instead of one.
        if not self.ensure_dir(dest_dir): return False
        
        primary_file = file_group[0]
        success_count = 0

        for file_to_move in file_group:
            target = dest_dir / file_to_move.name
            if str(file_to_move.resolve()) == str(target.resolve()):
                logging.info(f"Skipping move: '{file_to_move.name}' is already in its correct location.")
                success_count += 1
                continue
            
            if target.exists():
                logging.warning(f"⚠️  SKIPPED: File '{target.name}' already exists in '{dest_dir.name}'.")
                continue # Skip this file but try to move others in the group

            if self.dry:
                # <<< CHANGE: Improved dry-run logging
                log_prefix = "🧪 DRY RUN:"
                if file_to_move != primary_file:
                    log_prefix += " (sidecar)"
                logging.info(f"{log_prefix} Would move '{file_to_move.name}' → '{dest_dir}'")
                success_count += 1
                continue
            
            try:
                shutil.move(str(file_to_move), str(target))
                log_prefix = "✅ Moved"
                if file_to_move != primary_file:
                    log_prefix += " (sidecar)"
                logging.info(f"{log_prefix}: '{file_to_move.name}' → '{dest_dir.name}'")
                success_count += 1
            except Exception as e:
                logging.error(f"❌ ERROR moving file '{file_to_move.name}': {e}")

        # Return True only if the primary file was moved successfully.
        return success_count > 0 and primary_file not in [f for f in file_group if not (dest_dir / f.name).exists()]


class DirectoryWatcher:
    def __init__(self, config: Config):
        self.config = config; self.last_mtime = 0; self._scan()
    def _scan(self):
        if (source_dir := self.config.get_path('SOURCE_DIR')) and source_dir.exists(): self.last_mtime = source_dir.stat().st_mtime
    def check_for_changes(self) -> bool:
        if (source_dir := self.config.get_path('SOURCE_DIR')) and source_dir.exists():
            if (mtime := source_dir.stat().st_mtime) > self.last_mtime: self.last_mtime = mtime; return True
        return False
class WatchModeManager:
    def __init__(self, sorter: 'MediaSorter'):
        self.sorter = sorter; self.watcher = DirectoryWatcher(sorter.cfg)
    def stop(self):
        self.sorter.signal_stop()
    def start(self):
        logging.info("🚀 Performing initial sort...")
        self.sorter.process_source_directory()
        if self.sorter.stop_event.is_set(): logging.info("🛑 Watch mode startup aborted."); return
        self.watcher._scan()
        self._loop()
    def _loop(self):
        while not self.sorter.stop_event.is_set():
            if self.watcher.check_for_changes():
                logging.info(f"🔄 Changes detected! Starting processing...")
                self.sorter.process_source_directory()
                if self.sorter.stop_event.is_set(): break
                logging.info(f"✅ Processing complete.")
            if self.sorter.stop_event.wait(timeout=self.sorter.cfg.WATCH_INTERVAL): break
        logging.info("🛑 Watch mode stopped.")

class MediaSorter:
    def __init__(self, cfg: Config, dry: bool):
        self.cfg, self.dry = cfg, dry
        self.api_client = APIClient(cfg); self.classifier = MediaClassifier(self.api_client)
        self.fm = FileManager(cfg, dry); self.watch_manager = None
        self.stats = {k: 0 for k in ['processed','movies','tv','anime_movies','anime_series','french_movies','unknown','errors']}
        self.stop_event = threading.Event()
        self.is_processing = False

    def signal_stop(self):
        self.stop_event.set()

    def ensure_target_dirs(self) -> bool:
        if self.cfg.CLEANUP_MODE_ENABLED: return True
        dirs_to_check = []
        if self.cfg.MOVIES_ENABLED: dirs_to_check.append(self.cfg.get_path('MOVIES_DIR'))
        if self.cfg.TV_SHOWS_ENABLED: dirs_to_check.append(self.cfg.get_path('TV_SHOWS_DIR'))
        if self.cfg.ANIME_MOVIES_ENABLED: dirs_to_check.append(self.cfg.get_path('ANIME_MOVIES_DIR'))
        if self.cfg.ANIME_SERIES_ENABLED: dirs_to_check.append(self.cfg.get_path('ANIME_SERIES_DIR'))
        if self.cfg.FRENCH_MODE_ENABLED: dirs_to_check.append(self.cfg.get_path('FRENCH_MOVIES_DIR'))
        return all(self.fm.ensure_dir(d) for d in dirs_to_check if d)

    def sort_item(self, item: Path):
        # <<< CHANGE: Skip sidecar files; they will be handled with their primary media file.
        if item.suffix.lower() in self.cfg.SIDECAR_EXTENSIONS:
            # Check if a corresponding media file exists. If not, it's an orphan we can't process.
            has_media_partner = any(
                (item.parent / f"{item.stem}{ext}").exists() 
                for ext in self.cfg.SUPPORTED_EXTENSIONS
            )
            if has_media_partner:
                logging.debug(f"Skipping sidecar '{item.name}', will be processed with its media file.")
                return
            else:
                logging.warning(f"Orphan sidecar file '{item.name}' found without a primary media file. Cannot process.")

        # The item is a primary media file.
        files_to_move = [item] + self.fm._find_sidecar_files(item)
        num_sidecars = len(files_to_move) - 1
        
        name_to_classify = item.parent.name if item.parent != self.cfg.get_path('SOURCE_DIR') else item.stem
        info = self.classifier.classify_media(name_to_classify, self.cfg.get_set('CUSTOM_STRINGS_TO_REMOVE'))
        
        log_msg = f"🏷️  Class: {info.media_type.value} | Title: '{info.get_folder_name()}'"
        if num_sidecars > 0:
            log_msg += f" | Found {num_sidecars} sidecar file(s)."
        logging.info(log_msg)

        s, m_type = self.stats, info.media_type
        if m_type == MediaType.MOVIE and not self.cfg.MOVIES_ENABLED: logging.warning("Skipping movie sort (disabled)."); return
        if m_type == MediaType.TV_SERIES and not self.cfg.TV_SHOWS_ENABLED: logging.warning("Skipping TV show sort (disabled)."); return
        if m_type == MediaType.ANIME_MOVIE and not self.cfg.ANIME_MOVIES_ENABLED: logging.warning("Skipping anime movie sort (disabled)."); return
        if m_type == MediaType.ANIME_SERIES and not self.cfg.ANIME_SERIES_ENABLED: logging.warning("Skipping anime series sort (disabled)."); return
        if m_type == MediaType.UNKNOWN: s['unknown'] += 1; return

        success, base_dir = False, None
        if self.cfg.CLEANUP_MODE_ENABLED: base_dir = self.cfg.get_path('SOURCE_DIR')
        else:
            if m_type == MediaType.MOVIE: base_dir = self.cfg.get_path('MOVIES_DIR')
            elif m_type == MediaType.TV_SERIES: base_dir = self.cfg.get_path('TV_SHOWS_DIR')
            elif m_type == MediaType.ANIME_MOVIE: base_dir = self.cfg.get_path('ANIME_MOVIES_DIR')
            elif m_type == MediaType.ANIME_SERIES: base_dir = self.cfg.get_path('ANIME_SERIES_DIR')
        if m_type == MediaType.MOVIE and self.cfg.FRENCH_MODE_ENABLED and "french" in (info.language or "").lower():
            if not self.cfg.CLEANUP_MODE_ENABLED: base_dir = self.cfg.get_path('FRENCH_MOVIES_DIR')
        if not base_dir: logging.error(f"Target directory for {m_type.value} is not set."); s['errors'] += 1; return
        
        if m_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]:
            key = 'anime_movies' if m_type == MediaType.ANIME_MOVIE else 'french_movies' if base_dir == self.cfg.get_path('FRENCH_MOVIES_DIR') else 'movies'
            dest_folder = base_dir / info.get_folder_name()
            # <<< CHANGE: Call move_file_group instead of move_file
            success = self.fm.move_file_group(files_to_move, dest_folder)
            if success: s[key] += 1
            else: s['errors'] += 1
        elif m_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
            key = 'anime_series' if m_type == MediaType.ANIME_SERIES else 'tv'
            season = TitleCleaner.extract_season_info(item.name) or 1
            season_dir = base_dir / info.get_folder_name() / f"Season {season:02d}"
            # <<< CHANGE: Call move_file_group instead of move_file
            success = self.fm.move_file_group(files_to_move, season_dir)
            if success: s[key] += 1
            else: s['errors'] += 1

    def process_source_directory(self):
        self.is_processing = True
        try:
            self.stop_event.clear()
            source_dir = self.cfg.get_path('SOURCE_DIR')
            self.stats = {k: 0 for k in self.stats}
            if not source_dir or not source_dir.exists() or not self.ensure_target_dirs():
                logging.error("Source/Target directory validation failed."); self.print_summary(); return
            
            logging.info("Scanning for media files...")
            # <<< CHANGE: Scan for all supported and sidecar files initially.
            all_extensions = self.cfg.SUPPORTED_EXTENSIONS + self.cfg.SIDECAR_EXTENSIONS
            all_files = [p for ext in all_extensions for p in source_dir.glob(f'**/*{ext}')]
            
            # <<< CHANGE: We only want to *process* the main media files, not the sidecars directly.
            media_files_to_process = [f for f in all_files if f.suffix.lower() in self.cfg.SUPPORTED_EXTENSIONS]

            if not media_files_to_process:
                logging.info("✨ No primary media files found to process.")
            else:
                logging.info(f"📂 Found {len(media_files_to_process)} primary media files to process.")
                for file_path in media_files_to_process:
                    if self.stop_event.is_set():
                        logging.warning("🛑 Sort run aborted by user.")
                        break
                    self.stats['processed'] += 1
                    try:
                        self.sort_item(file_path)
                    except Exception as e:
                        self.stats['errors'] += 1
                        logging.error(f"Fatal error processing group for '{file_path.name}': {e}", exc_info=True)

            if not self.stop_event.is_set():
                self.cleanup_empty_dirs(source_dir)
            
            self.print_summary()
        finally:
            self.is_processing = False

    def cleanup_empty_dirs(self, path: Path):
        if self.dry: logging.info("Dry Run: Skipping cleanup of empty directories."); return
        logging.info("🧹 Sweeping for empty directories...")
        for dirpath, _, _ in os.walk(path, topdown=False):
            if Path(dirpath).resolve() == path.resolve(): continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath); logging.info(f"Removed empty directory: {dirpath}")
            except OSError as e: logging.error(f"Error removing directory {dirpath}: {e}")

    def start_watch_mode(self):
        self.watch_manager = WatchModeManager(self); self.watch_manager.start()
    def stop_watch_mode(self):
        if self.watch_manager: self.watch_manager.stop()
    def print_summary(self):
        summary = f"\n{'='*50}\n📊 PROCESSING SUMMARY\n{'='*50}\n"
        for k, v in self.stats.items(): summary += f"{k.replace('_',' ').title():<15}: {v}\n"
        summary += f"{'='*50}"; logging.info(summary)
