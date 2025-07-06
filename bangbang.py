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

Version 6.2.6.0
- FEATURE: Portable & Installer ready

v6.2.5.1
- FIXED: Tray menu did not feat. new tab.

v6.2.5.0
- FEATURE: Implemented pagination in the Reorganize tab for large libraries.
- BUG FIX: A bug where the about tab could cause a crash.

v6.2
- FEATURE: new Reorganize tab 

v6.1.0.1
- Release
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
    handlers = [logging.FileHandler(log_file, encoding='utf-8')]
    if log_to_console: handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=handlers, force=True)

class Config:
    def __init__(self):
        self.SOURCE_DIR, self.MOVIES_DIR, self.TV_SHOWS_DIR, self.ANIME_MOVIES_DIR, self.ANIME_SERIES_DIR, self.MISMATCHED_DIR = "", "", "", "", "", ""
        self.SUPPORTED_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp', '.ogv', '.ts', '.m2ts', '.mts'}
        self.SIDECAR_EXTENSIONS = {'.srt', '.sub', '.nfo', '.txt', '.jpg', '.png'}
        self.CUSTOM_STRINGS_TO_REMOVE = {'FRENCH', 'TRUEFRENCH', 'VOSTFR', 'MULTI', 'SUBFRENCH'}
        self.API_PROVIDER, self.OMDB_API_KEY, self.TMDB_API_KEY = "omdb", "yourkey", "yourkey"
        self.OMDB_URL, self.TMDB_URL, self.ANILIST_URL = "http://www.omdbapi.com/", "https://api.themoviedb.org/3", "https://graphql.anilist.co"
        self.REQUEST_DELAY, self.WATCH_INTERVAL, self.FALLBACK_SHOW_DESTINATION = 1.0, 900, "mismatched"
        self.LANGUAGES_TO_SPLIT, self.SPLIT_MOVIES_DIR = ["fr"], ""
        self.MOVIES_ENABLED, self.TV_SHOWS_ENABLED, self.ANIME_MOVIES_ENABLED, self.ANIME_SERIES_ENABLED, self.CLEANUP_MODE_ENABLED = True, True, True, True, False

    def get_path(self, key: str) -> Optional[Path]:
        p = getattr(self, key); return Path(p) if p else None
    def to_dict(self):
        d = {}; [d.update({k: list(v) if isinstance(v, set) else v}) for k, v in self.__dict__.items() if not k.startswith('_')]; return d
    @classmethod
    def from_dict(cls, data):
        c = cls()
        if "FRENCH_MODE_ENABLED" in data: c.LANGUAGES_TO_SPLIT = ["fr"] if data["FRENCH_MODE_ENABLED"] else []
        if "FRENCH_MOVIES_DIR" in data: c.SPLIT_MOVIES_DIR = data["FRENCH_MOVIES_DIR"]
        for k, v in data.items():
            if hasattr(c, k): setattr(c, k, set(v) if isinstance(getattr(c, k), set) else v)
        return c
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
        except Exception as e: logging.error(f"Error loading config from '{path}': {e}. Loading defaults."); return cls()
    def validate(self) -> (bool, str):
        if self.API_PROVIDER == "omdb" and (not self.OMDB_API_KEY or self.OMDB_API_KEY == "yourkey"): return False, "Primary provider (OMDb) API key is not configured."
        if self.API_PROVIDER == "tmdb" and (not self.TMDB_API_KEY or self.TMDB_API_KEY == "yourkey"): return False, "Primary provider (TMDB) API key is not configured."
        sd = self.get_path('SOURCE_DIR');
        if not sd or not sd.exists(): return False, f"Source directory not found or not set: {sd}"
        return True, "Validation successful."

