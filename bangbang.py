#!/usr/bin/env python3
"""
SortMeDown a Media Sorter Script
==================

Automatically sorts media files and folders (movies, TV shows, anime) into organized directories
based on metadata from OMDb API and AniList API.

Features:
- Processes both folders and individual files in the source directory
- Automatic detection of movies, TV series, and anime
- Multi-language support (English/French movies)
- Season-based organization for TV shows
- Dry-run mode for safe testing
- Comprehensive logging
- Duplicate detection and handling
- Integrated watchdog for continuous monitoring
- Dedicated French movies folder if run with --fr argument
- Revised Logic with less bias (no longer reling on "english" as primary key word)
- Auto Cleaning processor and custom strings input

python bangbang.py                                  # One-time sorting (original behavior)
python bangbang.py --fr                             # French Sauce: separates French movies
python bangbang.py --dry-run                        # Preview mode
python bangbang.py --version                        # Show version
python bangbang.py --watch                          # Standard watch mode (15 minute intervals)
python bangbang.py --watch --watch-interval 30      # Custom interval (30 minutes)
python bangbang.py --watch --dry-run                # Watch mode with dry-run (perfect for testing)


Version: 3.1.1


"""

from pathlib import Path
import re
import shutil
import requests
import logging
import argparse
from time import sleep
from typing import Optional, Dict, Any, Set
import json
import signal
import sys
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

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
#        ░      ░ ░     ░   Media Sorter Script  ░      ░  ░      ░        ░ ░      ░      3.1.1 ░ 
#                                                               ░                                    

     Available Arguments : --dry-run  --fr   -- watch   --watch --watch-interval 30  --version
      
                                                                      
