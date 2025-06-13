#!/usr/bin/env python3
"""
Refactored bangbang.py (Version 4.0.0) ALPHA

This new version is a hybrid: it keeps the CLI-friendly nature (argument parsing, print statements, ASCII art) but replaces its core engine with the more robust logic we developed for the GUI.

Summary of Upgrades:

    Recursive Deep Scan: The script now scans all subdirectories in your source folder, finding every media file no matter how deeply it's nested.

    Sidecar File Handling: It now recognizes and moves associated files (.srt, .nfo, .sub, etc.) with their primary media file, just like the GUI version.

    Empty Directory Cleanup: After a run, it performs a final sweep to remove all newly-emptied folders.

    New "Cleanup In-Place" Mode: A new --cleanup-in-place argument has been added. This allows you to sort and rename files within the source directory, which is perfect for organizing an already-populated drive without moving files.

    Item-Based, Not Folder-Based: The logic is now centered on processing individual media files, which is far more reliable and prevents the data loss issues of the old folder-based approach.

    Increased Robustness: It now checks if a file is already in its destination and skips it, preventing unnecessary moves and errors.






SortMeDown a Media Sorter Script
================================

Automatically sorts media files and folders (movies, TV shows, anime) into organized directories
based on metadata from OMDb API and AniList API.

This version incorporates the advanced, item-based, recursive scanning engine
developed for the GUI, along with sidecar file handling and cleanup features.

Usage Examples:
---------------
# One-time recursive sort of the source directory
python bangbang.py

# Sort, separating French-language movies into a specific folder
python bangbang.py --fr

# Preview all actions without moving any files (highly recommended for first run)
python bangbang.py --dry-run

# Sort files IN-PLACE within the source directory (does not move to libraries)
python bangbang.py --cleanup-in-place

# Monitor the source directory for new files and sort them automatically
python bangbang.py --watch

Version: 4.0.0
"""

from pathlib import Path
import re
import shutil
import requests
import logging
import argparse
from time import sleep
from typing import Optional, Dict, Any, Set, List
import json
import signal
import sys
import threading
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import os

