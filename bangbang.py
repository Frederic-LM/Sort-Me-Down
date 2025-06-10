#!/usr/bin/env python3
"""
SortmeDown Media Sorter Script
==================

Automatically sorts media files (movies, TV shows, anime) into organized directories
based on metadata from OMDb API and AniList API.

Features:
- Automatic detection of movies, TV series, and Anime & Anime serie
- Season-based organization for TV shows
- Dry-run mode for safe testing
- Comprehensive logging
- Duplicate detection and handling
- Intergrated watchdog
- Dual Api logic for better detection

python media_sorter.py                # One-time sorting (original behavior)
python media_sorter.py --dry-run      # Preview mode
python media_sorter.py --version      # Show version
python media_sorter.py --watch                          # Standard watch mode (15 minute intervals)
python media_sorter.py --watch --watch-interval 30      # Custom interval (30 minutes)
python media_sorter.py --watch --dry-run                # Watch mode with dry-run (perfect for testing)


Version: 2.61i


"""

from pathlib import Path
import re
import shutil
import requests
import logging
import argparse
from time import sleep
from typing import Optional, Tuple, Dict, Any, Set
import json
import signal
import sys
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

# ASCII Art Logo
ASCII_ART = """

  ██████  ▒█████   ██▀███  ▄▄▄█████▓ ███▄ ▄███▓▓█████ ▓█████▄  ▒█████   █     █░███▄    █ 
▒██    ▒ ▒██▒  ██▒▓██ ▒ ██▒▓  ██▒ ▓▒▓██▒▀█▀ ██▒▓█   ▀ ▒██▀ ██▌▒██▒  ██▒▓█░ █ ░█░██ ▀█   █ 
░ ▓██▄   ▒██░  ██▒▓██ ░▄█ ▒▒ ▓██░ ▒░▓██    ▓██░▒███   ░██   █▌▒██░  ██▒▒█░ █ ░█▓██  ▀█ ██▒
  ▒   ██▒▒██   ██░▒██▀▀█▄  ░ ▓██▓ ░ ▒██    ▒██ ▒▓█  ▄ ░▓█▄   ▌▒██   ██░░█░ █ ░█▓██▒  ▐▌██▒
▒██████▒▒░ ████▓▒░░██▓ ▒██▒  ▒██▒ ░ ▒██▒   ░██▒░▒████▒░▒████▓ ░ ████▓▒░░░██▒██▓▒██░   ▓██░
▒ ▒▓▒ ▒ ░░ ▒░▒░▒░ ░ ▒▓ ░▒▓░  ▒ ░░   ░ ▒░   ░  ░░░ ▒░ ░ ▒▒▓  ▒ ░ ▒░▒░▒░ ░ ▓░▒ ▒ ░ ▒░   ▒ ▒ 
░ ░▒  ░ ░  ░ ▒ ▒░   ░▒ ░ ▒░    ░    ░  ░      ░ ░ ░  ░ ░ ▒  ▒   ░ ▒ ▒░   ▒ ░ ░ ░ ░░   ░ ▒░
░  ░  ░  ░ ░ ░ ▒    ░░   ░   ░      ░      ░      ░    ░ ░  ░ ░ ░ ░ ▒    ░   ░    ░   ░ ░ 
      ░      ░ ░     ░                     ░      ░  ░   ░        ░ ░      ░        2.6i░ 
                                                       ░                                  
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
    title: str
    year: Optional[str]
    media_type: MediaType
    language: Optional[str]
    genre: Optional[str]
    season: Optional[int] = None


class Config:
    """Configuration class to hold all directory paths and API settings."""
    
    def __init__(self):
        # Directory Configuration
        self.SOURCE_DIR = Path("C:/temp")          # Replace with your media download directory
        self.MOVIES_DIR = Path("B:/Movies")        # Replace with your Movies directory
        self.TV_SHOWS_DIR = Path("B:/Series")      # Replace with your TV Shows directory
        self.ANIME_MOVIES_DIR = Path("B:/Anime/Anime (Film)") # Replace with your Anime Movies directory
        self.ANIME_SERIES_DIR = Path("B:/Anime/Anime (Serie)")# Replace with your Anime Series directory
        
        # API Configuration
        self.OMDB_API_KEY = "0000000"  # Replace with your actual omdbapi API key
        self.OMDB_URL = "http://www.omdbapi.com/"
        self.ANILIST_URL = "https://graphql.anilist.co"
        
        # Logging Configuration
        self.LOG_FILE = "F:/media_sorter.log"
        
        # Processing Configuration
        self.REQUEST_DELAY = 1.0  # Delay between API requests (seconds)
        self.MAX_RETRIES = 3
        
        # Watch Mode Configuration
        self.WATCH_INTERVAL = 15 * 60  # 15 minutes in seconds
        self.COOLDOWN_PERIOD = 5 * 60  # 5 minutes cooldown after processing
        
    def validate(self) -> bool:
        """Validate configuration settings."""
        if not self.OMDB_API_KEY:
            logging.warning("OMDb API key not properly configured")
            return False
        
        if not self.SOURCE_DIR.exists():
            logging.error(f"Source directory does not exist: {self.SOURCE_DIR}")
            return False
            
        return True


class TitleCleaner:
    """Utility class for cleaning and normalizing media titles."""
    
    # Regex patterns for cleaning titles
    PATTERNS = {
        'dots_underscores': r'[\._]',
        'year_brackets': r'\s*[\(\[]\d{4}[\)\]]',
        'season_episode': r'\s*[Ss]\d{1,2}[Ee]?\d{0,2}',
        'season_word': r'\s*Season\s*\d{1,2}',
        'resolution': r'\s*\d{3,4}p',
        'quality': r'\s*(WEBRip|BluRay|BDRip|DVDRip|HDRip|CAMRip|HDTV|WEB-DL)',
        'channels': r'\s*\d+CH',
        'codec': r'\s*(x264|x265|H\.?264|H\.?265|HEVC|AVC)',
        'release_group': r'\s*-[A-Z]+$',
        'multiple_spaces': r'\s+',
    }
    
    @classmethod
    def clean_for_search(cls, title: str) -> str:
        """
        Clean title for API searches - removes everything including year.
        
        Args:
            title: Raw title string
            
        Returns:
            Cleaned title suitable for API searches
        """
        cleaned = title
        
        # Apply all cleaning patterns except year extraction
        for pattern_name, pattern in cls.PATTERNS.items():
            if pattern_name == 'multiple_spaces':
                cleaned = re.sub(pattern, ' ', cleaned)
            else:
                cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        return cleaned.strip()
    
    @classmethod
    def clean_for_folder(cls, title: str) -> str:
        """
        Clean title for folder naming - preserves year but removes other metadata.
        
        Args:
            title: Raw title string
            
        Returns:
            Cleaned title suitable for folder names
        """
        # Extract and preserve year
        year_match = re.search(r'\((\d{4})\)', title)
        year = f" ({year_match.group(1)})" if year_match else ""
        
        # Clean the title
        cleaned = title
        for pattern_name, pattern in cls.PATTERNS.items():
            if pattern_name == 'multiple_spaces':
                cleaned = re.sub(pattern, ' ', cleaned)
            else:
                cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        cleaned = cleaned.strip()
        return cleaned + year
    
    @classmethod
    def extract_season_info(cls, filename: str) -> Optional[int]:
        """
        Extract season number from filename.
        
        Args:
            filename: Name of file or folder
            
        Returns:
            Season number if found, otherwise None
        """
        # Try different season patterns
        patterns = [
            r'[Ss](\d{1,2})[Ee]\d{1,2}',  # S01E01 format
            r'Season[ _-]?(\d{1,2})',      # Season 1 format
            r'[Ss](\d{1,2})',             # S01 format
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return None


class APIClient:
    """Client for interacting with external APIs."""
    
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'MediaSorter/2.0 (https://github.com/user/media-sorter)'
        })
    
    def query_omdb(self, title: str) -> Optional[Dict[str, Any]]:
        """
        Query OMDb API for movie/TV show information.
        
        Args:
            title: Title to search for
            
        Returns:
            API response data or None if not found
        """
        params = {"t": title, "apikey": self.config.OMDB_API_KEY}
        
        try:
            response = self.session.get(self.config.OMDB_URL, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get("Response") != "False":
                logging.info(f"OMDb found exact match for: {title}")
                return data
            
            # Try search if exact match fails
            search_params = {"s": title, "apikey": self.config.OMDB_API_KEY}
            search_response = self.session.get(
                self.config.OMDB_URL, 
                params=search_params, 
                timeout=10
            )
            search_response.raise_for_status()
            
            search_data = search_response.json()
            if "Search" in search_data and search_data["Search"]:
                best_match = search_data["Search"][0]["Title"]
                logging.info(f"OMDb using search result: {best_match} for query: {title}")
                return self.query_omdb(best_match)
                
        except requests.RequestException as e:
            logging.error(f"OMDb API request failed for '{title}': {e}")
        except Exception as e:
            logging.error(f"OMDb query error for '{title}': {e}")
        
        return None
    
    def query_anilist(self, title: str) -> Optional[Dict[str, Any]]:
        """
        Query AniList API for anime information.
        
        Args:
            title: Title to search for
            
        Returns:
            API response data or None if not found
        """
        query = '''
        query ($search: String) {
          Media(search: $search, type: ANIME) {
            title { 
              romaji 
              english 
              native 
            }
            format
            genres
            season
            seasonYear
            episodes
          }
        }
        '''
        
        variables = {"search": title}
        payload = {"query": query, "variables": variables}
        
        try:
            response = self.session.post(
                self.config.ANILIST_URL, 
                json=payload, 
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            media = data.get("data", {}).get("Media")
            if media:
                logging.info(f"AniList found match for: {title}")
                return media
                
        except requests.RequestException as e:
            logging.error(f"AniList API request failed for '{title}': {e}")
        except Exception as e:
            logging.error(f"AniList query error for '{title}': {e}")
        
        return None


class MediaClassifier:
    """Classifies media based on API responses."""
    
    def __init__(self, api_client: APIClient):
        self.api_client = api_client
    
    def classify_media(self, folder_name: str) -> MediaInfo:
        """
        Classify media type based on folder name and API data.
        Now checks both APIs to avoid false anime classifications.
        
        Args:
            folder_name: Name of the media folder
            
        Returns:
            MediaInfo object with classification results
        """
        clean_name = TitleCleaner.clean_for_search(folder_name)
        clean_name_with_year = TitleCleaner.clean_for_folder(folder_name)
        
        logging.info(f"Classifying: {folder_name} -> {clean_name}")
        
        # Query both APIs
        anilist_data = self.api_client.query_anilist(clean_name)
        sleep(self.api_client.config.REQUEST_DELAY)
        omdb_data = self.api_client.query_omdb(clean_name)
        
        # If both APIs have results, we need to decide which is more accurate
        if anilist_data and omdb_data:
            return self._resolve_conflicting_results(anilist_data, omdb_data, clean_name_with_year)
        
        # If only AniList has results
        elif anilist_data:
            logging.info(f"Only AniList found results for: {clean_name}")
            return self._classify_from_anilist(anilist_data, clean_name_with_year)
        
        # If only OMDb has results
        elif omdb_data:
            logging.info(f"Only OMDb found results for: {clean_name}")
            return self._classify_from_omdb(omdb_data, clean_name_with_year)
        
        # No results from either API
        logging.warning(f"No API results found for: {clean_name}")
        return MediaInfo(
            title=clean_name_with_year,
            year=None,
            media_type=MediaType.UNKNOWN,
            language=None,
            genre=None
        )

    def _resolve_conflicting_results(self, anilist_data: Dict[str, Any], 
                                   omdb_data: Dict[str, Any], title: str) -> MediaInfo:
        """
        Resolve conflicts when both AniList and OMDb return results.
        Prioritizes OMDb for non-Japanese content.
        
        Args:
            anilist_data: Data from AniList API
            omdb_data: Data from OMDb API
            title: Cleaned title for the media
            
        Returns:
            MediaInfo with the most appropriate classification
        """
        # Get OMDb metadata
        omdb_language = omdb_data.get("Language", "").lower()
        omdb_country = omdb_data.get("Country", "").lower()
        omdb_genre = omdb_data.get("Genre", "").lower()
        omdb_type = omdb_data.get("Type", "").lower()
        
        # Log the conflict for debugging
        logging.info(f"Resolving API conflict for '{title}':")
        logging.info(f"  OMDb - Type: {omdb_type}, Language: {omdb_language}, Country: {omdb_country}")
        logging.info(f"  AniList - Format: {anilist_data.get('format', 'Unknown')}")
        
        # Strong indicators this is Western content, not anime
        western_indicators = [
            # English-speaking countries with English language
            ("english" in omdb_language and 
             any(country in omdb_country for country in ["usa", "united states", "uk", "united kingdom", "canada", "australia"])),
            
            # English language without Japanese
            ("english" in omdb_language and "japanese" not in omdb_language and "japan" not in omdb_country),
            
            # Specific western countries
            any(country in omdb_country for country in ["usa", "united states", "uk", "united kingdom", "canada"]) and "japan" not in omdb_country,
            
            # Non-animated western content
            (omdb_type in ["series", "movie"] and "animation" not in omdb_genre and "english" in omdb_language)
        ]
        
        # Strong indicators this is actually anime
        anime_indicators = [
            # Japanese language or origin
            "japanese" in omdb_language,
            "japan" in omdb_country and "animation" in omdb_genre,
            
            # AniList format suggests genuine anime
            anilist_data.get("format") in ["TV", "TV_SHORT", "MOVIE", "ONA", "OVA", "SPECIAL"],
        ]
        
        # Count the indicators
        western_score = sum(western_indicators)
        anime_score = sum(anime_indicators)
        
        # Decision logic
        if western_score > anime_score:
            logging.info(f"  Decision: Using OMDb (Western content - Score: W:{western_score} A:{anime_score})")
            return self._classify_from_omdb(omdb_data, title)
        elif anime_score > western_score:
            logging.info(f"  Decision: Using AniList (Anime content - Score: W:{western_score} A:{anime_score})")
            return self._classify_from_anilist(anilist_data, title)
        else:
            # Tie-breaker: prefer OMDb for broader content, but check one more thing
            if anilist_data.get("format") == "MOVIE" and omdb_type == "movie":
                # For movies, if both agree it's a movie, trust the more specific source
                if "animation" in omdb_genre:
                    logging.info(f"  Decision: Using AniList (Both agree on animated movie)")
                    return self._classify_from_anilist(anilist_data, title)
            
            logging.info(f"  Decision: Defaulting to OMDb (Tie-breaker)")
            return self._classify_from_omdb(omdb_data, title)
    
    def _classify_from_anilist(self, data: Dict[str, Any], title: str) -> MediaInfo:
        """Classify media from AniList response."""
        format_type = data.get("format", "").upper()
        
        if format_type == "MOVIE":
            media_type = MediaType.ANIME_MOVIE
        elif format_type in ["TV", "TV_SHORT", "ONA", "OVA", "SPECIAL"]:
            media_type = MediaType.ANIME_SERIES
        else:
            media_type = MediaType.UNKNOWN
        
        return MediaInfo(
            title=title,
            year=str(data.get("seasonYear", "")),
            media_type=media_type,
            language="Japanese",
            genre=", ".join(data.get("genres", []))
        )
    
    def _classify_from_omdb(self, data: Dict[str, Any], title: str) -> MediaInfo:
        """Classify media from OMDb response."""
        type_ = data.get("Type", "").lower()
        language = data.get("Language", "").lower()
        genre = data.get("Genre", "").lower()
        country = data.get("Country", "").lower()
        
        # More precise anime detection for OMDb data
        is_anime = False
        
        # Check multiple indicators for anime
        anime_indicators = [
            # Language indicators
            "japanese" in language,
            "japan" in language,
            
            # Country indicators  
            "japan" in country,
            
            # Genre + country/language combination
            ("animation" in genre and ("japan" in country or "japanese" in language)),
            
            # Explicit anime mention in genre
            "anime" in genre,
            
            # Title-based detection (as fallback)
            any(keyword in title.lower() for keyword in ["anime", "manga"])
        ]
        
        # Only classify as anime if we have strong indicators
        is_anime = any(anime_indicators)
        
        # Classify based on type and anime detection
        if is_anime:
            if type_ == "movie":
                media_type = MediaType.ANIME_MOVIE
            else:
                media_type = MediaType.ANIME_SERIES
        elif type_ == "movie":
            media_type = MediaType.MOVIE
        elif type_ in ["series", "tv series"]:
            media_type = MediaType.TV_SERIES
        else:
            media_type = MediaType.UNKNOWN
        
        return MediaInfo(
            title=title,
            year=data.get("Year", ""),
            media_type=media_type,
            language=data.get("Language", ""),
            genre=data.get("Genre", "")
        )


class FileManager:
    """Handles file and folder operations."""
    
    def __init__(self, config: Config, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
    
    def ensure_directory(self, path: Path) -> bool:
        """
        Ensure directory exists, create if necessary.
        
        Args:
            path: Directory path to ensure
            
        Returns:
            True if directory exists or was created successfully
        """
        if path.exists():
            return True
        
        if self.dry_run:
            print(f"📁 DRY RUN: Would create directory '{path}'")
            logging.info(f"Dry run: Would create directory '{path}'")
            return True
        
        try:
            path.mkdir(parents=True, exist_ok=True)
            logging.info(f"Created directory: {path}")
            return True
        except Exception as e:
            logging.error(f"Failed to create directory '{path}': {e}")
            return False
    
    def move_folder(self, source: Path, destination_dir: Path) -> bool:
        """
        Move folder to destination directory.
        
        Args:
            source: Source folder path
            destination_dir: Destination directory path
            
        Returns:
            True if move was successful
        """
        target_path = destination_dir / source.name
        
        if target_path.exists():
            print(f"⚠️  SKIPPED: '{source.name}' already exists in '{destination_dir}'")
            logging.warning(f"Duplicate detected: '{target_path}' already exists")
            return False
        
        if self.dry_run:
            print(f"🧪 DRY RUN: Would move '{source.name}' → '{destination_dir}'")
            logging.info(f"Dry run: Would move '{source}' to '{destination_dir}'")
            return True
        
        try:
            shutil.move(str(source), str(target_path))
            print(f"✅ Moved: '{source.name}' → '{destination_dir}'")
            logging.info(f"Moved '{source}' to '{target_path}'")
            return True
        except Exception as e:
            print(f"❌ ERROR: Could not move '{source.name}' → '{destination_dir}': {e}")
            logging.error(f"Error moving '{source}' to '{destination_dir}': {e}")
            return False
    
    def move_files_to_season_folder(self, source_folder: Path, show_dir: Path, season_num: int) -> bool:
        """
        Move files from source folder to season-organized directory.
        
        Args:
            source_folder: Source folder containing episodes
            show_dir: Show's main directory
            season_num: Season number
            
        Returns:
            True if all files were moved successfully
        """
        season_dir = show_dir / f"Season {season_num:02d}"
        
        if not self.ensure_directory(season_dir):
            return False
        
        success = True
        files_moved = 0
        
        for file_path in source_folder.iterdir():
            if file_path.is_file() and file_path.suffix != ".part":
                dest_file = season_dir / file_path.name
                
                if dest_file.exists():
                    print(f"⚠️  File already exists: {dest_file} — skipping")
                    continue
                
                if self.dry_run:
                    print(f"🧪 DRY RUN: Would move '{file_path.name}' → '{season_dir}'")
                    logging.info(f"Dry run: Would move '{file_path}' to '{season_dir}'")
                    files_moved += 1
                else:
                    try:
                        shutil.move(str(file_path), str(dest_file))
                        print(f"✅ Moved file: {file_path.name} → {season_dir}")
                        logging.info(f"Moved file '{file_path.name}' to '{season_dir}'")
                        files_moved += 1
                    except Exception as e:
                        print(f"❌ ERROR moving '{file_path.name}': {e}")
                        logging.error(f"Error moving file '{file_path}': {e}")
                        success = False
        
        # Remove empty source folder
        if not self.dry_run and success and files_moved > 0:
            try:
                if not any(source_folder.iterdir()):
                    source_folder.rmdir()
                    print(f"🧹 Removed empty folder: {source_folder}")
                    logging.info(f"Removed empty source folder: {source_folder}")
            except Exception as e:
                logging.warning(f"Could not remove empty folder '{source_folder}': {e}")
        
        return success


class DirectoryWatcher:
    """
    Monitors directory for changes and tracks folder states.
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.last_scan_time = datetime.now()
        self.known_folders: Set[str] = set()
        self.known_files: Dict[str, float] = {}  # folder_name -> last_modified_time
        self._initial_scan()
    
    def _initial_scan(self) -> None:
        """Perform initial scan to establish baseline."""
        if not self.config.SOURCE_DIR.exists():
            logging.warning(f"Source directory does not exist: {self.config.SOURCE_DIR}")
            return
        
        try:
            for item in self.config.SOURCE_DIR.iterdir():
                if item.is_dir():
                    self.known_folders.add(item.name)
                    self.known_files[item.name] = item.stat().st_mtime
            
            logging.info(f"Initial scan found {len(self.known_folders)} folders")
            print(f"📂 Watching {len(self.known_folders)} existing folders")
            
        except Exception as e:
            logging.error(f"Error during initial scan: {e}")
    
    def check_for_changes(self) -> bool:
        """
        Check if there are any changes in the source directory.
        
        Returns:
            True if changes detected, False otherwise
        """
        if not self.config.SOURCE_DIR.exists():
            return False
        
        try:
            current_folders = set()
            current_files = {}
            
            for item in self.config.SOURCE_DIR.iterdir():
                if item.is_dir():
                    current_folders.add(item.name)
                    current_files[item.name] = item.stat().st_mtime
            
            # Check for new folders
            new_folders = current_folders - self.known_folders
            if new_folders:
                logging.info(f"New folders detected: {new_folders}")
                print(f"🆕 New folders detected: {', '.join(new_folders)}")
                self._update_known_state(current_folders, current_files)
                return True
            
            # Check for removed folders
            removed_folders = self.known_folders - current_folders
            if removed_folders:
                logging.info(f"Folders removed: {removed_folders}")
                print(f"🗑️  Folders removed: {', '.join(removed_folders)}")
                self._update_known_state(current_folders, current_files)
                return True
            
            # Check for modified folders (new files added)
            for folder_name in current_folders:
                if folder_name in self.known_files:
                    if current_files[folder_name] > self.known_files[folder_name]:
                        logging.info(f"Folder modified: {folder_name}")
                        print(f"📝 Folder modified: {folder_name}")
                        self._update_known_state(current_folders, current_files)
                        return True
            
            return False
            
        except Exception as e:
            logging.error(f"Error checking for changes: {e}")
            return False
    
    def _update_known_state(self, folders: Set[str], files: Dict[str, float]) -> None:
        """Update the known state after detecting changes."""
        self.known_folders = folders.copy()
        self.known_files = files.copy()
        self.last_scan_time = datetime.now()