"""


class MediaType(Enum):
    """Enumeration of supported media types."""
    MOVIE = "movie"
    TV_SERIES = "series"
    ANIME_MOVIE = "anime_movie"
    ANIME_SERIES = "anime_series"
    UNKNOWN = "unknown"


@dataclass
class MediaInfo:
     """Data class to hold media information."""
    title: str; year: Optional[str]; media_type: MediaType; language: Optional[str]; genre: Optional[str]; season: Optional[int] = None
    def get_folder_name(self) -> str:
        if not self.title: return "Unknown"
        folder_title = re.sub(r'[<>:"/\\|?*]', '', self.title).strip()
        if self.year: return f"{folder_title} ({self.year})"
        return folder_title



class Config:
    """Configuration class to hold all directory paths and API settings."""
    
    def __init__(self):
        # Directory Configuration
        self.SOURCE_DIR = Path("C:/download/unsorted")           # Replace with your media download directory
        self.MOVIES_DIR = Path("D:/Movies")                      # Replace with your Movies directory
        self.FRENCH_MOVIES_DIR = Path("D:/Films")                # Replace with your Movies directory =>> only needed if you intend the --f argument
        self.TV_SHOWS_DIR = Path("D:/Series")                    # Replace with your TV Shows directory
        self.ANIME_MOVIES_DIR = Path("D:/Anime_Movies")          # Replace with your Anime Movies directory
        self.ANIME_SERIES_DIR = Path("D:/Anime_TV")              # Replace with your Anime Series directory
        # Only files with these extensions will be processed.
        self.SUPPORTED_EXTENSIONS = {
            '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v',
            '.mpg', '.mpeg', '.3gp', '.ogv', '.ts', '.m2ts', '.mts' , '.sub'
        }
        self.CUSTOM_STRINGS_TO_REMOVE = {'FRENCH', 'TRUEFRENCH', 'VOSTFR', 'MULTI', 'SUBFRENCH'} # Custom user definable strings to clean
        # API Configuration
        self.OMDB_API_KEY = "yourkey"  # Replace with your actual API key from www.omdbapi.com
        self.OMDB_URL = "http://www.omdbapi.com/"
        self.ANILIST_URL = "https://graphql.anilist.co"
        # Logging Configuration
        self.LOG_FILE = "C:/download/unsorted/sortmedown.log"  #change where ever you want it
        # Processing Configuration
        self.REQUEST_DELAY = 1.0  # Delay between API requests (seconds)
        self.MAX_RETRIES = 3
        # Watch Mode Configuration
        self.WATCH_INTERVAL = 15 * 60  # 15 minutes in seconds
        self.COOLDOWN_PERIOD = 5 * 60  # 5 minutes cooldown after processing
        
    def validate(self) -> bool:
        """Validates critical configuration settings."""
        if not self.OMDB_API_KEY or self.OMDB_API_KEY == "yourkey": #check if you forgot to change this value with your own key
            logging.warning("OMDb API key not configured")
            return False
        if not self.SOURCE_DIR.exists():
            logging.error(f"Source directory not found: {self.SOURCE_DIR}")
            return False
        return True

      
      
class TitleCleaner:
    """A unified, intelligent utility for cleaning media titles for API searches."""
    METADATA_BREAKPOINT_PATTERN = re.compile(
        r'('
        r'\s[\(\[]?\d{4}[\)\]]?\b'         # Year, e.g., (2023) or 2023
        r'|\s[Ss]\d{1,2}[Ee]\d{1,2}\b'     # Season/Episode, e.g., S01E02
        # Add a pattern to catch standalone season indicators like "S02"
        r'|\s[Ss]\d{1,2}\b'                # Season only, e.g., S02
        r'|\sSeason\s\d{1,2}\b'           # Season Word, e.g., Season 01
        r'|\s\d{3,4}p\b'                  # Resolution, e.g., 1080p
        r'|\s(WEBRip|BluRay|BDRip|DVDRip|HDRip|WEB-DL|HDTV)\b' # Quality
        r'|\s(x264|x265|H\.?264|H\.?265|HEVC|AVC)\b' # Codec
        r')', re.IGNORECASE
    )

    @classmethod
    def clean_for_search(cls, name: str, custom_strings_to_remove: Set[str]) -> str:
        """
        Intelligently cleans a filename for API search.
        It isolates the title, removes custom junk words, and then stops at metadata.
        """
        # First, replace dots and underscores with spaces for better parsing
        name_with_spaces = re.sub(r'[\._]', ' ', name)
        
        # Remove custom strings first
        temp_title = name_with_spaces
        for s in custom_strings_to_remove:
            pattern = r'\b' + re.escape(s) + r'\b'
            temp_title = re.sub(pattern, ' ', temp_title, flags=re.IGNORECASE)

        # Now, find the metadata breakpoint in the already cleaned title
        match = cls.METADATA_BREAKPOINT_PATTERN.search(temp_title)
        
        # If metadata is found, take everything before it.
        title_part = temp_title[:match.start()] if match else temp_title

        # Remove any release group in brackets, e.g., [SubsPlease]
        cleaned_title = re.sub(r'\[[^\]]+\]', '', title_part)
        
        # Final cleanup of multiple spaces and stripping whitespace
        cleaned_title = re.sub(r'\s+', ' ', cleaned_title).strip()
        
        return cleaned_title

    @classmethod
    def extract_season_info(cls, filename: str) -> Optional[int]:
        # This method is unchanged and correct
        patterns = [r'[Ss](\d{1,2})[Ee]\d{1,2}', r'Season[ _-]?(\d{1,2})', r'[Ss](\d{1,2})']
        for p in patterns:
            if m:=re.search(p, filename, re.IGNORECASE): return int(m.group(1))
        return None

        
class APIClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'SortMeDown/3.1.1'})
    
    def query_omdb(self, title: str) -> Optional[Dict[str, Any]]:
        # Logic remains the same
        params = {"t": title, "apikey": self.config.OMDB_API_KEY}
        try:
            response = self.session.get(self.config.OMDB_URL, params=params, timeout=10)
            data = response.json()
            if data.get("Response") != "False": return data
            search_params = {"s": title, "apikey": self.config.OMDB_API_KEY}
            search_response = self.session.get(self.config.OMDB_URL, params=search_params, timeout=10)
            search_data = search_response.json()
            if "Search" in search_data and search_data["Search"]:
                id_params = {"i": search_data["Search"][0]["imdbID"], "apikey": self.config.OMDB_API_KEY}
                id_response = self.session.get(self.config.OMDB_URL, params=id_params, timeout=10)
                return id_response.json()
        except requests.RequestException as e:
            logging.error(f"OMDb API request failed for '{title}': {e}")
        return None
    
    def query_anilist(self, title: str) -> Optional[Dict[str, Any]]:
        # Logic remains the same
        query = '''query ($search: String) { Media(search: $search, type: ANIME) { title { romaji english native } format, genres, season, seasonYear, episodes } }'''
        payload = {"query": query, "variables": {"search": title}}
        try:
            response = self.session.post(self.config.ANILIST_URL, json=payload, timeout=10)
            media = response.json().get("data", {}).get("Media")
            if media: logging.info(f"AniList found match for: {title}"); return media
        except requests.RequestException as e:
            logging.error(f"AniList API request failed for '{title}': {e}")
        return None


class MediaClassifier:
    """Classifies media based on API responses."""
    def __init__(self, api_client: APIClient):
        self.api_client = api_client
     
    def classify_media(self, name: str, custom_strings_to_remove: Set[str]) -> MediaInfo:
        """Classifies media from a folder or file name using a unified cleaner."""
        # The cleaner now requires the set of custom strings
        clean_name = TitleCleaner.clean_for_search(name, custom_strings_to_remove)
        
        logging.info(f"Classifying: '{name}' -> Clean search: '{clean_name}'")
        
        if not clean_name:
            logging.warning(f"Could not extract a clean name from '{name}'. Skipping.")
            return MediaInfo(title=name, year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)

        anilist_data = self.api_client.query_anilist(clean_name)
        sleep(self.api_client.config.REQUEST_DELAY)
        omdb_data = self.api_client.query_omdb(clean_name)
        
        if anilist_data and omdb_data: return self._resolve_conflicting_results(anilist_data, omdb_data)
        elif anilist_data: return self._classify_from_anilist(anilist_data)
        elif omdb_data: return self._classify_from_omdb(omdb_data)
        
        logging.warning(f"No API results found for: {clean_name}")
        return MediaInfo(title=name, year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)

    def _resolve_conflicting_results(self, anilist_data: Dict[str, Any], omdb_data: Dict[str, Any]) -> MediaInfo:
        omdb_genre = omdb_data.get("Genre", "").lower()
        omdb_country = omdb_data.get("Country", "").lower()
        if "animation" not in omdb_genre and "anime" not in omdb_genre: return self._classify_from_omdb(omdb_data)
        is_western = any(c in omdb_country for c in ["usa", "uk", "canada", "france", "germany", "spain"])
        if is_western and "japan" not in omdb_country: return self._classify_from_omdb(omdb_data)
        return self._classify_from_anilist(anilist_data)
    
    def _classify_from_anilist(self, data: Dict[str, Any]) -> MediaInfo:
        format_type = data.get("format", "").upper()
        media_type = MediaType.UNKNOWN
        if format_type == "MOVIE": media_type = MediaType.ANIME_MOVIE
        elif format_type in ["TV", "TV_SHORT", "ONA", "OVA", "SPECIAL"]: media_type = MediaType.ANIME_SERIES
        title = data.get('title', {}).get('english') or data.get('title', {}).get('romaji')
        return MediaInfo(title=title, year=str(data.get("seasonYear", "")), media_type=media_type, language="Japanese", genre=", ".join(data.get("genres", [])))
    
    def _classify_from_omdb(self, data: Dict[str, Any]) -> MediaInfo:
        type_ = data.get("Type", "").lower()
        media_type = MediaType.UNKNOWN
        if type_ == "movie": media_type = MediaType.MOVIE
        elif type_ in ["series", "tv series"]: media_type = MediaType.TV_SERIES
        year_str = data.get("Year", "")
        year = year_str.split('–')[0] if year_str else None
        return MediaInfo(title=data.get("Title"), year=year, media_type=media_type, language=data.get("Language", ""), genre=data.get("Genre", ""))



class FileManager:
    """Handles file and folder operations with clear, distinct methods."""
    def __init__(self, cfg: Config, dry: bool):
        self.cfg = cfg
        self.dry = dry

    def ensure_dir(self, p: Path) -> bool:
        if not p.exists():
            if self.dry:
                print(f"📁 DRY RUN: Would create dir '{p}'")
            else:
                try:
                    p.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    print(f"❌ ERROR: Could not create directory '{p}': {e}")
                    logging.error(f"Failed to create directory '{p}': {e}")
                    return False
        return True

    def move_file(self, src_file: Path, dest_dir: Path) -> bool:
        """Moves a single source file into a destination directory."""
        if not self.ensure_dir(dest_dir):
            return False
        
        target = dest_dir / src_file.name
        if target.exists():
            print(f"⚠️  SKIPPED: File '{target.name}' already exists in '{dest_dir.name}'.")
            return False
            
        if self.dry:
            print(f"🧪 DRY RUN: Would move file '{src_file.name}' → '{dest_dir}'")
            return True
            
        try:
            shutil.move(str(src_file), str(target))
            print(f"✅ Moved file: '{src_file.name}' → '{dest_dir}'")
            return True
        except Exception as e:
            print(f"❌ ERROR moving file '{src_file.name}': {e}")
            logging.error(f"Error moving file '{src_file}' to '{dest_dir}': {e}")
            return False

    def move_folder(self, src_folder: Path, dest_parent_dir: Path, new_name: str) -> bool:
        """Moves a source folder to a parent directory and renames it."""
        target = dest_parent_dir / new_name
        if target.exists():
            print(f"⚠️  SKIPPED: Folder '{target.name}' already exists in '{dest_parent_dir}'.")
            return False

        if self.dry:
            print(f"🧪 DRY RUN: Would move folder '{src_folder.name}' → '{target}'")
            return True
            
        try:
            shutil.move(str(src_folder), str(target))
            print(f"✅ Moved folder: '{src_folder.name}' → '{target}'")
            return True
        except Exception as e:
            print(f"❌ ERROR moving folder '{src_folder.name}': {e}")
            logging.error(f"Error moving folder '{src_folder}' to '{target}': {e}")
            return False


class DirectoryWatcher:
    def __init__(self, config: Config): self.config, self.last_mtime = config, 0; self._scan()
    def _scan(self):
        if self.config.SOURCE_DIR.exists(): self.last_mtime = self.config.SOURCE_DIR.stat().st_mtime
    def check_for_changes(self) -> bool:
        if not self.config.SOURCE_DIR.exists(): return False
        mtime = self.config.SOURCE_DIR.stat().st_mtime
        if mtime > self.last_mtime: self.last_mtime = mtime; return True
        return False

class WatchModeManager:
    def __init__(self, sorter: 'MediaSorter'):
        self.sorter = sorter
        self.watcher = DirectoryWatcher(sorter.cfg) # <-- The change is here
        self.running = False
        self._setup_signals()

    def _setup_signals(self):
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

    def stop(self, *args):
        if self.running:
            self.running = False
            print("\n🛑 Stopping watch mode...")
            if self.thread:
                self.thread.join(timeout=5)

    def start(self):
        self.running = True
        print(f"👁️  Watch mode started. Press Ctrl+C to stop.")
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        try:
            while self.running:
                sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def _loop(self):
        while self.running:
            if self.watcher.check_for_changes():
                print(f"🔄 Changes detected! Starting processing...")
                self.sorter.process_source_directory()
                print(f"✅ Processing complete. Next check in {self.sorter.cfg.WATCH_INTERVAL // 60} minutes.")
            else:
                print(f"⏰ {datetime.now().strftime('%H:%M:%S')} - No changes detected. Press Ctrl+C to stop.")
            for _ in range(self.sorter.cfg.WATCH_INTERVAL):
                if not self.running:
                    break
                sleep(1)


class MediaSorter:
    def __init__(self, cfg: Config, dry: bool, fr: bool):
        self.cfg, self.dry, self.fr = cfg, dry, fr; 
        self.classifier = MediaClassifier(APIClient(cfg)); self.fm = FileManager(cfg, dry); 
        self.stats = {k: 0 for k in ['processed','movies','tv','anime_movies','anime_series','french_movies','unknown','errors']}
    
    def setup_logging(self): logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", handlers=[logging.FileHandler(self.cfg.LOG_FILE), logging.StreamHandler()])
    def ensure_target_dirs(self) -> bool: return all(self.fm.ensure_dir(d) for d in [self.cfg.MOVIES_DIR, self.cfg.FRENCH_MOVIES_DIR, self.cfg.TV_SHOWS_DIR, self.cfg.ANIME_MOVIES_DIR, self.cfg.ANIME_SERIES_DIR])
    
    ### CLEARER ROUTING LOGIC USING DEDICATED FILEMANAGER METHODS ###
    def sort_item(self, item: Path):
        is_folder = item.is_dir()
        name_to_classify = item.name if is_folder else item.stem
        
        print(f"\n🔍 Processing {'Folder' if is_folder else 'File'}: {item.name}")
        info = self.classifier.classify_media(name_to_classify, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
        folder_name = info.get_folder_name()
        print(f"🏷️  Class: {info.media_type.value} | Title: '{folder_name}'")

        s, m_type, success = self.stats, info.media_type, False
        if m_type == MediaType.UNKNOWN: s['unknown'] += 1; return

        if m_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]:
            dest_dir = self.cfg.ANIME_MOVIES_DIR if m_type == MediaType.ANIME_MOVIE else self.cfg.MOVIES_DIR
            if m_type == MediaType.MOVIE and self.fr and "french" in (info.language or "").lower():
                dest_dir = self.cfg.FRENCH_MOVIES_DIR
                s['french_movies'] += 1

            if is_folder: success = self.fm.move_folder(item, dest_dir, folder_name)
            else: success = self.fm.move_file(item, dest_dir / folder_name)

            if m_type == MediaType.MOVIE: s['movies'] += 1
            else: s['anime_movies'] += 1

        elif m_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
            season = TitleCleaner.extract_season_info(item.name) or 1
            base_dir = self.cfg.ANIME_SERIES_DIR if m_type == MediaType.ANIME_SERIES else self.cfg.TV_SHOWS_DIR
            show_dir = base_dir / folder_name
            season_dir = show_dir / f"Season {season:02d}"
            
            if is_folder:
                # Move all files from the source folder to the new season folder
                all_files_moved = [self.fm.move_file(f, season_dir) for f in list(item.iterdir()) if f.is_file()]
                success = all(all_files_moved)
                if not self.dry and success and all_files_moved: # Only remove if files were actually moved
                    try: item.rmdir()
                    except Exception: pass # Fails if not empty, which is fine
            else: # is a file
                success = self.fm.move_file(item, season_dir)

            if m_type == MediaType.ANIME_SERIES: s['anime_series'] += 1
            else: s['tv'] += 1
            
        if not success: s['errors'] += 1

    #
    def process_source_directory(self):
        if not self.cfg.SOURCE_DIR.exists() or not self.ensure_target_dirs(): return
        
        items_to_process = []
        for item in self.cfg.SOURCE_DIR.iterdir():
            if item.is_dir():
                items_to_process.append(item)
            elif item.is_file() and item.suffix.lower() in self.cfg.SUPPORTED_EXTENSIONS:
                items_to_process.append(item)
            else:
                logging.info(f"Skipping unsupported file type: {item.name}")
        
        if not items_to_process:
            print("✨ No supported files or folders found to process.")
            return

        print(f"📂 Found {len(items_to_process)} items to process.")
        for item in items_to_process:
            self.stats['processed'] += 1
            try:
                self.sort_item(item)
            except Exception as e:
                self.stats['errors'] += 1
                logging.error(f"Fatal error processing '{item.name}': {e}", exc_info=True)
        self.print_summary()

    def start_watch_mode(self): WatchModeManager(self).start()
    def print_summary(self):
        print(f"\n{'='*50}\n📊 SORTING SUMMARY\n{'='*50}")
        for k, v in self.stats.items(): print(f"{k.replace('_',' ').title():<15}: {v}")
        print(f"{'='*50}"); logging.info(f"Sorting done. Stats: {self.stats}")

def main():
    parser = argparse.ArgumentParser(description="Sort media files and folders.", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Preview actions."); parser.add_argument("--fr", action="store_true", help="Sort French movies separately."); parser.add_argument("--watch", action="store_true", help="Monitor source directory."); parser.add_argument("--watch-interval", type=int, default=15, metavar="MIN", help="Watch interval in minutes (default: 15)."); parser.add_argument("--version", action="version", version="SortMeDown a Media Sorter 3.1.1")
    args = parser.parse_args()
    cfg = Config(); cfg.WATCH_INTERVAL = args.watch_interval * 60
    if not cfg.validate(): sys.exit("❌ Config validation failed.")
    sorter = MediaSorter(cfg, dry=args.dry_run, fr=args.fr); sorter.setup_logging()
    print(ASCII_ART)
    if args.dry_run: print("🧪 DRY RUN MODE - No files will be moved.")
    if args.fr: print("🔵⚪🔴 French Sauce is ENABLED.")
    try:
        if args.watch: sorter.start_watch_mode()
        else: sorter.process_source_directory()
    except KeyboardInterrupt: print("\n⏹️  Operation cancelled.")
    except Exception as e: logging.error(f"Fatal error: {e}", exc_info=True); sys.exit(f"❌ Fatal error: {e}")

if __name__ == "__main__":
    sys.exit(main())