# ASCII Art Logo
ASCII_ART = """
#    ██████  ▒█████   ██▀███  ▄▄▄█████▓    ███▄ ▄███▓▓█████    ▓█████▄  ▒█████   █     █░███▄    █ 
#  ▒██    ▒ ▒██▒  ██▒▓██ ▒ ██▒▓  ██▒ ▓▒   ▓██▒▀█▀ ██▒▓█   ▀    ▒██▀ ██▌▒██▒  ██▒▓█░ █ ░█░██ ▀█   █ 
#  ░ ▓██▄   ▒██░  ██▒▓██ ░▄█ ▒▒ ▓██░ ▒░   ▓██    ▓██░▒███      ░██   █▌▒██░  ██▒▒█░ █ ░█▓██  ▀█ ██▒
#    ▒   ██▒▒██   ██░▒██▀▀█▄  ░ ▓██▓ ░    ▒██    ▒██ ▒▓█  ▄    ░▓█▄   ▌▒██   ██░░█░ █ ░█▓██▒  ▐▌██▒
#  ▒██████▒▒░ ████▓▒░░██▓ ▒██▒  ▒██▒ ░    ▒██▒   ░██▒░▒████▒   ░▒████▓ ░ ████▓▒░░░██▒██▓▒██░   ▓██░
#  ▒ ▒▓▒ ▒ ░░ ▒░▒░▒░ ░ ▒▓ ░▒▓░  ▒ ░░      ░ ▒░   ░  ░░░ ▒░ ░    ▒▒▓  ▒ ░ ▒░▒░▒░ ░ ▓░▒ ▒ ░ ▒░   ▒ ▒ 
#  ░ ░▒  ░ ░  ░ ▒ ▒░   ░▒ ░ ▒░    ░       ░  ░      ░ ░ ░  ░    ░ ▒  ▒   ░ ▒ ▒░   ▒ ░ ░ ░ ░░   ░ ▒░
#  ░  ░  ░  ░ ░ ░ ▒    ░░   ░   ░         ░      ░      ░       ░ ░  ░ ░ ░ ░ ▒    ░   ░    ░   ░ ░ 
#        ░      ░ ░     ░   Media Sorter Script  ░      ░  ░      ░        ░ ░      ░      4.0.0 ░ 
#                                                               ░                                    
"""

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
        self.SOURCE_DIR = Path("C:/download/unsorted")
        self.MOVIES_DIR = Path("D:/Movies")
        self.FRENCH_MOVIES_DIR = Path("D:/Films")
        self.TV_SHOWS_DIR = Path("D:/Series")
        self.ANIME_MOVIES_DIR = Path("D:/Anime_Movies")
        self.ANIME_SERIES_DIR = Path("D:/Anime_TV")
        # <<< MODIFIED: Separated primary media from sidecar files for better logic
        self.SUPPORTED_EXTENSIONS = {
            '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v',
            '.mpg', '.mpeg', '.3gp', '.ogv', '.ts', '.m2ts', '.mts'
        }
        self.SIDECAR_EXTENSIONS = {'.srt', '.sub', '.nfo', '.txt', '.jpg', '.png'}
        self.CUSTOM_STRINGS_TO_REMOVE = {'FRENCH', 'TRUEFRENCH', 'VOSTFR', 'MULTI', 'SUBFRENCH'}
        self.OMDB_API_KEY = "yourkey"
        self.OMDB_URL = "http://www.omdbapi.com/"
        self.ANILIST_URL = "https://graphql.anilist.co"
        self.LOG_FILE = Path(__file__).parent / "bangbangSMD.log"
        self.REQUEST_DELAY = 1.0
        self.WATCH_INTERVAL = 15 * 60

    def validate(self) -> bool:
        if not self.OMDB_API_KEY or self.OMDB_API_KEY == "yourkey":
            logging.warning("OMDb API key not configured"); return False
        if not self.SOURCE_DIR.exists():
            logging.error(f"Source directory not found: {self.SOURCE_DIR}"); return False
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
        self.session.headers.update({'User-Agent': 'SortMeDown/CLI/4.0.0'})
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
        logging.info(f"Classifying: '{name}' -> Clean search: '{clean_name}'")
        if not clean_name:
            logging.warning(f"Could not extract a clean name from '{name}'. Skipping.")
            return MediaInfo(title=name, year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)
        anilist_data = self.api_client.query_anilist(clean_name)
        sleep(self.api_client.config.REQUEST_DELAY)
        omdb_data = self.api_client.query_omdb(clean_name)
        if anilist_data and "animation" not in omdb_data.get("Genre","").lower() and "japan" not in omdb_data.get("Country","").lower():
            return self._classify_from_omdb(omdb_data)
        if anilist_data: return self._classify_from_anilist(anilist_data)
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