class WatchModeManager:
    """
    Manages the watch mode operation with proper shutdown handling.
    """
    
    def __init__(self, sorter: 'MediaSorter'):
        self.sorter = sorter
        self.watcher = DirectoryWatcher(sorter.config)
        self.running = False
        self.thread = None
        self.last_processing_time = None
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            print(f"\n🛑 Received signal {signum}. Shutting down gracefully...")
            logging.info(f"Received shutdown signal: {signum}")
            self.stop()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def start(self) -> None:
        """Start the watch mode."""
        if self.running:
            return
        
        self.running = True
        print(f"👁️  Watch mode started - monitoring every {self.sorter.config.WATCH_INTERVAL // 60} minutes")
        print("📍 Press Ctrl+C to stop watching")
        logging.info("Watch mode started")
        
        # Start in a separate thread to allow for clean shutdown
        self.thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.thread.start()
        
        try:
            # Keep main thread alive
            while self.running:
                sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self) -> None:
        """Stop the watch mode."""
        if not self.running:
            return
        
        self.running = False
        print("\n🛑 Stopping watch mode...")
        logging.info("Watch mode stopped")
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
    
    def _watch_loop(self) -> None:
        """Main watch loop that runs in a separate thread."""
        while self.running:
            try:
                # Check if we're in cooldown period
                if self._in_cooldown_period():
                    sleep(60)  # Check every minute during cooldown
                    continue
                
                # Check for changes
                if self.watcher.check_for_changes():
                    print(f"🔄 Changes detected! Starting processing...")
                    logging.info("Changes detected, starting processing")
                    
                    # Process the changes
                    self.sorter.sort_all_folders()
                    self.last_processing_time = datetime.now()
                    
                    print(f"✅ Processing complete. Next check in {self.sorter.config.WATCH_INTERVAL // 60} minutes")
                else:
                    current_time = datetime.now().strftime("%H:%M:%S")
                    print(f"⏰ {current_time} - No changes detected")
                
                # Wait for next check
                for _ in range(self.sorter.config.WATCH_INTERVAL):
                    if not self.running:
                        break
                    sleep(1)
                
            except Exception as e:
                logging.error(f"Error in watch loop: {e}")
                print(f"❌ Watch loop error: {e}")
                # Wait a bit before retrying
                sleep(60)
    
    def _in_cooldown_period(self) -> bool:
        """Check if we're still in the cooldown period after last processing."""
        if not self.last_processing_time:
            return False
        
        cooldown_end = self.last_processing_time + timedelta(
            seconds=self.sorter.config.COOLDOWN_PERIOD
        )
        
        if datetime.now() < cooldown_end:
            return True
        
        return False


