#backeng for GUI 1.1

from pathlib import Path
import re
import shutil
import requests
import logging
from time import sleep
from typing import Optional, Dict, Any, Set
import json
import threading
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

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
        self.SUPPORTED_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp', '.ogv', '.ts', '.m2ts', '.mts' , '.sub']
        self.CUSTOM_STRINGS_TO_REMOVE = ['FRENCH', 'TRUEFRENCH', 'VOSTFR', 'MULTI', 'SUBFRENCH']
        self.OMDB_API_KEY = "yourkey"; self.OMDB_URL = "http://www.omdbapi.com/"; self.ANILIST_URL = "https://graphql.anilist.co"
        self.REQUEST_DELAY = 1.0; self.WATCH_INTERVAL = 15 * 60
        self.FRENCH_MODE_ENABLED = False
        # --- NEW ATTRIBUTES ---
        self.MOVIES_ENABLED = True
        self.TV_SHOWS_ENABLED = True
        self.ANIME_MOVIES_ENABLED = True
        self.ANIME_SERIES_ENABLED = True

    def get_path(self, key: str) -> Optional[Path]:
        p = getattr(self, key)
        return Path(p) if p else None
    def get_set(self, key: str) -> Set[str]:
        return set(getattr(self, key))
    def to_dict(self):
        # This will now automatically include the new attributes
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
            logging.warning("OMDb API key not configured. Please set it in Settings.")
            return False
        source_dir = self.get_path('SOURCE_DIR')
        if not source_dir or not source_dir.exists():
            logging.error(f"Source directory not found or not set: {source_dir}")
            return False
        return True

# ... TitleCleaner, APIClient, MediaClassifier, and FileManager classes are unchanged ...
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
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'SortMeDown/GUI'})
    def query_omdb(self, title: str) -> Optional[Dict[str, Any]]:
        try:
            for params in [{"t": title}, {"s": title}]:
                full_params = {**params, "apikey": self.config.OMDB_API_KEY}
                response = self.session.get(self.config.OMDB_URL, params=full_params, timeout=10)
                response.raise_for_status()
                data = response.json()
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
    def ensure_dir(self, p: Path) -> bool:
        if not p: logging.error("❌ ERROR: Destination directory path is not set."); return False
        if not p.exists():
            if self.dry: logging.info(f"📁 DRY RUN: Would create dir '{p}'")
            else:
                try: p.mkdir(parents=True, exist_ok=True)
                except Exception as e: logging.error(f"❌ ERROR: Could not create directory '{p}': {e}"); return False
        return True
    def move_file(self, src_file: Path, dest_dir: Path) -> bool:
        if not self.ensure_dir(dest_dir): return False
        target = dest_dir / src_file.name
        if target.exists(): logging.warning(f"⚠️  SKIPPED: File '{target.name}' already exists in '{dest_dir.name}'."); return False
        if self.dry: logging.info(f"🧪 DRY RUN: Would move file '{src_file.name}' → '{dest_dir}'"); return True
        try:
            shutil.move(str(src_file), str(target))
            logging.info(f"✅ Moved file: '{src_file.name}' → '{dest_dir.name}'")
            return True
        except Exception as e: logging.error(f"❌ ERROR moving file '{src_file.name}': {e}"); return False
    def move_folder(self, src_folder: Path, dest_parent_dir: Path, new_name: str) -> bool:
        if not self.ensure_dir(dest_parent_dir): return False
        target = dest_parent_dir / new_name
        if target.exists(): logging.warning(f"⚠️  SKIPPED: Folder '{target.name}' already exists in '{dest_parent_dir}'."); return False
        if self.dry: logging.info(f"🧪 DRY RUN: Would move folder '{src_folder.name}' → '{target}'"); return True
        try:
            shutil.move(str(src_folder), str(target))
            logging.info(f"✅ Moved folder: '{src_folder.name}' → '{target.name}'")
            return True
        except Exception as e: logging.error(f"❌ ERROR moving folder '{src_folder.name}': {e}"); return False
class DirectoryWatcher:
    def __init__(self, config: Config):
        self.config = config; self.last_mtime = 0; self._scan()
    def _scan(self):
        if (source_dir := self.config.get_path('SOURCE_DIR')) and source_dir.exists():
            self.last_mtime = source_dir.stat().st_mtime
    def check_for_changes(self) -> bool:
        if (source_dir := self.config.get_path('SOURCE_DIR')) and source_dir.exists():
            if (mtime := source_dir.stat().st_mtime) > self.last_mtime:
                self.last_mtime = mtime; return True
        return False
class WatchModeManager:
    def __init__(self, sorter: 'MediaSorter'):
        self.sorter = sorter; self.watcher = DirectoryWatcher(sorter.cfg); self.stop_event = threading.Event()
    def stop(self): self.stop_event.set()
    def start(self):
        logging.info("🚀 Performing initial sort...")
        self.sorter.process_source_directory(stop_event=self.stop_event)
        self.watcher._scan()
        self._loop()
    def _loop(self):
        while not self.stop_event.is_set():
            if self.watcher.check_for_changes():
                logging.info(f"🔄 Changes detected! Starting processing...")
                self.sorter.process_source_directory(stop_event=self.stop_event)
                logging.info(f"✅ Processing complete.")
            if self.stop_event.wait(timeout=self.sorter.cfg.WATCH_INTERVAL): break
        logging.info("🛑 Watch mode stopped.")

