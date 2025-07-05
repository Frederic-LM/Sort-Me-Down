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

Version 6.1
- ENHANCED: new function to clean up and organise existing lib

Version 6.0.4
- ENHANCED: Made the "safe fallback mode" context-aware. If a conflict occurs
  after a successful filename-based fallback, the system will now correctly use
  the filename's title as the basis for the new folder, not the old, failed
  folder name. This leads to more intuitive and accurate folder naming.

Version 6.0.3
- REFINED: Implemented a more robust two-step classification. The engine now
  first tries the folder name. If that fails (returns Unknown), it automatically
  falls back and attempts a second classification using the filename before
  resorting to the final mismatched/fallback handlers.

Version 6.0.2
- FIXED: Implemented a fallback mechanism where if a folder name yields no API
  results, the engine will attempt to use the filename for classification. This
  solves the edge case where a poorly named folder contains a well-named file.
"""


from pathlib import Path
import re
import shutil
import requests
import logging
import threading
from time import sleep
from typing import Optional, Dict, Any, Set, List, Callable, Tuple
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

def setup_logging(log_file: Path, log_to_console: bool = False):
    """Configures logging for the application engine."""
    handlers = [logging.FileHandler(log_file, encoding='utf-8')]
    if log_to_console: handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=handlers, force=True)

class Config:
    def __init__(self):
        self.SOURCE_DIR = ""
        self.MOVIES_DIR = ""
        self.TV_SHOWS_DIR = ""
        self.ANIME_MOVIES_DIR = ""
        self.ANIME_SERIES_DIR = ""
        self.MISMATCHED_DIR = ""
        self.SUPPORTED_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp', '.ogv', '.ts', '.m2ts', '.mts'}
        self.SIDECAR_EXTENSIONS = {'.srt', '.sub', '.nfo', '.txt', '.jpg', '.png'}
        self.CUSTOM_STRINGS_TO_REMOVE = {'FRENCH', 'TRUEFRENCH', 'VOSTFR', 'MULTI', 'SUBFRENCH'}
        
        self.API_PROVIDER = "omdb"
        self.OMDB_API_KEY = "yourkey"
        self.TMDB_API_KEY = "yourkey"
        
        self.OMDB_URL = "http://www.omdbapi.com/"
        self.TMDB_URL = "https://api.themoviedb.org/3"
        self.ANILIST_URL = "https://graphql.anilist.co"
        self.REQUEST_DELAY = 1.0
        self.WATCH_INTERVAL = 15 * 60
        self.FALLBACK_SHOW_DESTINATION = "mismatched"

        self.LANGUAGES_TO_SPLIT = ["fr"]
        self.SPLIT_MOVIES_DIR = ""
        
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
        if "FRENCH_MODE_ENABLED" in data:
            if data["FRENCH_MODE_ENABLED"]:
                config.LANGUAGES_TO_SPLIT = ["fr"]
            else:
                config.LANGUAGES_TO_SPLIT = []
        if "FRENCH_MOVIES_DIR" in data:
            config.SPLIT_MOVIES_DIR = data["FRENCH_MOVIES_DIR"]

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
        if self.API_PROVIDER == "omdb" and (not self.OMDB_API_KEY or self.OMDB_API_KEY == "yourkey"):
            return False, "Primary provider (OMDb) API key is not configured."
        if self.API_PROVIDER == "tmdb" and (not self.TMDB_API_KEY or self.TMDB_API_KEY == "yourkey"):
            return False, "Primary provider (TMDB) API key is not configured."
        source_dir = self.get_path('SOURCE_DIR')
        if not source_dir or not source_dir.exists(): return False, f"Source directory not found or not set: {source_dir}"
        return True, "Validation successful."

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

    # --- START: NEW METHOD ---
    @classmethod
    def extract_episode_info(cls, filename: str) -> Optional[int]:
        """Extracts the episode number from a filename."""
        # Pattern for S01E02, 1x02, etc.
        match = re.search(r'[Ss]\d{1,2}[._- ]?[Ee](\d{1,3})', filename, re.IGNORECASE)
        if match:
            return int(match.group(1))

        # Pattern for "Episode 02"
        match = re.search(r'Episode[._- ]?(\d{1,3})', filename, re.IGNORECASE)
        if match:
            return int(match.group(1))

        return None
    # --- END: NEW METHOD ---

    @classmethod
    def extract_year(cls, filename: str) -> Optional[str]:
        matches = re.findall(r'\b(\d{4})\b', filename)
        if not matches: return None
        current_year = datetime.now().year
        plausible_years = [m for m in matches if 1900 <= int(m) <= current_year + 2]
        return plausible_years[-1] if plausible_years else None

class APIClient:
    def __init__(self, config: Config): self.config = config; self.session = requests.Session(); self.session.headers.update({'User-Agent': 'SortMeDown/Engine/6.0.4'})
    
    def test_omdb_api_key(self, api_key: str) -> Tuple[bool, str]:
        if not api_key or api_key == "yourkey": return False, "API key is empty or is the default key."
        params = {"i": "tt0848228", "apikey": api_key}
        try:
            response = self.session.get(self.config.OMDB_URL, params=params, timeout=10)
            response.raise_for_status(); data = response.json()
            if data.get("Response") == "True": return True, "OMDb API Key is valid!"
            else: return False, f"OMDb Key is invalid: {data.get('Error', 'Unknown error')}"
        except requests.RequestException as e: return False, f"Network request failed: {e}"

    def test_tmdb_api_key(self, api_key: str) -> Tuple[bool, str]:
        if not api_key or api_key == "yourkey": return False, "API key is empty or is the default key."
        params = {"api_key": api_key}
        try:
            response = self.session.get(f"{self.config.TMDB_URL}/configuration", params=params, timeout=10)
            if response.status_code == 200: return True, "TMDB API Key is valid!"
            elif response.status_code == 401: return False, "TMDB Key is invalid or has been revoked."
            else: response.raise_for_status(); return False, f"TMDB returned status {response.status_code}"
        except requests.RequestException as e: return False, f"Network request failed: {e}"

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

    def query_tmdb(self, title: str) -> Optional[Dict[str, Any]]:
        try:
            search_params = {"api_key": self.config.TMDB_API_KEY, "query": title}
            search_response = self.session.get(f"{self.config.TMDB_URL}/search/multi", params=search_params, timeout=10)
            search_response.raise_for_status()
            search_data = search_response.json()
            if not search_data.get("results"): return None
            
            first_result = search_data["results"][0]
            media_type = first_result.get("media_type")
            media_id = first_result.get("id")

            if media_type not in ["movie", "tv"]: return None

            detail_params = {"api_key": self.config.TMDB_API_KEY, "append_to_response": "credits,translations"}
            detail_response = self.session.get(f"{self.config.TMDB_URL}/{media_type}/{media_id}", params=detail_params, timeout=10)
            detail_response.raise_for_status()
            return detail_response.json()

        except requests.RequestException as e: logging.error(f"TMDB API request failed for '{title}': {e}")
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
    def __init__(self, api_client: APIClient):
        self.api_client = api_client

    def classify_media(self, name: str, custom_strings: Set[str]) -> MediaInfo:
        clean_name = TitleCleaner.clean_for_search(name, custom_strings)
        logging.info(f"Classifying: '{name}' -> Clean search: '{clean_name}'")
        if not clean_name:
            logging.warning(f"Could not extract a clean name from '{name}'. Skipping.")
            return MediaInfo(title=name, year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)

        anilist_data = None
        cfg = self.api_client.config
        
        # Only query AniList if an anime type is actually enabled for sorting.
        if cfg.ANIME_MOVIES_ENABLED or cfg.ANIME_SERIES_ENABLED:
            anilist_data = self.api_client.query_anilist(clean_name)
            sleep(cfg.REQUEST_DELAY)
        
        primary_provider = cfg.API_PROVIDER
        secondary_provider = "tmdb" if primary_provider == "omdb" else "omdb"
        
        is_secondary_available = False
        if secondary_provider == 'omdb' and cfg.OMDB_API_KEY and cfg.OMDB_API_KEY != 'yourkey':
            is_secondary_available = True
        elif secondary_provider == 'tmdb' and cfg.TMDB_API_KEY and cfg.TMDB_API_KEY != 'yourkey':
            is_secondary_available = True

        logging.info(f"Using '{primary_provider.upper()}' as primary provider.")
        query_func_primary = getattr(self.api_client, f"query_{primary_provider}")
        main_api_data = query_func_primary(clean_name)

        if main_api_data is None and is_secondary_available:
            logging.warning(f"Primary provider '{primary_provider.upper()}' failed. Trying fallback '{secondary_provider.upper()}'.")
            sleep(self.api_client.config.REQUEST_DELAY)
            query_func_secondary = getattr(self.api_client, f"query_{secondary_provider}")
            main_api_data = query_func_secondary(clean_name)
            if main_api_data:
                primary_provider = secondary_provider

        if anilist_data:
            if main_api_data and primary_provider == 'omdb':
                if "animation" not in main_api_data.get("Genre", "").lower() and "japan" not in main_api_data.get("Country", "").lower():
                    return self._classify_from_omdb(main_api_data)
            return self._classify_from_anilist(anilist_data)

        if main_api_data:
            return self._classify_from_main_api(main_api_data, primary_provider)

        logging.warning(f"No API results found for: {clean_name}")
        return MediaInfo(title=name, year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)

    def _classify_from_main_api(self, data: Dict[str, Any], provider: str) -> MediaInfo:
        if provider == "omdb": return self._classify_from_omdb(data)
        if provider == "tmdb": return self._classify_from_tmdb(data)
        return MediaInfo(title=data.get("Title", "Unknown"), year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)

    def _classify_from_anilist(self, data: Dict[str, Any]) -> MediaInfo:
        f_type = data.get("format", "").upper(); m_type = MediaType.ANIME_MOVIE if f_type == "MOVIE" else MediaType.ANIME_SERIES if f_type in ["TV", "TV_SHORT", "ONA", "OVA", "SPECIAL"] else MediaType.UNKNOWN
        title = data.get('title', {}).get('english') or data.get('title', {}).get('romaji'); return MediaInfo(title=title, year=str(data.get("seasonYear", "")), media_type=m_type, language="Japanese", genre=", ".join(data.get("genres", [])))

    def _classify_from_omdb(self, data: Dict[str, Any]) -> MediaInfo:
        type_ = data.get("Type", "").lower(); m_type = MediaType.MOVIE if type_ == "movie" else MediaType.TV_SERIES if type_ in ["series", "tv series"] else MediaType.UNKNOWN
        return MediaInfo(title=data.get("Title"), year=(data.get("Year", "") or "").split('–')[0], media_type=m_type, language=data.get("Language", ""), genre=data.get("Genre", ""))

    def _classify_from_tmdb(self, data: Dict[str, Any]) -> MediaInfo:
        is_movie = "title" in data
        m_type = MediaType.MOVIE if is_movie else MediaType.TV_SERIES
        title = data.get("title") if is_movie else data.get("name")
        year_str = (data.get("release_date") or data.get("first_air_date") or "{}").split('-')[0]
        
        lang = ""
        if data.get("translations"):
            english_translation = next((t for t in data["translations"]["translations"] if t["iso_639_1"] == "en"), None)
            if english_translation:
                lang = english_translation["english_name"]

        genres = ", ".join([g["name"] for g in data.get("genres", [])])
        return MediaInfo(title=title, year=year_str, media_type=m_type, language=lang, genre=genres)

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

    def delete_file_group(self, primary_file: Path):
        """Deletes a primary file and all its associated sidecar files."""
        file_group = [primary_file] + self._find_sidecar_files(primary_file)
        logging.warning(f"DELETING {len(file_group)} file(s) for group '{primary_file.stem}'")
        for file_to_delete in file_group:
            try:
                if self.dry_run:
                    logging.info(f"DRY RUN: Would delete file '{file_to_delete.name}'")
                else:
                    os.remove(file_to_delete)
                    logging.info(f"Deleted file: {file_to_delete.name}")
            except Exception as e:
                logging.error(f"Failed to delete file '{file_to_delete.name}': {e}")
                
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
    def __init__(self, cfg: Config, dry_run: bool = False, progress_callback: Optional[Callable[[int, int], None]] = None):
        self.cfg = cfg; self.dry_run = dry_run; self.api_client = APIClient(cfg); self.classifier = MediaClassifier(self.api_client)
        self.fm = FileManager(cfg, self.dry_run); self.stats = {}; self.stop_event = threading.Event(); self.is_processing = False
        self.progress_callback = progress_callback
    def signal_stop(self): self.stop_event.set(); logging.info("Stop signal received. Finishing current item...")
    
    def force_move_item(self, item: Path, folder_name: str, media_type: MediaType, is_split_lang_override: bool = False):
        """Moves a file to a specified library based on manual classification, bypassing API calls."""
        logging.info(f"FORCE MOVE: Manually classifying '{item.name}' as {media_type.value} into folder '{folder_name}'.")
        files_to_move = [item] + self.fm._find_sidecar_files(item)
        
        base_dir = {
            MediaType.MOVIE: self.cfg.get_path('MOVIES_DIR'),
            MediaType.TV_SERIES: self.cfg.get_path('TV_SHOWS_DIR'),
            MediaType.ANIME_MOVIE: self.cfg.get_path('ANIME_MOVIES_DIR'),
            MediaType.ANIME_SERIES: self.cfg.get_path('ANIME_SERIES_DIR')
        }.get(media_type)

        if media_type == MediaType.MOVIE and is_split_lang_override and self.cfg.SPLIT_MOVIES_DIR:
            base_dir = self.cfg.get_path('SPLIT_MOVIES_DIR')
            logging.info("Split language movie override selected.")

        if not base_dir:
            logging.error(f"Target directory for {media_type.value} is not set in config. Cannot force move.")
            return

        clean_folder_name = re.sub(r'[<>:"/\\|?*]', '', folder_name).strip()
        dest_folder = base_dir / clean_folder_name
        
        if media_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
            season = TitleCleaner.extract_season_info(item.name) or 1
            dest_folder = dest_folder / f"Season {season:02d}"

        self.fm.move_file_group(files_to_move, dest_folder)

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
        if self.cfg.LANGUAGES_TO_SPLIT and self.cfg.SPLIT_MOVIES_DIR:
            dirs_to_check.append(self.cfg.get_path('SPLIT_MOVIES_DIR'))
        return all(self.fm.ensure_dir(d) for d in dirs_to_check if d)
        
    def _validate_api_result(self, file_path: Path, successful_search_term: str, api_info: MediaInfo) -> MediaInfo:
        is_series_in_filename = TitleCleaner.extract_season_info(file_path.name) is not None
        is_movie_in_api = api_info.media_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]
        if is_series_in_filename and is_movie_in_api:
            logging.warning(f"CONFLICT: Filename '{file_path.name}' indicates series, but API classified '{api_info.title}' as a movie. Trusting filename.")
            new_type = MediaType.ANIME_SERIES if (api_info.language and "japanese" in api_info.language.lower()) else MediaType.TV_SERIES
            api_info.media_type = new_type
        
        # Note: successful_search_term might be a full filename, so check it for a year too.
        year_in_filename = TitleCleaner.extract_year(file_path.name) or TitleCleaner.extract_year(successful_search_term)
        if year_in_filename and api_info.year and year_in_filename != api_info.year:
            logging.warning(f"CONFLICT: Filename year '{year_in_filename}' mismatches API year '{api_info.year}' for '{api_info.title}'. Reverting to safe fallback mode.")
            
            # Use the term that led to the successful (but conflicting) search as the basis for the safe title.
            clean_title = TitleCleaner.clean_for_search(successful_search_term, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
            api_info.media_type = MediaType.UNKNOWN; api_info.title = clean_title; api_info.year = year_in_filename
        return api_info
        
    def sort_item(self, item: Path, override_name: Optional[str] = None):
        if item.suffix.lower() in self.cfg.SIDECAR_EXTENSIONS: return

        initial_info: MediaInfo
        successful_search_term: str

        if override_name:
            logging.info(f"Re-processing '{item.name}' with manual name: '{override_name}'")
            successful_search_term = override_name
            initial_info = self.classifier.classify_media(override_name, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
        else:
            is_in_subfolder = item.parent != self.cfg.get_path('SOURCE_DIR')
            
            primary_name_to_classify = item.parent.name if is_in_subfolder else item.stem
            successful_search_term = primary_name_to_classify

            initial_info = self.classifier.classify_media(primary_name_to_classify, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
            
            if initial_info.media_type == MediaType.UNKNOWN and is_in_subfolder:
                secondary_name_to_classify = item.stem
                if secondary_name_to_classify.lower() != primary_name_to_classify.lower():
                    logging.warning(f"Folder-based search for '{primary_name_to_classify}' failed. Falling back to filename: '{secondary_name_to_classify}'")
                    fallback_info = self.classifier.classify_media(secondary_name_to_classify, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
                    
                    if fallback_info.media_type != MediaType.UNKNOWN:
                        logging.info("Fallback to filename was successful. Using new classification.")
                        initial_info = fallback_info
                        successful_search_term = secondary_name_to_classify # The filename is now the context
                    else:
                        logging.warning(f"Filename fallback for '{secondary_name_to_classify}' also failed.")
        
        info = self._validate_api_result(item, successful_search_term, initial_info)

        files_to_move = [item] + self.fm._find_sidecar_files(item)
        log_msg = f"Class: {info.media_type.value} | Title: '{info.get_folder_name()}'"
        s = self.stats
        if len(files_to_move) > 1: log_msg += f" | Found {len(files_to_move) - 1} sidecar file(s)."
        logging.info(log_msg)
        
        # --- START: MODIFIED/REPLACEMENT BLOCK for UNKNOWN MEDIA TYPE ---
        if info.media_type == MediaType.UNKNOWN:
            s['unknown'] += 1
            if self.cfg.CLEANUP_MODE_ENABLED:
                logging.warning("Skipping fallback move for UNKNOWN item in Cleanup Mode.")
                return

            mismatched_path = self._get_mismatched_path()
            if not mismatched_path:
                logging.error("Mismatched directory not set or determinable. Skipping UNKNOWN item.")
                s['errors'] += 1
                return

            is_series = TitleCleaner.extract_season_info(item.name) is not None

            if is_series:
                # --- Handler for UNKNOWN TV SHOWS ---
                # This logic respects the user's specific setting for mismatched shows.
                fallback_dest = self.cfg.FALLBACK_SHOW_DESTINATION
                if fallback_dest == "ignore":
                    logging.info("Fallback handler: Mismatched series set to 'ignore'. Leaving in place.")
                    return

                logging.info(f"Fallback handler: Mismatched series routing to '{fallback_dest}' destination as per settings.")
                dest_map = {
                    "tv": self.cfg.get_path('TV_SHOWS_DIR'),
                    "anime": self.cfg.get_path('ANIME_SERIES_DIR'),
                    "mismatched": mismatched_path
                }
                base_dir = dest_map.get(fallback_dest)

                if not base_dir:
                    logging.error(f"Fallback destination directory for '{fallback_dest}' not set. Skipping.")
                    s['errors'] += 1
                    return
                
                season = TitleCleaner.extract_season_info(item.name) or 1
                # Use get_folder_name() which safely handles missing titles from conflicts
                dest_folder = base_dir / info.get_folder_name() / f"Season {season:02d}"
                
                if self.fm.move_file_group(files_to_move, dest_folder):
                    s['unknown'] -=1
                    # Update the correct stat based on where it went
                    stat_key = 'tv' if fallback_dest == 'tv' else 'anime_series' if fallback_dest == 'anime' else 'unknown'
                    s[stat_key] += 1
                else:
                    s['errors'] += 1
            
            else:
                # --- Default Handler for ALL OTHER UNKNOWNS (Movies, etc.) ---
                # This logic ALWAYS routes to the Mismatched folder, ignoring the TV show setting.
                logging.info("Fallback handler: Unidentified item is not a series. Routing to Mismatched folder.")
                
                # The folder name will be "Title (Year)" if available, or just "Unknown"
                dest_folder = mismatched_path / info.get_folder_name()
                
                if self.fm.move_file_group(files_to_move, dest_folder):
                    # We can consider this a successful "movie" fallback sort for stats
                    s['unknown'] -= 1
                    s['movies'] += 1
                else:
                    s['errors'] += 1
            return
        # --- END: MODIFIED/REPLACEMENT BLOCK ---
            
        type_enabled_map = {MediaType.MOVIE: self.cfg.MOVIES_ENABLED, MediaType.TV_SERIES: self.cfg.TV_SHOWS_ENABLED, MediaType.ANIME_MOVIE: self.cfg.ANIME_MOVIES_ENABLED, MediaType.ANIME_SERIES: self.cfg.ANIME_SERIES_ENABLED}
        if not type_enabled_map.get(info.media_type, True):
            logging.info(f"Skipping {info.media_type.value} sort (disabled in config).")
            return

        base_dir = item.parent if self.cfg.CLEANUP_MODE_ENABLED else {
            MediaType.MOVIE: self.cfg.get_path('MOVIES_DIR'),
            MediaType.TV_SERIES: self.cfg.get_path('TV_SHOWS_DIR'),
            MediaType.ANIME_MOVIE: self.cfg.get_path('ANIME_MOVIES_DIR'),
            MediaType.ANIME_SERIES: self.cfg.get_path('ANIME_SERIES_DIR')
        }.get(info.media_type)
        
        if info.media_type == MediaType.MOVIE and self.cfg.get_path('SPLIT_MOVIES_DIR') and self.cfg.LANGUAGES_TO_SPLIT and not self.cfg.CLEANUP_MODE_ENABLED:
            movie_languages = {lang.strip().lower() for lang in (info.language or "").split(',')}
            split_languages = {lang.strip().lower() for lang in self.cfg.LANGUAGES_TO_SPLIT}

            should_split = False
            if "all" in split_languages:
                if "english" not in movie_languages:
                    should_split = True
            elif not movie_languages.isdisjoint(split_languages):
                should_split = True

            if should_split:
                logging.info(f"🔵⚪🔴 Movie language '{info.language}' matches split rule. Routing to split directory.")
                base_dir = self.cfg.get_path('SPLIT_MOVIES_DIR')
                
        if not base_dir:
            logging.error(f"Target directory for {info.media_type.value} is not set.")
            s['errors'] += 1
            return
            
        if info.media_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]:
            key = 'anime_movies' if info.media_type == MediaType.ANIME_MOVIE else 'movies'
            if base_dir == self.cfg.get_path('SPLIT_MOVIES_DIR'): key = 'split_lang_movies'
            
            dest_folder = base_dir / info.get_folder_name()
            # --- START: Redundant Folder Fix ---
            if self.cfg.CLEANUP_MODE_ENABLED and dest_folder.resolve() == item.parent.resolve():
                logging.info(f"Skipping move, '{item.name}' is already in the correct folder.")
                s[key] = s.get(key, 0) + 1
                return
            # --- END: Redundant Folder Fix ---
            
            if self.fm.move_file_group(files_to_move, dest_folder): s[key] = s.get(key, 0) + 1
            else: s['errors'] += 1
        elif info.media_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
            key = 'anime_series' if info.media_type == MediaType.ANIME_SERIES else 'tv'
            season = TitleCleaner.extract_season_info(item.name) or 1
            
            dest_folder = base_dir / info.get_folder_name() / f"Season {season:02d}"
            # --- START: Redundant Folder Fix ---
            if self.cfg.CLEANUP_MODE_ENABLED and dest_folder.resolve() == item.parent.resolve():
                logging.info(f"Skipping move, '{item.name}' is already in the correct folder.")
                s[key] += 1
                return
            # --- END: Redundant Folder Fix ---

            if self.fm.move_file_group(files_to_move, dest_folder): s[key] += 1
            else: s['errors'] += 1
            
    # --- START: NEW METHODS for Reorganize Tab ---
    def reorganize_folder_structure(self, target_path: Path):
        """
        Organizes files within the target_path into subfolders.
        This is a controlled wrapper around the 'Clean Up In Place' logic.
        """
        self.is_processing = True
        try:
            logging.info(f"--- Starting Folder Reorganization for: '{target_path}' ---")
            
            # Temporarily override config for this specific task
            original_source_dir = self.cfg.SOURCE_DIR
            original_cleanup_mode = self.cfg.CLEANUP_MODE_ENABLED
            
            self.cfg.SOURCE_DIR = str(target_path)
            self.cfg.CLEANUP_MODE_ENABLED = True
            
            # Run the main processing logic with the overridden config
            self.process_source_directory()

        except Exception as e:
            logging.error(f"A fatal error occurred during folder reorganization: {e}", exc_info=True)
        finally:
            # Restore original config to not affect other operations
            self.cfg.SOURCE_DIR = original_source_dir
            self.cfg.CLEANUP_MODE_ENABLED = original_cleanup_mode
            self.is_processing = False
            logging.info("--- Folder Reorganization Finished ---")

    def rename_files_in_library(self, target_path: Path):
        """
        Scans a library and renames media files and their sidecars to a clean format.
        Format: 'Title (Year).ext' for movies, 'Title - S01E02.ext' for TV.
        """
        self.is_processing = True
        self.stop_event.clear()
        total_files = 0
        processed_files = 0

        try:
            logging.info(f"--- Starting Filename Cleanup for: '{target_path}' ---")
            media_files = [p for ext in self.cfg.SUPPORTED_EXTENSIONS for p in target_path.glob(f'**/*{ext}') if p.is_file()]
            total_files = len(media_files)
            
            if self.progress_callback: self.progress_callback(0, total_files)
            if not media_files:
                logging.info("No media files found to rename.")
                return

            for item in media_files:
                if self.stop_event.is_set():
                    logging.warning("Rename run aborted by user.")
                    break
                
                processed_files += 1
                logging.info(f"Analyzing: '{item.name}'")
                
                info = self.classifier.classify_media(item.stem, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
                if info.media_type == MediaType.UNKNOWN:
                    logging.warning(f"SKIPPED: Could not identify '{item.name}', cannot generate clean name.")
                    if self.progress_callback: self.progress_callback(processed_files, total_files)
                    continue

                new_stem = ""
                if info.media_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]:
                    new_stem = info.get_folder_name() # "Title (Year)"
                elif info.media_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
                    season = TitleCleaner.extract_season_info(item.name)
                    episode = TitleCleaner.extract_episode_info(item.name)
                    if season and episode:
                        new_stem = f"{info.title} - S{season:02d}E{episode:02d}"
                    elif season: # Fallback for files with only season info
                        new_stem = f"{info.title} - S{season:02d}"
                    else:
                        logging.warning(f"SKIPPED: Could not extract season/episode from '{item.name}'.")
                        if self.progress_callback: self.progress_callback(processed_files, total_files)
                        continue
                
                sanitized_stem = re.sub(r'[<>:"/\\|?*]', '', new_stem).strip()
                if not sanitized_stem:
                    logging.error(f"Failed to generate a valid new name for '{item.name}'.")
                    if self.progress_callback: self.progress_callback(processed_files, total_files)
                    continue
                
                file_group = [item] + self.fm._find_sidecar_files(item)
                
                for file_to_rename in file_group:
                    new_name = f"{sanitized_stem}{file_to_rename.suffix}"
                    new_target_path = file_to_rename.parent / new_name
                    
                    if file_to_rename.resolve() == new_target_path.resolve():
                        logging.info(f"Already clean: '{file_to_rename.name}'")
                        continue
                    
                    if new_target_path.exists():
                        logging.warning(f"SKIPPED: A file named '{new_name}' already exists.")
                        continue # Break inner loop to not rename part of the group
                    
                    log_prefix = "DRY RUN:" if self.dry_run else "Renamed"
                    logging.info(f"{log_prefix}: '{file_to_rename.name}' -> '{new_name}'")
                    
                    if not self.dry_run:
                        try:
                            shutil.move(str(file_to_rename), str(new_target_path))
                        except Exception as e:
                            logging.error(f"ERROR renaming '{file_to_rename.name}': {e}")

                if self.progress_callback: self.progress_callback(processed_files, total_files)
        
        except Exception as e:
            logging.error(f"A fatal error occurred during file renaming: {e}", exc_info=True)
        finally:
            self.is_processing = False
            logging.info("--- Filename Cleanup Finished ---")
            if self.progress_callback: self.progress_callback(processed_files, total_files)
    # --- END: NEW METHODS ---

    def process_source_directory(self):
        self.is_processing = True
        try:
            self.stop_event.clear(); self.stats = {k: 0 for k in ['processed','movies','tv','anime_movies','anime_series','split_lang_movies','unknown','errors']}
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
            total_files = len(media_files)

            if self.progress_callback: self.progress_callback(0, total_files)

            if not media_files: logging.info("No primary media files found to process.")
            else:
                logging.info(f"Found {total_files} primary media files to process.")
                for file_path in media_files:
                    if self.stop_event.is_set(): logging.warning("Sort run aborted by user."); break
                    self.stats['processed'] += 1
                    try: self.sort_item(file_path)
                    except Exception as e: self.stats['errors'] += 1; logging.error(f"Fatal error processing '{file_path.name}': {e}", exc_info=True)
                    
                    if self.progress_callback: self.progress_callback(self.stats['processed'], total_files)

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
        if self.cfg.CLEANUP_MODE_ENABLED:
            logging.error("FATAL: Watch mode cannot be started when 'Clean Up In Place' mode is enabled.")
            return

        self.stop_event.clear()
        logging.info("Watch mode started. Performing initial sort...")
        self.process_source_directory()

        if self.stop_event.is_set():
            logging.info("Watch mode stopped during initial sort.")
            return

        watcher = DirectoryWatcher(self.cfg)
        logging.info(f"Initial sort complete. Now watching for changes every {self.cfg.WATCH_INTERVAL // 60} minutes.")
        
        while not self.stop_event.wait(timeout=self.cfg.WATCH_INTERVAL):
            if watcher.check_for_changes():
                logging.info("Changes detected! Starting new sort...")
                self.process_source_directory() 
                if self.stop_event.is_set():
                    logging.warning("Watch loop interrupted by user during sort.")
                    break
                logging.info("Processing complete. Resuming watch.")
            else:
                logging.info("No new files found. Continuing to watch.")
        
        logging.info("Watch mode stopped.")

    def log_summary(self):
        summary = f"\n\n--- PROCESSING SUMMARY ---\n";
        for k, v in self.stats.items(): 
            if v > 0:
                summary += f"{k.replace('_',' ').title():<20}: {v}\n"
        summary += f"--------------------------\n"; logging.info(summary)