class MediaSorter:
    """Main class that orchestrates the media sorting process."""
    
    def __init__(self, config: Config, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.api_client = APIClient(config)
        self.classifier = MediaClassifier(self.api_client)
        self.file_manager = FileManager(config, dry_run)
        
        # Statistics
        self.stats = {
            'processed': 0,
            'movies': 0,
            'tv_shows': 0,
            'anime_movies': 0,
            'anime_series': 0,
            'unknown': 0,
            'errors': 0
        }
    
    def setup_logging(self) -> None:
        """Configure logging system."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(self.config.LOG_FILE),
                logging.StreamHandler()
            ]
        )
    
    def ensure_target_directories(self) -> bool:
        """Ensure all target directories exist."""
        directories = [
            self.config.MOVIES_DIR,
            self.config.TV_SHOWS_DIR,
            self.config.ANIME_MOVIES_DIR,
            self.config.ANIME_SERIES_DIR
        ]
        
        success = True
        for directory in directories:
            if not self.file_manager.ensure_directory(directory):
                success = False
        
        return success
    
    def detect_season_from_folder(self, folder_path: Path) -> Optional[int]:
        """
        Detect season number from folder contents.
        
        Args:
            folder_path: Path to folder to analyze
            
        Returns:
            Season number if detected, otherwise None
        """
        # First try folder name
        season_num = TitleCleaner.extract_season_info(folder_path.name)
        if season_num:
            return season_num
        
        # Then try file names
        for file_path in folder_path.iterdir():
            if file_path.is_file():
                season_num = TitleCleaner.extract_season_info(file_path.name)
                if season_num:
                    return season_num
        
        return 1  # Default to season 1
    
    def handle_series(self, folder_path: Path, media_info: MediaInfo) -> bool:
        """
        Handle TV series or anime series sorting.
        
        Args:
            folder_path: Source folder path
            media_info: Media information
            
        Returns:
            True if handled successfully
        """
        season_number = self.detect_season_from_folder(folder_path)
        
        if media_info.media_type == MediaType.ANIME_SERIES:
            base_dir = self.config.ANIME_SERIES_DIR
            print(f"🎌 Anime Series: '{media_info.title}', Season: {season_number:02d}")
        else:
            base_dir = self.config.TV_SHOWS_DIR
            print(f"📺 TV Show: '{media_info.title}', Season: {season_number:02d}")
        
        show_dir = base_dir / media_info.title
        
        if not self.file_manager.ensure_directory(show_dir):
            return False
        
        return self.file_manager.move_files_to_season_folder(
            folder_path, show_dir, season_number
        )
    
    def sort_single_folder(self, folder_path: Path) -> bool:
        """
        Sort a single media folder.
        
        Args:
            folder_path: Path to folder to sort
            
        Returns:
            True if sorted successfully
        """
        print(f"\n🔍 Processing: {folder_path.name}")
        logging.info(f"Processing: {folder_path.name}")
        
        # Classify the media
        media_info = self.classifier.classify_media(folder_path.name)
        
        print(f"🏷️  Classification: {media_info.media_type.value}")
        print(f"📝 Clean title: {media_info.title}")
        
        success = False
        
        # Route based on media type
        if media_info.media_type == MediaType.MOVIE:
            print(f"🎬 Movie detected")
            success = self.file_manager.move_folder(folder_path, self.config.MOVIES_DIR)
            self.stats['movies'] += 1
            
        elif media_info.media_type == MediaType.ANIME_MOVIE:
            print(f"🎬 Anime movie detected")
            success = self.file_manager.move_folder(folder_path, self.config.ANIME_MOVIES_DIR)
            self.stats['anime_movies'] += 1
            
        elif media_info.media_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
            success = self.handle_series(folder_path, media_info)
            if media_info.media_type == MediaType.TV_SERIES:
                self.stats['tv_shows'] += 1
            else:
                self.stats['anime_series'] += 1
            
        else:
            print(f"❓ Unclassified: {folder_path.name}")
            logging.warning(f"Unclassified folder: {folder_path.name}")
            self.stats['unknown'] += 1
            return True  # Not an error, just unclassified
        
        if not success:
            self.stats['errors'] += 1
        
        return success
    
    def start_watch_mode(self) -> None:
        """Start watch mode to monitor directory for changes."""
        watch_manager = WatchModeManager(self)
        watch_manager.start()
    
    def sort_all_folders(self) -> None:
        """Sort all folders in the source directory."""
        if not self.config.SOURCE_DIR.exists():
            print(f"❌ Source directory does not exist: {self.config.SOURCE_DIR}")
            return
        
        if not self.ensure_target_directories():
            print("❌ Failed to create target directories")
            return
        
        folders = [f for f in self.config.SOURCE_DIR.iterdir() if f.is_dir()]
        
        if not folders:
            print("✨ No folders found to process!")
            logging.info("No folders found to process")
            return
        
        print(f"📂 Found {len(folders)} folders to process")
        
        for folder in folders:
            try:
                self.sort_single_folder(folder)
                self.stats['processed'] += 1
            except Exception as e:
                print(f"❌ Unexpected error processing '{folder.name}': {e}")
                logging.error(f"Unexpected error processing '{folder}': {e}")
                self.stats['errors'] += 1
        
        self.print_summary()
    
    def print_summary(self) -> None:
        """Print sorting summary statistics."""
        print(f"\n{'='*50}")
        print("📊 SORTING SUMMARY")
        print(f"{'='*50}")
        print(f"📁 Total processed: {self.stats['processed']}")
        print(f"🎬 Movies: {self.stats['movies']}")
        print(f"📺 TV Shows: {self.stats['tv_shows']}")
        print(f"🎌 Anime Movies: {self.stats['anime_movies']}")
        print(f"🎌 Anime Series: {self.stats['anime_series']}")
        print(f"❓ Unknown: {self.stats['unknown']}")
        print(f"❌ Errors: {self.stats['errors']}")
        print(f"{'='*50}")
        
        logging.info(f"Sorting completed. Stats: {self.stats}")
def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sort media folders by type using OMDb and AniList APIs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Sort all folders once
  %(prog)s --dry-run          # Preview changes without moving files
  %(prog)s --watch            # Monitor directory for changes (15 min intervals)
  %(prog)s --watch --watch-interval 30  # Monitor with 30 minute intervals
        """
    )
    
    parser.add_argument(
        "--dry-run", 
        action="store_true", 
        help="Preview actions without moving files"
    )
    
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Monitor source directory for changes and process automatically"
    )
    
    parser.add_argument(
        "--watch-interval",
        type=int,
        default=15,
        metavar="MINUTES",
        help="Watch mode check interval in minutes (default: 15)"
    )
    
    parser.add_argument(
        "--version", 
        action="version", 
        version="Media Sorter 2.0"
    )
    
    args = parser.parse_args()
    
    # Initialize configuration
    config = Config()
    
    # Update watch interval if specified
    if args.watch_interval:
        config.WATCH_INTERVAL = args.watch_interval * 60  # Convert to seconds
    
    # Validate configuration
    if not config.validate():
        print("❌ Configuration validation failed. Please check your settings.")
        return 1
    
    # Initialize sorter
    sorter = MediaSorter(config, dry_run=args.dry_run)
    sorter.setup_logging()
    
    # Print header
    print(ASCII_ART)
    
    if args.dry_run:
        print("🧪 DRY RUN MODE - No files will be moved")
        logging.info("Dry run mode enabled")
    
    try:
        # Choose operation mode
        if args.watch:
            if args.dry_run:
                print("⚠️  Watch mode with dry-run: will show what would be processed")

            try:
                sorter.start_watch_mode()
                return 0
            except KeyboardInterrupt:
                print("\n⏹️  Watch mode stopped by user")
                return 0
        else:
            # Single run mode
            try:
                sorter.sort_all_folders()
                return 0
            except KeyboardInterrupt:
                print("\n⏹️  Operation cancelled by user")
                logging.info("Operation cancelled by user")
                return 1

    except Exception as e:
        print(f"❌ Fatal error: {e}")
        logging.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())