# <<< MODIFIED: FileManager is now aligned with the superior backend version
class FileManager:
    def __init__(self, cfg: Config, dry: bool):
        self.cfg = cfg
        self.dry = dry

    def _find_sidecar_files(self, primary_file: Path) -> List[Path]:
        sidecars = []
        stem = primary_file.stem
        for sibling in primary_file.parent.iterdir():
            if sibling != primary_file and sibling.stem == stem and sibling.suffix.lower() in self.cfg.SIDECAR_EXTENSIONS:
                sidecars.append(sibling)
        return sidecars

    def ensure_dir(self, p: Path) -> bool:
        if not p:
            print("❌ ERROR: Destination directory path is not set.")
            return False
        if not p.exists():
            if self.dry: print(f"📁 DRY RUN: Would create dir '{p}'")
            else:
                try: p.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    print(f"❌ ERROR: Could not create directory '{p}': {e}")
                    logging.error(f"Failed to create directory '{p}': {e}")
                    return False
        return True

    def move_file_group(self, file_group: List[Path], dest_dir: Path) -> bool:
        if not self.ensure_dir(dest_dir): return False
        
        primary_file = file_group[0]
        all_moved_successfully = True

        for file_to_move in file_group:
            target = dest_dir / file_to_move.name
            if str(file_to_move.resolve()) == str(target.resolve()):
                print(f"-> Skipping move: '{file_to_move.name}' is already in its correct location.")
                continue
            
            if target.exists():
                print(f"⚠️  SKIPPED: File '{target.name}' already exists in '{dest_dir.name}'.")
                continue

            log_prefix = "🧪 DRY RUN:"
            if file_to_move != primary_file: log_prefix += " (sidecar)"
            if self.dry:
                print(f"{log_prefix} Would move '{file_to_move.name}' → '{dest_dir}'")
                continue
            
            try:
                shutil.move(str(file_to_move), str(target))
                log_prefix = "✅ Moved"
                if file_to_move != primary_file: log_prefix += " (sidecar)"
                print(f"{log_prefix}: '{file_to_move.name}' → '{dest_dir.name}'")
            except Exception as e:
                print(f"❌ ERROR moving file '{file_to_move.name}': {e}")
                logging.error(f"Error moving file '{file_to_move}' to '{dest_dir}': {e}")
                all_moved_successfully = False
        
        return all_moved_successfully

class DirectoryWatcher:
    # ... (This class is fine as-is for the CLI)
    def __init__(self, config: Config): self.config, self.last_mtime = config, 0; self._scan()
    def _scan(self):
        if self.config.SOURCE_DIR.exists(): self.last_mtime = self.config.SOURCE_DIR.stat().st_mtime
    def check_for_changes(self) -> bool:
        if not self.config.SOURCE_DIR.exists(): return False
        mtime = self.config.SOURCE_DIR.stat().st_mtime
        if mtime > self.last_mtime: self.last_mtime = mtime; return True
        return False

class WatchModeManager:
    # ... (This class is fine as-is for the CLI)
    def __init__(self, sorter: 'MediaSorter'):
        self.sorter = sorter
        self.watcher = DirectoryWatcher(sorter.cfg)
        self.running = False
        self._setup_signals()

    def _setup_signals(self):
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

    def stop(self, *args):
        if self.running:
            self.running = False
            print("\n🛑 Stopping watch mode...")

    def start(self):
        self.running = True
        print(f"👁️  Watch mode started. Press Ctrl+C to stop.")
        print("\n🚀 Performing initial sort...")
        self.sorter.process_source_directory()
        print(f"✅ Initial sort complete. Now watching for changes...")
        self.watcher._scan()
        self._loop()

    def _loop(self):
        while self.running:
            if self.watcher.check_for_changes():
                print(f"🔄 Changes detected! Starting processing...")
                self.sorter.process_source_directory()
                print(f"✅ Processing complete. Next check in {self.sorter.cfg.WATCH_INTERVAL // 60} minutes.")
            
            print(f"⏰ {datetime.now().strftime('%H:%M:%S')} - No changes. Checking again in {self.sorter.cfg.WATCH_INTERVAL // 60} min. (Ctrl+C to stop)")
            for _ in range(self.sorter.cfg.WATCH_INTERVAL):
                if not self.running: break
                sleep(1)