class TitleCleaner:
    METADATA_BREAKPOINT_PATTERN = re.compile(r'('r'\s[\(\[]?\d{4}[\)\]]?\b'r'|\s[Ss]\d{1,2}[Ee]\d{1,2}\b'r'|\s[Ss]\d{1,2}\b'r'|\sSeason\s\d{1,2}\b'r'|\s\d{3,4}p\b'r'|\s(WEBRip|BluRay|BDRip|DVDRip|HDRip|WEB-DL|HDTV)\b'r'|\s(x264|x265|H\.?264|H\.?265|HEVC|AVC)\b'r')', re.IGNORECASE)
    @classmethod
    def clean_for_search(cls, name: str, custom_strings: Set[str]) -> str:
        nws = re.sub(r'[\._]', ' ', name); tt = nws
        for s in custom_strings: tt = re.sub(r'\b' + re.escape(s) + r'\b', ' ', tt, flags=re.IGNORECASE)
        tp = tt[:match.start()] if (match := cls.METADATA_BREAKPOINT_PATTERN.search(tt)) else tt
        ct = re.sub(r'\[[^\]]+\]', '', tp); return re.sub(r'\s+', ' ', ct).strip()
    @classmethod
    def extract_season_info(cls, filename: str) -> Optional[int]:
        for p in [r'\b[Ss](\d{1,2})[Ee]\d{1,2}\b', r'\bSeason[ _-]?(\d{1,2})\b', r'\b[Ss](\d{1,2})\b']:
            if m:=re.search(p, filename, re.IGNORECASE): return int(m.group(1))
        return None
    @classmethod
    def extract_episode_info(cls, filename: str) -> Optional[int]:
        m = re.search(r'[Ss]\d{1,2}[._- ]?[Ee](\d{1,3})\b', filename, re.IGNORECASE)
        if m: return int(m.group(1))
        m = re.search(r'\bEpisode[._- ]?(\d{1,3})\b', filename, re.IGNORECASE)
        if m: return int(m.group(1))
        return None
    @classmethod
    def extract_year(cls, filename: str) -> Optional[str]:
        ms = re.findall(r'\b(\d{4})\b', filename)
        if not ms: return None
        cy = datetime.now().year; py = [m for m in ms if 1900 <= int(m) <= cy + 2]; return py[-1] if py else None

class APIClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'SortMeDown/Engine/6.0.4'})
    
    def test_omdb_api_key(self, api_key: str) -> Tuple[bool, str]:
        if not api_key or api_key == "yourkey": return False, "API key is empty or is the default key."
        params = {"i": "tt0848228", "apikey": api_key}
        try:
            r = self.session.get(self.config.OMDB_URL, params=params, timeout=10)
            r.raise_for_status()
            d = r.json()
            if d.get("Response") == "True": return True, "OMDb API Key is valid!"
            else: return False, f"OMDb Key is invalid: {d.get('Error', 'Unknown error')}"
        except requests.RequestException as e: return False, f"Network request failed: {e}"

    def test_tmdb_api_key(self, api_key: str) -> Tuple[bool, str]:
        if not api_key or api_key == "yourkey": return False, "API key is empty or is the default key."
        params = {"api_key": api_key}
        try:
            r = self.session.get(f"{self.config.TMDB_URL}/configuration", params=params, timeout=10)
            if r.status_code == 200: return True, "TMDB API Key is valid!"
            elif r.status_code == 401: return False, "TMDB Key is invalid or has been revoked."
            else: r.raise_for_status(); return False, f"TMDB returned status {r.status_code}"
        except requests.RequestException as e: return False, f"Network request failed: {e}"

    def query_omdb(self, title: str) -> Optional[Dict[str, Any]]:
        try:
            for p in [{"t": title}, {"s": title}]:
                fp = {**p, "apikey": self.config.OMDB_API_KEY}
                r = self.session.get(self.config.OMDB_URL, params=fp, timeout=10)
                r.raise_for_status()
                d = r.json()
                if d.get("Response") == "True":
                    if "Search" in d:
                        id_p = {"i": d["Search"][0]["imdbID"], "apikey": self.config.OMDB_API_KEY}
                        id_r = self.session.get(self.config.OMDB_URL, params=id_p, timeout=10)
                        return id_r.json()
                    return d
        except requests.RequestException as e: logging.error(f"OMDb API request failed for '{title}': {e}")
        return None

    def query_tmdb(self, title: str) -> Optional[Dict[str, Any]]:
        try:
            sp = {"api_key": self.config.TMDB_API_KEY, "query": title}
            sr = self.session.get(f"{self.config.TMDB_URL}/search/multi", params=sp, timeout=10)
            sr.raise_for_status()
            sd = sr.json()
            if not sd.get("results"): return None
            fr = sd["results"][0]
            mt, mid = fr.get("media_type"), fr.get("id")
            if mt not in ["movie", "tv"]: return None
            dp = {"api_key": self.config.TMDB_API_KEY, "append_to_response": "credits,translations"}
            dr = self.session.get(f"{self.config.TMDB_URL}/{mt}/{mid}", params=dp, timeout=10)
            dr.raise_for_status()
            return dr.json()
        except requests.RequestException as e: logging.error(f"TMDB API request failed for '{title}': {e}")
        return None

    def query_anilist(self, title: str) -> Optional[Dict[str, Any]]:
        q = '''query ($search: String) { Media(search: $search, type: ANIME) { title { romaji english native } format, genres, season, seasonYear, episodes } }'''
        try:
            r = self.session.post(self.config.ANILIST_URL, json={"query": q, "variables": {"search": title}}, timeout=10)
            r.raise_for_status()
            m = r.json().get("data", {}).get("Media")
            if m: logging.info(f"AniList found match for: {title}"); return m
        except requests.RequestException as e: logging.error(f"AniList API request failed for '{title}': {e}")
        return None