class MediaSorter:
    def __init__(self, cfg: Config, dry: bool):
        self.cfg, self.dry = cfg, dry # fr is now part of cfg
        self.api_client = APIClient(cfg); self.classifier = MediaClassifier(self.api_client)
        self.fm = FileManager(cfg, dry); self.watch_manager = None
        self.stats = {k: 0 for k in ['processed','movies','tv','anime_movies','anime_series','french_movies','unknown','errors']}

    def ensure_target_dirs(self) -> bool:
        # Now only creates directories for enabled types
        dirs_to_check = []
        if self.cfg.MOVIES_ENABLED: dirs_to_check.append(self.cfg.get_path('MOVIES_DIR'))
        if self.cfg.TV_SHOWS_ENABLED: dirs_to_check.append(self.cfg.get_path('TV_SHOWS_DIR'))
        if self.cfg.ANIME_MOVIES_ENABLED: dirs_to_check.append(self.cfg.get_path('ANIME_MOVIES_DIR'))
        if self.cfg.ANIME_SERIES_ENABLED: dirs_to_check.append(self.cfg.get_path('ANIME_SERIES_DIR'))
        if self.cfg.FRENCH_MODE_ENABLED: dirs_to_check.append(self.cfg.get_path('FRENCH_MOVIES_DIR'))
        return all(self.fm.ensure_dir(d) for d in dirs_to_check if d)

    def sort_item(self, item: Path):
        is_folder = item.is_dir()
        name_to_classify = item.name if is_folder else item.stem
        info = self.classifier.classify_media(name_to_classify, self.cfg.get_set('CUSTOM_STRINGS_TO_REMOVE'))
        logging.info(f"🏷️  Class: {info.media_type.value} | Title: '{info.get_folder_name()}'")

        s, m_type = self.stats, info.media_type
        
        # --- NEW LOGIC BLOCK TO CHECK IF SORTING IS ENABLED ---
        if m_type == MediaType.MOVIE and not self.cfg.MOVIES_ENABLED:
            logging.warning("Skipping movie sort (disabled in settings)."); return
        if m_type == MediaType.TV_SERIES and not self.cfg.TV_SHOWS_ENABLED:
            logging.warning("Skipping TV show sort (disabled in settings)."); return
        if m_type == MediaType.ANIME_MOVIE and not self.cfg.ANIME_MOVIES_ENABLED:
            logging.warning("Skipping anime movie sort (disabled in settings)."); return
        if m_type == MediaType.ANIME_SERIES and not self.cfg.ANIME_SERIES_ENABLED:
            logging.warning("Skipping anime series sort (disabled in settings)."); return
        if m_type == MediaType.UNKNOWN:
            s['unknown'] += 1; return

        success = False
        if m_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]:
            dest_dir, key = (self.cfg.get_path('ANIME_MOVIES_DIR'), 'anime_movies') if m_type == MediaType.ANIME_MOVIE else (self.cfg.get_path('MOVIES_DIR'), 'movies')
            if m_type == MediaType.MOVIE and self.cfg.FRENCH_MODE_ENABLED and "french" in (info.language or "").lower():
                dest_dir, key = self.cfg.get_path('FRENCH_MOVIES_DIR'), 'french_movies'
            if not dest_dir: logging.error(f"Target directory for {m_type.value} not set."); s['errors'] += 1; return
            folder_name = info.get_folder_name()
            if is_folder: success = self.fm.move_folder(item, dest_dir, folder_name)
            else: success = self.fm.move_file(item, dest_dir / folder_name)
            if success: s[key] += 1
            else: s['errors'] += 1
        elif m_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
            dest_dir, key = (self.cfg.get_path('ANIME_SERIES_DIR'), 'anime_series') if m_type == MediaType.ANIME_SERIES else (self.cfg.get_path('TV_SHOWS_DIR'), 'tv')
            if not dest_dir: logging.error(f"Target directory for {m_type.value} not set."); s['errors'] += 1; return
            season = TitleCleaner.extract_season_info(item.name) or 1
            season_dir = dest_dir / info.get_folder_name() / f"Season {season:02d}"
            if is_folder:
                files = [f for f in item.iterdir() if f.is_file()]
                if not files: logging.warning(f"Skipping empty folder: {item.name}"); return
                results = [self.fm.move_file(f, season_dir) for f in files]
                if all(results):
                    success = True
                    if not self.dry:
                        try: shutil.rmtree(item)
                        except Exception as e: logging.error(f"Could not remove original folder {item.name}: {e}")
            else: success = self.fm.move_file(item, season_dir)
            if success: s[key] += 1
            else: s['errors'] += 1

    def process_source_directory(self, stop_event: Optional[threading.Event] = None):
        source_dir = self.cfg.get_path('SOURCE_DIR')
        self.stats = {k: 0 for k in self.stats}
        if not source_dir or not source_dir.exists() or not self.ensure_target_dirs():
            logging.error("Source/Target directory validation failed. Please check settings.")
            self.print_summary(); return
        items = [i for i in source_dir.iterdir() if i.is_dir() or i.suffix.lower() in self.cfg.get_set('SUPPORTED_EXTENSIONS')]
        if not items: logging.info("✨ No supported files or folders found to process.")
        else:
            logging.info(f"📂 Found {len(items)} items to process.")
            for item in items:
                if stop_event and stop_event.is_set(): logging.warning("🛑 Sort run aborted by user."); break
                self.stats['processed'] += 1
                try: self.sort_item(item)
                except Exception as e: self.stats['errors'] += 1; logging.error(f"Fatal error on '{item.name}': {e}", exc_info=True)
        self.print_summary()
    def start_watch_mode(self):
        self.watch_manager = WatchModeManager(self); self.watch_manager.start()
    def stop_watch_mode(self):
        if self.watch_manager: self.watch_manager.stop()
    def print_summary(self):
        summary = f"\n{'='*50}\n📊 SORTING SUMMARY\n{'='*50}\n"
        for k, v in self.stats.items(): summary += f"{k.replace('_',' ').title():<15}: {v}\n"
        summary += f"{'='*50}"
        logging.info(summary)