class MediaSorter:
    # <<< MODIFIED: `fr` and `cleanup_in_place` are now passed in
    def __init__(self, cfg: Config, dry: bool, fr: bool, cleanup_in_place: bool):
        self.cfg, self.dry, self.fr, self.cleanup_in_place = cfg, dry, fr, cleanup_in_place
        self.classifier = MediaClassifier(APIClient(cfg))
        self.fm = FileManager(cfg, dry)
        self.stats = {k: 0 for k in ['processed','movies','tv','anime_movies','anime_series','french_movies','unknown','errors']}
    
    def setup_logging(self): logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", handlers=[logging.FileHandler(self.cfg.LOG_FILE), logging.StreamHandler(sys.stdout)])
    def ensure_target_dirs(self) -> bool:
        if self.cleanup_in_place: return True # No external dirs needed
        dirs_to_check = [self.cfg.MOVIES_DIR, self.cfg.TV_SHOWS_DIR, self.cfg.ANIME_MOVIES_DIR, self.cfg.ANIME_SERIES_DIR]
        if self.fr: dirs_to_check.append(self.cfg.FRENCH_MOVIES_DIR)
        return all(self.fm.ensure_dir(d) for d in dirs_to_check)
    
    # <<< NEW: This logic is ported directly from the backend
    def cleanup_empty_dirs(self, path: Path):
        if self.dry:
            print("-> Dry Run: Skipping cleanup of empty directories.")
            return
        print("\n🧹 Sweeping for empty directories...")
        for dirpath, _, _ in os.walk(path, topdown=False):
            # Do not attempt to remove the root source directory itself
            if Path(dirpath).resolve() == path.resolve():
                continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
                    print(f"-> Removed empty directory: {dirpath}")
            except OSError as e:
                logging.error(f"Error removing directory {dirpath}: {e}")

    # <<< MODIFIED: sort_item now processes a file group, not a folder
    def sort_item(self, item: Path):
        # We only process primary media files. Sidecars are handled with them.
        if item.suffix.lower() in self.cfg.SIDECAR_EXTENSIONS:
            return

        # Determine the name to use for classification.
        # If the parent is the source dir, use the filename. Otherwise, use the parent folder's name.
        name_to_classify = item.parent.name if item.parent != self.cfg.SOURCE_DIR else item.stem
        
        print(f"\n🔍 Processing File: {item.name}")
        info = self.classifier.classify_media(name_to_classify, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
        folder_name = info.get_folder_name()
        print(f"🏷️  Class: {info.media_type.value} | Title: '{folder_name}'")

        s, m_type, success = self.stats, info.media_type, False
        if m_type == MediaType.UNKNOWN: s['unknown'] += 1; return

        # Find all associated sidecar files to move with the primary file
        files_to_move = [item] + self.fm._find_sidecar_files(item)
        if len(files_to_move) > 1:
            print(f"-> Found {len(files_to_move) - 1} sidecar file(s) to move with '{item.name}'.")

        base_dir = None
        if self.cleanup_in_place:
            base_dir = self.cfg.SOURCE_DIR
        else:
            if m_type == MediaType.MOVIE: base_dir = self.cfg.MOVIES_DIR
            elif m_type == MediaType.TV_SERIES: base_dir = self.cfg.TV_SHOWS_DIR
            elif m_type == MediaType.ANIME_MOVIE: base_dir = self.cfg.ANIME_MOVIES_DIR
            elif m_type == MediaType.ANIME_SERIES: base_dir = self.cfg.ANIME_SERIES_DIR
        
        if m_type == MediaType.MOVIE and self.fr and "french" in (info.language or "").lower():
            if not self.cleanup_in_place: base_dir = self.cfg.FRENCH_MOVIES_DIR
        
        if not base_dir:
            print(f"❌ ERROR: Target directory for {m_type.value} is not set."); s['errors'] += 1; return

        if m_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]:
            key = 'anime_movies' if m_type == MediaType.ANIME_MOVIE else 'french_movies' if base_dir == self.cfg.FRENCH_MOVIES_DIR else 'movies'
            dest_folder = base_dir / folder_name
            success = self.fm.move_file_group(files_to_move, dest_folder)
            if success: s[key] += 1
            else: s['errors'] += 1
        
        elif m_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
            key = 'anime_series' if m_type == MediaType.ANIME_SERIES else 'tv'
            season = TitleCleaner.extract_season_info(item.name) or 1
            season_dir = base_dir / folder_name / f"Season {season:02d}"
            success = self.fm.move_file_group(files_to_move, season_dir)
            if success: s[key] += 1
            else: s['errors'] += 1

    # <<< MODIFIED: Complete rewrite to use deep scanning and item-based processing
    def process_source_directory(self):
        if not self.cfg.SOURCE_DIR.exists() or not self.ensure_target_dirs(): return
        
        print("\n🔎 Starting deep scan of source directory...")
        # Scan for all supported and sidecar files initially.
        all_extensions = self.cfg.SUPPORTED_EXTENSIONS.union(self.cfg.SIDECAR_EXTENSIONS)
        all_files_found = [p for ext in all_extensions for p in self.cfg.SOURCE_DIR.glob(f'**/*{ext}') if p.is_file()]

        # We only want to *process* the main media files. Sidecars will be handled by their partners.
        media_files_to_process = [f for f in all_files_found if f.suffix.lower() in self.cfg.SUPPORTED_EXTENSIONS]
        
        if not media_files_to_process:
            print("✨ No primary media files found to process.")
            return

        print(f"📂 Found {len(media_files_to_process)} primary media files to process.")
        for file_path in media_files_to_process:
            self.stats['processed'] += 1
            try:
                self.sort_item(file_path)
            except Exception as e:
                self.stats['errors'] += 1
                logging.error(f"Fatal error processing '{file_path.name}': {e}", exc_info=True)
        
        # Finally, clean up any empty directories left behind.
        self.cleanup_empty_dirs(self.cfg.SOURCE_DIR)
        self.print_summary()

    def start_watch_mode(self): WatchModeManager(self).start()
    def print_summary(self):
        print(f"\n{'='*50}\n📊 PROCESSING SUMMARY\n{'='*50}")
        for k, v in self.stats.items(): print(f"{k.replace('_',' ').title():<15}: {v}")
        print(f"{'='*50}"); logging.info(f"Processing run complete. Stats: {self.stats}")