class MediaClassifier:
    def __init__(self, api_client: APIClient):
        self.api_client = api_client

    def classify_media(self, name: str, custom_strings: Set[str]) -> MediaInfo:
        clean_name = TitleCleaner.clean_for_search(name, custom_strings)
        if not clean_name:
            logging.warning(f"Could not extract a clean name from '{name}'. Skipping.")
            return MediaInfo(title=name, year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)
        
        logging.info(f"Classifying: '{name}' -> Clean search: '{clean_name}'")
        cfg = self.api_client.config
        anilist_data = None
        if cfg.ANIME_MOVIES_ENABLED or cfg.ANIME_SERIES_ENABLED:
            anilist_data = self.api_client.query_anilist(clean_name)
            sleep(cfg.REQUEST_DELAY)

        pp, sp = cfg.API_PROVIDER, "tmdb" if cfg.API_PROVIDER == "omdb" else "omdb"
        sa = (sp == 'omdb' and cfg.OMDB_API_KEY and cfg.OMDB_API_KEY != 'yourkey') or \
             (sp == 'tmdb' and cfg.TMDB_API_KEY and cfg.TMDB_API_KEY != 'yourkey')
        
        logging.info(f"Using '{pp.upper()}' as primary provider.")
        qfp = getattr(self.api_client, f"query_{pp}")
        mad = qfp(clean_name)

        if mad is None and sa:
            logging.warning(f"Primary provider '{pp.upper()}' failed. Trying fallback '{sp.upper()}'.")
            sleep(cfg.REQUEST_DELAY)
            qfs = getattr(self.api_client, f"query_{sp}")
            mad = qfs(clean_name)
            if mad: pp = sp
            
        if anilist_data:
            if mad and pp == 'omdb' and "animation" not in mad.get("Genre", "").lower() and "japan" not in mad.get("Country", "").lower():
                return self._classify_from_omdb(mad)
            return self._classify_from_anilist(anilist_data)
        
        if mad: return self._classify_from_main_api(mad, pp)
        
        logging.warning(f"No API results found for: {clean_name}")
        return MediaInfo(title=name, year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)

    def _classify_from_main_api(self, data: Dict[str, Any], p: str) -> MediaInfo:
        if p == "omdb": return self._classify_from_omdb(data)
        if p == "tmdb": return self._classify_from_tmdb(data)
        return MediaInfo(title=data.get("Title", "Unknown"), year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)

    def _classify_from_anilist(self, d: Dict[str, Any]) -> MediaInfo:
        ft = d.get("format", "").upper()
        mt = MediaType.ANIME_MOVIE if ft == "MOVIE" else MediaType.ANIME_SERIES if ft in ["TV", "TV_SHORT", "ONA", "OVA", "SPECIAL"] else MediaType.UNKNOWN
        t = d.get('title', {}).get('english') or d.get('title', {}).get('romaji')
        return MediaInfo(title=t, year=str(d.get("seasonYear", "")), media_type=mt, language="Japanese", genre=", ".join(d.get("genres", [])))

    def _classify_from_omdb(self, d: Dict[str, Any]) -> MediaInfo:
        t_ = d.get("Type", "").lower()
        mt = MediaType.MOVIE if t_ == "movie" else MediaType.TV_SERIES if t_ in ["series", "tv series"] else MediaType.UNKNOWN
        return MediaInfo(title=d.get("Title"), year=(d.get("Year", "") or "").split('–')[0], media_type=mt, language=d.get("Language", ""), genre=d.get("Genre", ""))

    def _classify_from_tmdb(self, d: Dict[str, Any]) -> MediaInfo:
        is_m = "title" in d
        mt = MediaType.MOVIE if is_m else MediaType.TV_SERIES
        t = d.get("title") if is_m else d.get("name")
        y = (d.get("release_date") or d.get("first_air_date") or "{}").split('-')[0]
        lang = ""
        if d.get("translations"):
            et = next((t for t in d["translations"]["translations"] if t["iso_639_1"] == "en"), None)
            if et: lang = et["english_name"]
        g = ", ".join([g["name"] for g in d.get("genres", [])])
        return MediaInfo(title=t, year=y, media_type=mt, language=lang, genre=g)

class FileManager:
    def __init__(self, cfg: Config, dry_run: bool): self.cfg, self.dry_run = cfg, dry_run
    def _find_sidecar_files(self, pf: Path) -> List[Path]:
        s, st = [], pf.stem
        for sib in pf.parent.iterdir():
            if sib != pf and sib.stem == st and sib.suffix.lower() in self.cfg.SIDECAR_EXTENSIONS: s.append(sib)
        return s
    def ensure_dir(self, p: Path) -> bool:
        if not p: logging.error("Destination directory path is not set."); return False
        if not p.exists():
            if self.dry_run: logging.info(f"DRY RUN: Would create dir '{p}'")
            else:
                try: p.mkdir(parents=True, exist_ok=True)
                except Exception as e: logging.error(f"Could not create directory '{p}': {e}"); return False
        return True
    def move_file_group(self, fg: List[Path], dd: Path) -> bool:
        if not self.ensure_dir(dd): return False
        pf, all_ok = fg[0], True
        for ftm in fg:
            t = dd / ftm.name
            if str(ftm.resolve()) == str(t.resolve()): logging.info(f"Skipping move: '{ftm.name}' is already in correct location."); continue
            if t.exists(): logging.warning(f"SKIPPED: File '{t.name}' already exists in '{dd.name}'."); continue
            lp = "DRY RUN:" if self.dry_run else "Moved"
            if ftm != pf: lp += " (sidecar)"
            logging.info(f"{lp}: '{ftm.name}' -> '{dd.name}'")
            if not self.dry_run:
                try: shutil.move(str(ftm), str(t))
                except Exception as e: logging.error(f"ERROR moving file '{ftm.name}': {e}"); all_ok = False
        return all_ok
    def delete_file_group(self, pf: Path):
        fg = [pf] + self._find_sidecar_files(pf)
        logging.warning(f"DELETING {len(fg)} file(s) for group '{pf.stem}'")
        for ftd in fg:
            try:
                if self.dry_run: logging.info(f"DRY RUN: Would delete file '{ftd.name}'")
                else: os.remove(ftd); logging.info(f"Deleted file: {ftd.name}")
            except Exception as e: logging.error(f"Failed to delete file '{ftd.name}': {e}")
                
class DirectoryWatcher:
    def __init__(self, config: Config): self.config, self.last_mtime = config, 0; self._scan()
    def _scan(self):
        if (sd := self.config.get_path('SOURCE_DIR')) and sd.exists(): self.last_mtime = sd.stat().st_mtime
    def check_for_changes(self) -> bool:
        if (sd := self.config.get_path('SOURCE_DIR')) and sd.exists():
            mt = sd.stat().st_mtime
            if mt > self.last_mtime: self.last_mtime = mt; return True
        return False
        