def main():
    parser = argparse.ArgumentParser(description="SortMeDown Media Sorter", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without moving files.")
    parser.add_argument("--fr", action="store_true", help="Enable sorting of French-language movies to a separate directory.")
    # <<< NEW: Added cleanup argument
    parser.add_argument("--cleanup-in-place", action="store_true", help="Sort and rename files within the source directory, without moving them to libraries.")
    parser.add_argument("--watch", action="store_true", help="Monitor source directory for new files and sort them automatically.")
    parser.add_argument("--watch-interval", type=int, default=15, metavar="MIN", help="Watch interval in minutes (default: 15).")
    parser.add_argument("--version", action="version", version="SortMeDown Media Sorter 4.0.0")
    args = parser.parse_args()
    
    cfg = Config()
    cfg.WATCH_INTERVAL = args.watch_interval * 60
    
    if not cfg.validate():
        sys.exit("❌ Config validation failed. Please check your paths and API key.")
        
    sorter = MediaSorter(cfg, dry=args.dry_run, fr=args.fr, cleanup_in_place=args.cleanup_in_place)
    sorter.setup_logging()
    
    print(ASCII_ART)
    if args.dry_run: print("🧪 DRY RUN MODE - No files will be moved.")
    if args.fr: print("🔵⚪🔴 French Sauce is ENABLED.")
    if args.cleanup_in_place: print("🧹 CLEANUP IN-PLACE MODE - Files will be sorted within the source directory.")

    try:
        if args.watch:
            if args.cleanup_in_place:
                print("❌ ERROR: --watch and --cleanup-in-place modes are mutually exclusive.")
                sys.exit(1)
            sorter.start_watch_mode()
        else:
            sorter.process_source_directory()
    except KeyboardInterrupt:
        print("\n⏹️  Operation cancelled by user.")
    except Exception as e:
        logging.error(f"A fatal error occurred in main execution: {e}", exc_info=True)
        sys.exit(f"❌ A fatal error occurred: {e}")

if __name__ == "__main__":
    main()