class MediaSorter:
    def __init__(self, cfg: Config, dry_run: bool = False, progress_callback: Optional[Callable[[int, int], None]] = None):
        self.cfg, self.dry_run, self.progress_callback = cfg, dry_run, progress_callback
        self.api_client = APIClient(cfg); self.classifier = MediaClassifier(self.api_client); self.fm = FileManager(cfg, dry_run)
        self.stats, self.stop_event, self.is_processing = {}, threading.Event(), False
        
    def signal_stop(self): self.stop_event.set(); logging.info("Stop signal received. Finishing current item...")
    
    def force_move_item(self, item: Path, folder_name: str, media_type: MediaType, is_split_lang_override: bool = False):
        logging.info(f"FORCE MOVE: Manually classifying '{item.name}' as {media_type.value} into folder '{folder_name}'.")
        files_to_move = [item] + self.fm._find_sidecar_files(item)
        base_dir = {MediaType.MOVIE: self.cfg.get_path('MOVIES_DIR'), MediaType.TV_SERIES: self.cfg.get_path('TV_SHOWS_DIR'),
                    MediaType.ANIME_MOVIE: self.cfg.get_path('ANIME_MOVIES_DIR'), MediaType.ANIME_SERIES: self.cfg.get_path('ANIME_SERIES_DIR')}.get(media_type)
        if media_type == MediaType.MOVIE and is_split_lang_override and self.cfg.SPLIT_MOVIES_DIR: base_dir = self.cfg.get_path('SPLIT_MOVIES_DIR'); logging.info("Split language movie override selected.")
        if not base_dir: logging.error(f"Target directory for {media_type.value} is not set. Cannot force move."); return
        clean_folder_name = re.sub(r'[<>:"/\\|?*]', '', folder_name).strip()
        dest_folder = base_dir / clean_folder_name
        if media_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]: dest_folder = dest_folder / f"Season {TitleCleaner.extract_season_info(item.name) or 1:02d}"
        self.fm.move_file_group(files_to_move, dest_folder)

    def _get_mismatched_path(self) -> Optional[Path]:
        if p := self.cfg.get_path('MISMATCHED_DIR'): return p
        if sp := self.cfg.get_path('SOURCE_DIR'): return sp / '_Mismatched'
        return None
        
    def ensure_target_dirs(self) -> bool:
        if self.cfg.CLEANUP_MODE_ENABLED: return True
        dirs = [self._get_mismatched_path()]
        if self.cfg.MOVIES_ENABLED: dirs.append(self.cfg.get_path('MOVIES_DIR'))
        if self.cfg.TV_SHOWS_ENABLED: dirs.append(self.cfg.get_path('TV_SHOWS_DIR'))
        if self.cfg.ANIME_MOVIES_ENABLED: dirs.append(self.cfg.get_path('ANIME_MOVIES_DIR'))
        if self.cfg.ANIME_SERIES_ENABLED: dirs.append(self.cfg.get_path('ANIME_SERIES_DIR'))
        if self.cfg.LANGUAGES_TO_SPLIT and self.cfg.SPLIT_MOVIES_DIR: dirs.append(self.cfg.get_path('SPLIT_MOVIES_DIR'))
        return all(self.fm.ensure_dir(d) for d in dirs if d)
        
    def _validate_api_result(self, file_path: Path, term: str, info: MediaInfo) -> MediaInfo:
        is_series_in_file = TitleCleaner.extract_season_info(file_path.name) is not None
        is_movie_in_api = info.media_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]
        if is_series_in_file and is_movie_in_api:
            logging.warning(f"CONFLICT: Filename '{file_path.name}' suggests series, API says movie. Trusting filename.")
            info.media_type = MediaType.ANIME_SERIES if (info.language and "japanese" in info.language.lower()) else MediaType.TV_SERIES
        year_in_file = TitleCleaner.extract_year(file_path.name) or TitleCleaner.extract_year(term)
        if year_in_file and info.year and year_in_file != info.year:
            logging.warning(f"CONFLICT: Filename year '{year_in_file}' mismatches API year '{info.year}'. Reverting to safe fallback.")
            clean_title = TitleCleaner.clean_for_search(term, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
            info.media_type, info.title, info.year = MediaType.UNKNOWN, clean_title, year_in_file
        return info
        
    def sort_item(self, item: Path, override_name: Optional[str] = None):
        if item.suffix.lower() in self.cfg.SIDECAR_EXTENSIONS: return
        initial_info, search_term = None, None
        if override_name:
            search_term, initial_info = override_name, self.classifier.classify_media(override_name, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
        else:
            is_sub = item.parent != self.cfg.get_path('SOURCE_DIR')
            p_name = item.parent.name if is_sub else item.stem; search_term = p_name
            initial_info = self.classifier.classify_media(p_name, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
            if initial_info.media_type == MediaType.UNKNOWN and is_sub and (s_name := item.stem).lower() != p_name.lower():
                logging.warning(f"Folder search for '{p_name}' failed. Trying filename: '{s_name}'")
                fb_info = self.classifier.classify_media(s_name, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
                if fb_info.media_type != MediaType.UNKNOWN: logging.info("Filename fallback successful."); initial_info, search_term = fb_info, s_name
                else: logging.warning(f"Filename fallback for '{s_name}' also failed.")
        
        info = self._validate_api_result(item, search_term, initial_info)
        files_to_move = [item] + self.fm._find_sidecar_files(item)
        s = self.stats; logging.info(f"Class: {info.media_type.value} | Title: '{info.get_folder_name()}'" + (f" | Found {len(files_to_move) - 1} sidecars." if len(files_to_move) > 1 else ""))
        
        if info.media_type == MediaType.UNKNOWN:
            s['unknown'] += 1;
            if self.cfg.CLEANUP_MODE_ENABLED: logging.warning("Skipping fallback for UNKNOWN in Cleanup Mode."); return
            mpath = self._get_mismatched_path()
            if not mpath: logging.error("Mismatched dir not set. Skipping."); s['errors'] += 1; return
            is_series = TitleCleaner.extract_season_info(item.name) is not None
            if is_series:
                fdest = self.cfg.FALLBACK_SHOW_DESTINATION
                if fdest == "ignore": logging.info("Mismatched series set to 'ignore'."); return
                logging.info(f"Mismatched series routing to '{fdest}' destination.")
                dmap = {"tv": self.cfg.get_path('TV_SHOWS_DIR'), "anime": self.cfg.get_path('ANIME_SERIES_DIR'), "mismatched": mpath}
                bdir = dmap.get(fdest)
                if not bdir: logging.error(f"Fallback dir '{fdest}' not set."); s['errors'] += 1; return
                df = bdir / info.get_folder_name() / f"Season {TitleCleaner.extract_season_info(item.name) or 1:02d}"
                if self.fm.move_file_group(files_to_move, df): s['unknown'] -=1; s['tv' if fdest == 'tv' else 'anime_series' if fdest == 'anime' else 'unknown'] +=1
                else: s['errors'] += 1
            else:
                logging.info("Unidentified item is not a series. Routing to Mismatched folder.")
                df = mpath / info.get_folder_name()
                if self.fm.move_file_group(files_to_move, df): s['unknown'] -=1; s['movies'] += 1
                else: s['errors'] += 1
            return
            
        if not {MediaType.MOVIE: self.cfg.MOVIES_ENABLED, MediaType.TV_SERIES: self.cfg.TV_SHOWS_ENABLED,
                MediaType.ANIME_MOVIE: self.cfg.ANIME_MOVIES_ENABLED, MediaType.ANIME_SERIES: self.cfg.ANIME_SERIES_ENABLED}.get(info.media_type, True):
            logging.info(f"Skipping {info.media_type.value} sort (disabled)."); return

        base_dir = item.parent if self.cfg.CLEANUP_MODE_ENABLED else {MediaType.MOVIE: self.cfg.get_path('MOVIES_DIR'), MediaType.TV_SERIES: self.cfg.get_path('TV_SHOWS_DIR'),
                      MediaType.ANIME_MOVIE: self.cfg.get_path('ANIME_MOVIES_DIR'), MediaType.ANIME_SERIES: self.cfg.get_path('ANIME_SERIES_DIR')}.get(info.media_type)
        
        if info.media_type == MediaType.MOVIE and self.cfg.get_path('SPLIT_MOVIES_DIR') and self.cfg.LANGUAGES_TO_SPLIT and not self.cfg.CLEANUP_MODE_ENABLED:
            movie_langs = {l.strip().lower() for l in (info.language or "").split(',')}
            split_langs = {l.strip().lower() for l in self.cfg.LANGUAGES_TO_SPLIT}
            should_split = "all" in split_langs and "english" not in movie_langs or not movie_langs.isdisjoint(split_langs)
            if should_split: logging.info(f"🔵⚪🔴 Movie language '{info.language}' matches split rule."); base_dir = self.cfg.get_path('SPLIT_MOVIES_DIR')
                
        if not base_dir: logging.error(f"Target dir for {info.media_type.value} not set."); s['errors'] += 1; return
            
        if info.media_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]:
            key = 'anime_movies' if info.media_type == MediaType.ANIME_MOVIE else 'movies'
            if base_dir == self.cfg.get_path('SPLIT_MOVIES_DIR'): key = 'split_lang_movies'
            dest_folder = base_dir / info.get_folder_name()
            if self.cfg.CLEANUP_MODE_ENABLED and dest_folder.resolve() == item.parent.resolve(): logging.info(f"Skipping move, '{item.name}' is already in the correct folder."); s[key] = s.get(key, 0) + 1; return
            if self.fm.move_file_group(files_to_move, dest_folder): s[key] = s.get(key, 0) + 1
            else: s['errors'] += 1
        elif info.media_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
            key = 'anime_series' if info.media_type == MediaType.ANIME_SERIES else 'tv'
            dest_folder = base_dir / info.get_folder_name() / f"Season {TitleCleaner.extract_season_info(item.name) or 1:02d}"
            if self.cfg.CLEANUP_MODE_ENABLED and dest_folder.resolve() == item.parent.resolve(): logging.info(f"Skipping move, '{item.name}' is already in correct folder."); s[key] += 1; return
            if self.fm.move_file_group(files_to_move, dest_folder): s[key] += 1
            else: s['errors'] += 1

    # --- START: CORRECTED Reorganize Methods ---
    def reorganize_folder_structure(self, target_path: Path, file_list: Optional[List[Path]] = None):
        """
        Organizes files into subfolders. This is a self-contained method and does not use
        the global 'CLEANUP_MODE_ENABLED' flag.
        """
        self.is_processing = True
        self.stop_event.clear()
        processed_files = 0
        total_files = 0
        try:
            logging.info(f"--- Starting Folder Reorganization for: '{target_path}' ---")

            files_to_process = file_list
            if not files_to_process:
                logging.info("No specific files selected, scanning entire directory...")
                files_to_process = [p for ext in self.cfg.SUPPORTED_EXTENSIONS for p in target_path.glob(f'**/*{ext}') if p.is_file()]

            total_files = len(files_to_process)
            if self.progress_callback: self.progress_callback(0, total_files)

            for item in files_to_process:
                if self.stop_event.is_set(): logging.warning("Reorganization run aborted."); break
                processed_files += 1
                
                try:
                    logging.info(f"Analyzing: '{item.relative_to(target_path)}'")
                    info = self.classifier.classify_media(item.stem, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
                    if info.media_type == MediaType.UNKNOWN:
                        logging.warning(f"SKIPPED: Could not identify '{item.name}', cannot determine destination folder.")
                        continue
                    
                    dest_folder = None
                    if info.media_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]:
                        dest_folder = target_path / info.get_folder_name()
                    elif info.media_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
                        season = TitleCleaner.extract_season_info(item.name) or 1
                        dest_folder = target_path / info.get_folder_name() / f"Season {season:02d}"
                    
                    if not dest_folder: continue

                    if dest_folder.resolve() == item.parent.resolve():
                        logging.info(f"Already in correct location: '{item.name}'")
                        continue
                    
                    files_to_move = [item] + self.fm._find_sidecar_files(item)
                    self.fm.move_file_group(files_to_move, dest_folder)

                except Exception as e:
                    logging.error(f"Fatal error reorganizing '{item.name}': {e}", exc_info=True)
                finally:
                    if self.progress_callback: self.progress_callback(processed_files, total_files)
        finally:
            self.is_processing = False
            logging.info("--- Folder Reorganization Finished ---")
            if self.progress_callback: self.progress_callback(processed_files, total_files)

    def rename_files_in_library(self, target_path: Path, file_list: Optional[List[Path]] = None):
        """
        Scans and renames media files. Processes only files in file_list if provided,
        otherwise scans the entire target_path.
        """
        self.is_processing = True
        self.stop_event.clear()
        processed_files, total_files = 0, 0
        try:
            logging.info(f"--- Starting Filename Cleanup for: '{target_path}' ---")
            files_to_process = file_list
            if not files_to_process:
                logging.info("No specific files selected, scanning entire directory...")
                files_to_process = [p for ext in self.cfg.SUPPORTED_EXTENSIONS for p in target_path.glob(f'**/*{ext}') if p.is_file()]
            
            total_files = len(files_to_process)
            if self.progress_callback: self.progress_callback(0, total_files)
            if not files_to_process: logging.info("No media files found to rename."); return

            for item in files_to_process:
                if self.stop_event.is_set(): logging.warning("Rename run aborted."); break
                processed_files += 1
                logging.info(f"Analyzing: '{item.relative_to(target_path)}'")
                
                info = self.classifier.classify_media(item.stem, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
                if info.media_type == MediaType.UNKNOWN:
                    logging.warning(f"SKIPPED: Could not identify '{item.name}', cannot generate clean name."); continue
                
                new_stem = ""
                if info.media_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]: new_stem = info.get_folder_name()
                elif info.media_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
                    s, e = TitleCleaner.extract_season_info(item.name), TitleCleaner.extract_episode_info(item.name)
                    if s and e: new_stem = f"{info.title} - S{s:02d}E{e:02d}"
                    elif s: new_stem = f"{info.title} - S{s:02d}"
                    else: logging.warning(f"SKIPPED: Could not extract season/episode from '{item.name}'."); continue
                
                sanitized_stem = re.sub(r'[<>:"/\\|?*]', '', new_stem).strip()
                if not sanitized_stem: logging.error(f"Failed to generate valid name for '{item.name}'."); continue
                
                file_group = [item] + self.fm._find_sidecar_files(item)
                for file_to_rename in file_group:
                    new_name = f"{sanitized_stem}{file_to_rename.suffix}"
                    new_target_path = file_to_rename.parent / new_name
                    if file_to_rename.resolve() == new_target_path.resolve(): logging.info(f"Already clean: '{file_to_rename.name}'"); continue
                    if new_target_path.exists(): logging.warning(f"SKIPPED: A file named '{new_name}' already exists."); continue
                    log_prefix = "DRY RUN:" if self.dry_run else "Renamed"
                    logging.info(f"{log_prefix}: '{file_to_rename.name}' -> '{new_name}'")
                    if not self.dry_run:
                        try: shutil.move(str(file_to_rename), str(new_target_path))
                        except Exception as ex: logging.error(f"ERROR renaming '{file_to_rename.name}': {ex}")

                if self.progress_callback: self.progress_callback(processed_files, total_files)
        finally:
            self.is_processing = False
            logging.info("--- Filename Cleanup Finished ---")
            if self.progress_callback: self.progress_callback(processed_files, total_files)
    # --- END: CORRECTED Reorganize Methods ---

    def process_source_directory(self):
        self.is_processing = True
        try:
            self.stop_event.clear(); self.stats = {k: 0 for k in ['processed','movies','tv','anime_movies','anime_series','split_lang_movies','unknown','errors']}
            source_dir = self.cfg.get_path('SOURCE_DIR')
            if not source_dir or not source_dir.exists() or not self.ensure_target_dirs(): logging.error("Source/Target dir validation failed."); return
            logging.info("Starting deep scan of source directory...")
            all_files = [p for ext in self.cfg.SUPPORTED_EXTENSIONS.union(self.cfg.SIDECAR_EXTENSIONS) for p in source_dir.glob(f'**/*{ext}') if p.is_file()]
            mpath = self._get_mismatched_path()
            if mpath and mpath.exists():
                mpath_abs = mpath.resolve()
                all_files = [f for f in all_files if not str(f.resolve().parent).startswith(str(mpath_abs))]
            media_files = [f for f in all_files if f.suffix.lower() in self.cfg.SUPPORTED_EXTENSIONS]
            total = len(media_files)
            if self.progress_callback: self.progress_callback(0, total)
            if not media_files: logging.info("No primary media files found to process.")
            else:
                logging.info(f"Found {total} primary media files to process.")
                for i, fp in enumerate(media_files):
                    if self.stop_event.is_set(): logging.warning("Sort run aborted."); break
                    self.stats['processed'] += 1
                    try: self.sort_item(fp)
                    except Exception as e: self.stats['errors'] += 1; logging.error(f"Fatal error processing '{fp.name}': {e}", exc_info=True)
                    if self.progress_callback: self.progress_callback(i + 1, total)
            if not self.stop_event.is_set() and not self.cfg.CLEANUP_MODE_ENABLED: self.cleanup_empty_dirs(source_dir)
            self.log_summary()
        finally: self.is_processing = False
    
    def cleanup_empty_dirs(self, path: Path):
        if self.dry_run: logging.info("DRY RUN: Skipping cleanup of empty directories."); return
        logging.info("Sweeping for empty directories...")
        mpath = self._get_mismatched_path()
        for dirpath, _, _ in os.walk(path, topdown=False):
            dp = Path(dirpath).resolve()
            if dp == path.resolve() or (mpath and dp == mpath.resolve()): continue
            try:
                if not os.listdir(dirpath): os.rmdir(dirpath); logging.info(f"Removed empty directory: {dirpath}")
            except OSError as e: logging.error(f"Error removing directory {dirpath}: {e}")

    def start_watch_mode(self):
        self.stop_event.clear()
        logging.info("Watch mode started. Performing initial sort...")
        self.process_source_directory()
        if self.stop_event.is_set():
            logging.info("Watch mode stopped during initial sort."); return
        watcher = DirectoryWatcher(self.cfg)
        interval = self.cfg.WATCH_INTERVAL
        logging.info(f"Initial sort complete. Now watching for changes every {interval // 60} minutes.")
        while not self.stop_event.is_set():
            if watcher.check_for_changes():
                logging.info("Changes detected! Starting new sort...")
                self.process_source_directory() 
                if self.stop_event.is_set():
                    logging.warning("Watch loop interrupted."); break
                logging.info("Processing complete. Resuming watch.")
            else:
                logging.info("No new files found. Continuing to watch.")
            for _ in range(interval):
                if self.stop_event.is_set(): break
                sleep(1)
        logging.info("Watch mode stopped.")

    def log_summary(self):
        summary = f"\n\n--- PROCESSING SUMMARY ---\n";
        for k, v in self.stats.items(): 
            if v > 0: summary += f"{k.replace('_',' ').title():<20}: {v}\n"
        summary += f"--------------------------\n"; logging.info(summary)
