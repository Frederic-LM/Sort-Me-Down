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


Version 6.7.1
- FIXED: Double Date string
- IMPROVED: smarter API call to tvdb -40% api call

Version 6.7.0 (Stable Release)
- FIXED: UnboundLocalError crash in sort_item by standardizing on 'stats' variable.Again
- FIXED: Reworked query_tvdb to correctly handle API search results, fixing all TVDB failures.Again
- FIXED: Removed duplicate TitleCleaner class definition.
- FIXED: All previous bugs related to language splitting, year searches, and anime detection.


Version 6.6.6
- FIXED: query_tvdb vrong api call

Version 6.6.5
- FIXED: UnboundLocalError crash in sort_item by standardizing on 'stats' variable.
- FIXED: query_tvdb method to correctly filter search results for relevant media types.

Version 6.6.4
- FIXED: Language split logic to correctly match language codes (e.g., 'fr') with full language names (e.g., 'French').
- FIXED: API search query logic to handle titles with years correctly.

Version 6.6.3
- Use of year param for API
- FEATURE: Lightweight, cross-platform notifications and startup logic.
- FIXED: Statistical bug for mismatched files.
- FIXED: Anime classification for clean filenames.

Version 6.5.0
- FEATURE: Optional system notifications for mismatched files.

Version 6.4.0
- FEATURE: TVDB API Integration
- FEATURE: Improved smart API provider logic
"""


from pathlib import Path
import re
import shutil
import requests
import logging
import threading
from time import sleep
import time
from typing import Optional, Dict, Any, Set, List, Callable, Tuple
import json
from dataclasses import dataclass
from enum import Enum
import os
import sys
from datetime import datetime
import subprocess

# --- Helper Functions ---

def resource_path(relative_path):
    try: base_path = Path(sys._MEIPASS)
    except Exception: base_path = Path(__file__).parent.absolute()
    return base_path / relative_path

def send_notification(title, message, app_name="SortMeDown"):
    try:
        if sys.platform == "win32":
            script_path = resource_path('send_notification.ps1')
            if not os.path.exists(script_path): return
            command = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path), "-Title", title, "-Message", message]
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.run(command, check=True, startupinfo=startupinfo)
        elif sys.platform == "darwin":
            command = ['osascript', '-e', f'display notification "{message}" with title "{title}"']
            subprocess.run(command, check=True)
        elif sys.platform == "linux":
            if shutil.which('notify-send'):
                command = ['notify-send', title, message, '-a', app_name]
                subprocess.run(command, check=True)
            else:
                logging.warning("`notify-send` command not found. Cannot send notification.")
    except Exception as e:
        logging.warning(f"Failed to send notification: {e}")

# --- Public Classes & Enums ---

class MediaType(Enum):
    MOVIE = "movie"; TV_SERIES = "series"; ANIME_MOVIE = "anime_movie"; ANIME_SERIES = "anime_series"; UNKNOWN = "unknown"

@dataclass
class MediaInfo:
    title: str; year: Optional[str]; media_type: MediaType; language: Optional[str]; genre: Optional[str]; season: Optional[int] = None
    def get_folder_name(self) -> str:
        if not self.title: return "Unknown"
        folder_title = re.sub(r'[<>:"/\\|?*]', '', self.title).strip()
        if self.year and self.year not in folder_title:
            return f"{folder_title} ({self.year})"
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
        self.TVDB_API_KEY, self.TVDB_PIN = "yourkey", ""
        self.TVDB_URL, self.TVDB_TOKEN, self.TVDB_TOKEN_EXPIRES = "https://api4.thetvdb.com/v4", "", 0
        self.OMDB_URL, self.TMDB_URL, self.ANILIST_URL = "http://www.omdbapi.com/", "https://api.themoviedb.org/3", "https://graphql.anilist.co"
        self.REQUEST_DELAY, self.WATCH_INTERVAL, self.FALLBACK_SHOW_DESTINATION = 1.0, 900, "mismatched"
        self.LANGUAGES_TO_SPLIT, self.SPLIT_MOVIES_DIR = [], ""
        self.MOVIES_ENABLED, self.TV_SHOWS_ENABLED, self.ANIME_MOVIES_ENABLED, self.ANIME_SERIES_ENABLED, self.CLEANUP_MODE_ENABLED = True, True, True, True, False
        self.NOTIFY_ON_MISMATCH = False

    def get_path(self, key: str) -> Optional[Path]:
        p = getattr(self, key); return Path(p) if p else None
    def to_dict(self):
        d = {}; [d.update({k: list(v) if isinstance(v, set) else v}) for k, v in self.__dict__.items() if not k.startswith('_')]; return d
    @classmethod
    def from_dict(cls, data):
        c = cls()
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
        if self.API_PROVIDER == "tvdb" and (not self.TVDB_API_KEY or self.TVDB_API_KEY == "yourkey"): return False, "Primary provider (TVDB) API key is not configured."
        sd = self.get_path('SOURCE_DIR');
        if not sd or not sd.exists(): return False, f"Source directory not found or not set: {sd}"
        return True, "Validation successful."

class TitleCleaner:
    METADATA_BREAKPOINT_PATTERN = re.compile(r'('r'\s[\(\[]?\d{4}[\)\]]?\b'r'|\s[Ss]\d{1,2}[Ee]\d{1,2}\b'r'|\s[Ss]\d{1,2}\b'r'|\sSeason\s\d{1,2}\b'r'|\s\d{3,4}p\b'r'|\s(WEBRip|BluRay|BDRip|DVDRip|HDRip|WEB-DL|HDTV|CR)\b'r'|\s(x264|x265|H\.?264|H\.?265|HEVC|AVC|AAC2\.0)\b'r'|\s(Msub)\b'r')', re.IGNORECASE)

    @classmethod
    def extract_search_terms(cls, name: str, custom_strings: Set[str]) -> Tuple[str, Optional[str]]:
        year = cls.extract_year(name)
        cleaned_name = re.sub(r'[\._]', ' ', name)
        for s in custom_strings:
            cleaned_name = re.sub(r'\b' + re.escape(s) + r'\b', ' ', cleaned_name, flags=re.IGNORECASE)
        title_part = cleaned_name[:match.start()] if (match := cls.METADATA_BREAKPOINT_PATTERN.search(cleaned_name)) else cleaned_name
        final_title = re.sub(r'\[[^\]]+\]', '', title_part).strip()
        if year:
            final_title = final_title.replace(year, '')
        final_title = re.sub(r'\s+', ' ', final_title).strip()
        final_title = final_title.strip(' -')
        return final_title, year

    @classmethod
    def quick_clean_stem(cls, name: str, custom_strings: Set[str]) -> str:
        cleaned_name = re.sub(r'[\._]', ' ', name)
        for s in custom_strings:
            cleaned_name = re.sub(r'\b' + re.escape(s) + r'\b', ' ', cleaned_name, flags=re.IGNORECASE)
        match = cls.METADATA_BREAKPOINT_PATTERN.search(cleaned_name)
        if match:
            s_e_match = re.search(r'([Ss]\d{1,2}[Ee]\d{1,2})', cleaned_name, re.IGNORECASE)
            title_part = cleaned_name[:match.start()]
            if s_e_match:
                title_part = f"{title_part.strip()} - {s_e_match.group(1).upper()}"
            cleaned_name = title_part
        cleaned_name = re.sub(r'\[[^\]]+\]|\([^)]*\b(source|custom)\b[^)]*\)', '', cleaned_name, flags=re.IGNORECASE)
        cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
        return cleaned_name

    @classmethod
    def extract_season_info(cls, filename: str) -> Optional[int]:
        for p in [r'\b[Ss](\d{1,2})[Ee]\d{1,2}\b', r'\bSeason[ _\-]?' + r'(\d{1,2})\b', r'\b[Ss](\d{1,2})\b']:
            if m:=re.search(p, filename, re.IGNORECASE): return int(m.group(1))
        return None

    @classmethod
    def extract_episode_info(cls, filename: str) -> Optional[int]:
        m = re.search(r'[Ss]\d{1,2}[._\- ]?[Ee](\d{1,3})\b', filename, re.IGNORECASE)
        if m: return int(m.group(1))
        m = re.search(r'\bEpisode[._\- ]?(\d{1,3})\b', filename, re.IGNORECASE)
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
        self.session.headers.update({'User-Agent': 'SortMeDown/Engine/6.7.0'})
        self._tvdb_token_lock = threading.Lock()

    def _get_tvdb_token(self) -> Optional[str]:
        with self._tvdb_token_lock:
            current_time = time.time()
            if (self.config.TVDB_TOKEN and self.config.TVDB_TOKEN_EXPIRES > current_time + 300):
                return self.config.TVDB_TOKEN
            try:
                auth_data = {"apikey": self.config.TVDB_API_KEY, "pin": self.config.TVDB_PIN}
                response = self.session.post(f"{self.config.TVDB_URL}/login", json=auth_data, timeout=10)
                response.raise_for_status()
                data = response.json()
                if data.get("status") == "success":
                    token_data = data.get("data", {})
                    self.config.TVDB_TOKEN = token_data.get("token")
                    self.config.TVDB_TOKEN_EXPIRES = current_time + (24 * 3600)
                    logging.info("TVDB authentication successful")
                    return self.config.TVDB_TOKEN
                else:
                    logging.error(f"TVDB auth failed: {data.get('message', 'Unknown error')}")
                    return None
            except requests.RequestException as e:
                logging.error(f"TVDB authentication failed: {e}")
                return None
    
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

    def test_tvdb_api_key(self, api_key: str, pin: str = "") -> Tuple[bool, str]:
        if not api_key or api_key == "yourkey":
            return False, "API key is empty or is the default key."
        try:
            auth_data = {"apikey": api_key, "pin": pin}
            response = self.session.post(f"{self.config.TVDB_URL}/login", json=auth_data, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    return True, "TVDB API Key is valid!"
                else:
                    return False, f"TVDB authentication failed: {data.get('message', 'Unknown error')}"
            elif response.status_code == 401:
                return False, "TVDB API key is invalid or PIN is required."
            else:
                return False, f"TVDB returned status {response.status_code}"
        except requests.RequestException as e:
            return False, f"Network request failed: {e}"

    def query_omdb(self, title: str, year: Optional[str] = None) -> Optional[Dict[str, Any]]:
        try:
            params = {"apikey": self.config.OMDB_API_KEY}
            if year:
                params["y"] = year
            params["t"] = title
            r = self.session.get(self.config.OMDB_URL, params=params, timeout=10)
            r.raise_for_status()
            d = r.json()
            if d.get("Response") == "True":
                return d
            params.pop("t", None); params.pop("y", None)
            params["s"] = title
            r = self.session.get(self.config.OMDB_URL, params=params, timeout=10)
            r.raise_for_status()
            d = r.json()
            if d.get("Response") == "True" and "Search" in d:
                id_params = {"i": d["Search"][0]["imdbID"], "apikey": self.config.OMDB_API_KEY}
                id_r = self.session.get(self.config.OMDB_URL, params=id_params, timeout=10)
                return id_r.json()
        except requests.RequestException as e: logging.error(f"OMDb API request failed for '{title}': {e}")
        return None

    def query_tmdb(self, title: str, year: Optional[str] = None) -> Optional[Dict[str, Any]]:
        try:
            sp = {"api_key": self.config.TMDB_API_KEY, "query": title}
            if year:
                sp["year"] = year
            sr = self.session.get(f"{self.config.TMDB_URL}/search/multi", params=sp, timeout=10)
            sr.raise_for_status()
            sd = sr.json()
            if not sd.get("results"): return None
            best_result = sd["results"][0]
            if year:
                for result in sd["results"]:
                    release_date = result.get("release_date") or result.get("first_air_date") or ""
                    if release_date.startswith(year):
                        best_result = result
                        break
            mt, mid = best_result.get("media_type"), best_result.get("id")
            if mt not in ["movie", "tv"]: return None
            dp = {"api_key": self.config.TMDB_API_KEY, "append_to_response": "credits,translations"}
            dr = self.session.get(f"{self.config.TMDB_URL}/{mt}/{mid}", params=dp, timeout=10)
            dr.raise_for_status()
            return dr.json()
        except requests.RequestException as e: logging.error(f"TMDB API request failed for '{title}': {e}")
        return None
    
    def query_tvdb(self, title: str, year: Optional[str] = None, hints: Optional[Dict[str, bool]] = None) -> Optional[Dict[str, Any]]:
        token = self._get_tvdb_token()
        if not token:
            return None

        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        
        
        search_order = ["series", "movie"] 
        if hints:
            if hints.get('likely_series'):
                search_order = ["series", "movie"]
                logging.info("TVDB Hint: Prioritizing SERIES search based on filename.")
            elif hints.get('likely_movie'):
                search_order = ["movie", "series"]
                logging.info("TVDB Hint: Prioritizing MOVIE search based on filename.")

        for search_type in search_order: 
            try:
                search_params = {"query": title, "type": search_type}
                if year:
                    search_params["year"] = year

                logging.info(f"TVDB: Searching for TYPE='{search_type}' with params: {search_params}")
                response = self.session.get(f"{self.config.TVDB_URL}/search", headers=headers, params=search_params, timeout=10)

                if response.status_code != 200:
                    continue

                search_results = response.json().get("data")
                if not search_results:
                    continue

                best_match = search_results[0] 
                normalized_search_title = re.sub(r'[^\w\s]', '', title).lower()
                for result in search_results:
                    result_name = result.get("name", "")
                    normalized_result_name = re.sub(r'[^\w\s]', '', result_name).lower()
                    if normalized_search_title == normalized_result_name:
                        best_match = result
                        break

                media_type = best_match.get("type")
                tvdb_id = best_match.get("tvdb_id")

                if tvdb_id and media_type in ["series", "movie"]:
                    endpoint = "series" if media_type == "series" else "movies"
                    detail_url = f"{self.config.TVDB_URL}/{endpoint}/{tvdb_id}/extended"
                    detail_response = self.session.get(detail_url, headers=headers, timeout=10)
                    
                    if detail_response.status_code == 200:
                        detail_data = detail_response.json()
                        if detail_data.get("status") == "success" and detail_data.get("data"):
                            logging.info(f"TVDB SUCCESS: Found definitive record for '{best_match.get('name')}'")
                            return detail_data.get("data") 

            except requests.RequestException as e:
                logging.error(f"TVDB network error for type '{search_type}': {e}")
                continue
        
      
        logging.warning(f"TVDB could not find a definitive match for '{title}'.")
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

    def _detect_content_hints(self, filename: str, clean_name: str) -> Dict[str, bool]:
        hints = {'likely_anime': False, 'likely_series': False, 'likely_movie': False}
        anime_keywords = ['subbed', 'dubbed', 'vostfr']
        anime_patterns = [r'\[.*\]', r'\b(OVA|ONA|BD|BDRip)\b']
        hints['likely_anime'] = any(keyword in filename.lower() for keyword in anime_keywords) or \
                              any(re.search(pattern, filename, re.IGNORECASE) for pattern in anime_patterns)
        has_episode_info = TitleCleaner.extract_episode_info(filename) is not None
        has_season_info = TitleCleaner.extract_season_info(filename) is not None
        hints['likely_series'] = has_episode_info or has_season_info
        movie_keywords = ['1080p', '720p', '4k', 'bluray', 'webrip', 'dvdrip']
        hints['likely_movie'] = not hints['likely_series'] and any(keyword in filename.lower() for keyword in movie_keywords)
        return hints

    def _get_optimal_provider_order(self, content_hints: Dict[str, bool], config: Config) -> List[str]:
        available_providers = []
        if config.OMDB_API_KEY and config.OMDB_API_KEY != "yourkey": available_providers.append('omdb')
        if config.TMDB_API_KEY and config.TMDB_API_KEY != "yourkey": available_providers.append('tmdb')
        if config.TVDB_API_KEY and config.TVDB_API_KEY != "yourkey": available_providers.append('tvdb')
        if not available_providers: return []
        primary = config.API_PROVIDER
        provider_order = [primary] if primary in available_providers else []
        remaining = [p for p in available_providers if p != primary]
        priority_map = {
            'likely_anime': ['tmdb', 'tvdb', 'omdb'],
            'likely_series': ['tvdb', 'tmdb', 'omdb'],
            'likely_movie': ['tmdb', 'omdb', 'tvdb']
        }
        content_type = next((ctype for ctype, is_present in content_hints.items() if is_present), None)
        if content_type:
            for provider in priority_map[content_type]:
                if provider in remaining:
                    provider_order.append(provider)
                    remaining.remove(provider)
        provider_order.extend(remaining)
        return provider_order

    def classify_media(self, name: str, custom_strings: Set[str], filename: str = "") -> MediaInfo:
        clean_title, year = TitleCleaner.extract_search_terms(name, custom_strings)
        if not clean_title:
            logging.warning(f"Could not extract a clean name from '{name}'. Skipping.")
            return MediaInfo(title=name, year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)
        logging.info(f"Classifying: '{name}' -> Clean search: '{clean_title}'" + (f" (Year: {year})" if year else ""))
        content_hints = self._detect_content_hints(filename or name, clean_title)
        cfg = self.api_client.config
        provider_order = self._get_optimal_provider_order(content_hints, cfg)
        if not provider_order:
            logging.error("No API providers configured!")
            return MediaInfo(title=name, year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)
        logging.info(f"Provider priority: {' → '.join(p.upper() for p in provider_order)}")
        anilist_data = None
        if content_hints['likely_anime'] and (cfg.ANIME_MOVIES_ENABLED or cfg.ANIME_SERIES_ENABLED):
            logging.info("Anime suspected - checking AniList first")
            anilist_data = self.api_client.query_anilist(clean_title)
            sleep(cfg.REQUEST_DELAY)
            if anilist_data:
                return self._classify_from_anilist(anilist_data)
        main_api_data, successful_provider = None, None
        for provider in provider_order:
            logging.info(f"Trying {provider.upper()} API...")
            query_func = getattr(self.api_client, f"query_{provider}")
            if provider == 'tvdb':
                main_api_data = query_func(clean_title, year=year, hints=content_hints)
            else:
                main_api_data = query_func(clean_title, year=year)
            sleep(cfg.REQUEST_DELAY)
            if main_api_data:
                successful_provider = provider
                logging.info(f"{provider.upper()} found match!")
                break
            else:
                logging.warning(f"{provider.upper()} returned no results")
        if not main_api_data and not anilist_data and (cfg.ANIME_MOVIES_ENABLED or cfg.ANIME_SERIES_ENABLED):
            logging.info("Main APIs failed - trying AniList as fallback")
            anilist_data = self.api_client.query_anilist(clean_title)
            if anilist_data:
                return self._classify_from_anilist(anilist_data)
        if main_api_data:
            return self._classify_from_main_api(main_api_data, successful_provider)
        logging.warning(f"No API results found for: {clean_title}" + (f" ({year})" if year else ""))
        return MediaInfo(title=name, year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)

    def _classify_from_main_api(self, data: Dict[str, Any], provider: str) -> MediaInfo:
        if provider == "omdb": return self._classify_from_omdb(data)
        if provider == "tmdb": return self._classify_from_tmdb(data)
        if provider == "tvdb": return self._classify_from_tvdb(data)
        return MediaInfo(title=data.get("name", "Unknown"), year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)

    def _classify_from_anilist(self, d: Dict[str, Any]) -> MediaInfo:
        ft = d.get("format", "").upper()
        mt = MediaType.ANIME_MOVIE if ft == "MOVIE" else MediaType.ANIME_SERIES if ft in ["TV", "TV_SHORT", "ONA", "OVA", "SPECIAL"] else MediaType.UNKNOWN
        t = d.get('title', {}).get('english') or d.get('title', {}).get('romaji')
        return MediaInfo(title=t, year=str(d.get("seasonYear", "")), media_type=mt, language="Japanese", genre=", ".join(d.get("genres", [])))

    def _classify_from_omdb(self, d: Dict[str, Any]) -> MediaInfo:
        t_ = d.get("Type", "").lower()
        mt = MediaType.MOVIE if t_ == "movie" else MediaType.TV_SERIES if t_ in ["series", "tv series"] else MediaType.UNKNOWN
        genre = d.get("Genre", "").lower()
        country = d.get("Country", "").lower()
        if "animation" in genre and "japan" in country:
            if mt == MediaType.TV_SERIES: mt = MediaType.ANIME_SERIES
            elif mt == MediaType.MOVIE: mt = MediaType.ANIME_MOVIE
        return MediaInfo(title=d.get("Title"), year=(d.get("Year", "") or "").split('–')[0], media_type=mt, language=d.get("Language", ""), genre=d.get("Genre", ""))

    def _classify_from_tmdb(self, d: Dict[str, Any]) -> MediaInfo:
        is_m = "title" in d
        mt = MediaType.MOVIE if is_m else MediaType.TV_SERIES
        t = d.get("title") if is_m else d.get("name")
        y = (d.get("release_date") or d.get("first_air_date") or "{}").split('-')[0]
        genres = [g.get("name", "").lower() for g in d.get("genres", [])]
        origin_countries = d.get("origin_country", [])
        if "animation" in genres and "JP" in origin_countries:
             if mt == MediaType.TV_SERIES: mt = MediaType.ANIME_SERIES
             elif mt == MediaType.MOVIE: mt = MediaType.ANIME_MOVIE
        lang = ""
        if d.get("translations"):
            et = next((t for t in d["translations"]["translations"] if t["iso_639_1"] == "en"), None)
            if et: lang = et["english_name"]
        genre_str = ", ".join([g["name"] for g in d.get("genres", [])])
        return MediaInfo(title=t, year=y, media_type=mt, language=lang, genre=genre_str)

    def _classify_from_tvdb(self, data: Dict[str, Any]) -> MediaInfo:
        title = data.get("name", "Unknown")
        year = data.get("year") or (data.get("firstAired") or "").split('-')[0]
        
        media_type = MediaType.TV_SERIES if "seasons" in data else MediaType.MOVIE

        genres = [g.get("name", "").lower() for g in data.get("genres", []) if g.get("name")]
        country = data.get("originalCountry")
        is_anime = "anime" in genres or ("animation" in genres and country == "jpn")
        
        if is_anime:
            if media_type == MediaType.MOVIE: media_type = MediaType.ANIME_MOVIE
            elif media_type == MediaType.TV_SERIES: media_type = MediaType.ANIME_SERIES
            
        lang_code = data.get("originalLanguage")
        lang_map = {"eng": "English", "jpn": "Japanese", "fra": "French", "deu": "German", "spa": "Spanish"}
        language = lang_map.get(lang_code, lang_code)
        genre_str = ", ".join([g["name"] for g in data.get("genres", [])])
        
        return MediaInfo(title=title, year=year, media_type=media_type, language=language, genre=genre_str)

class FileManager:
    def __init__(self, cfg: Config, dry_run: bool): self.cfg, self.dry_run = cfg, dry_run
    def _find_sidecar_files(self, pf: Path) -> List[Path]:
        s, st = [], pf.stem
        for sib in pf.parent.iterdir():
            if sib != pf and sib.stem == st and sib.suffix.lower() in self.cfg.SIDECAR_EXTENSIONS: s.append(sib)
        return s
    def ensure_dir(self, p: Path) -> bool:
        if self.dry_run:
            logging.info(f"DRY RUN: Would ensure directory '{p}' exists.")
            return True
        if not p: logging.error("Destination directory path is not set."); return False
        if not p.exists():
            try: p.mkdir(parents=True, exist_ok=True)
            except Exception as e: logging.error(f"Could not create directory '{p}': {e}"); return False
        return True
    def move_file_group(self, fg: List[Path], dd: Path) -> bool:
        if self.dry_run:
            logging.info(f"DRY RUN: Would ensure directory '{dd}' exists.")
            for ftm in fg:
                lp = "DRY RUN:"
                if ftm != fg[0]: lp += " (sidecar)"
                logging.info(f"{lp}: '{ftm.name}' -> '{dd.name}'")
            return True
        try:
            if not dd.exists():
                dd.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logging.error(f"FATAL ERROR: Destination path '{dd}' is not accessible. Error: {e}")
            return False
        pf, all_ok = fg[0], True
        for ftm in fg:
            t = dd / ftm.name
            if str(ftm.resolve()) == str(t.resolve()):
                logging.info(f"Skipping move: '{ftm.name}' is already in correct location.")
                continue
            if t.exists():
                logging.warning(f"SKIPPED: File '{t.name}' already exists in '{dd.name}'.")
                continue
            lp = "Moved"
            if ftm != pf: lp += " (sidecar)"
            logging.info(f"{lp}: '{ftm.name}' -> '{dd.name}'")
            try:
                shutil.move(str(ftm), str(t))
            except Exception as e:
                logging.error(f"ERROR moving file '{ftm.name}': {e}")
                all_ok = False
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
        if self.dry_run: return True
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
            clean_title, _ = TitleCleaner.extract_search_terms(term, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
            info.media_type, info.title, info.year = MediaType.UNKNOWN, clean_title, year_in_file
        return info
        
    def sort_item(self, item: Path, override_name: Optional[str] = None):
        if item.suffix.lower() in self.cfg.SIDECAR_EXTENSIONS: return
        filename_context = item.name
        
        if override_name:
            search_term = override_name
            initial_info = self.classifier.classify_media(override_name, self.cfg.CUSTOM_STRINGS_TO_REMOVE, filename_context)
        else:
            is_sub = item.parent.resolve() != self.cfg.get_path('SOURCE_DIR').resolve()
            search_term = item.parent.name if is_sub else item.name
            initial_info = self.classifier.classify_media(search_term, self.cfg.CUSTOM_STRINGS_TO_REMOVE, filename_context)
            if initial_info.media_type == MediaType.UNKNOWN and is_sub and item.name.lower() != search_term.lower():
                logging.warning(f"Folder search for '{search_term}' failed. Trying filename: '{item.name}'")
                fb_info = self.classifier.classify_media(item.name, self.cfg.CUSTOM_STRINGS_TO_REMOVE, filename_context)
                if fb_info.media_type != MediaType.UNKNOWN:
                    logging.info("Filename fallback successful.")
                    initial_info, search_term = fb_info, item.name
                else:
                    logging.warning(f"Filename fallback for '{item.name}' also failed.")
        
        info = self._validate_api_result(item, search_term, initial_info)
        files_to_move = [item] + self.fm._find_sidecar_files(item)
        stats = self.stats
        logging.info(f"Class: {info.media_type.value} | Title: '{info.get_folder_name()}'" + (f" | Found {len(files_to_move) - 1} sidecars." if len(files_to_move) > 1 else ""))
        
        if info.media_type == MediaType.UNKNOWN:
            if self.cfg.CLEANUP_MODE_ENABLED: return
            mpath = self._get_mismatched_path()
            if not mpath: logging.error("Mismatched dir not set. Skipping."); stats['errors'] += 1; return
            is_series = TitleCleaner.extract_season_info(item.name) is not None
            if is_series:
                fdest = self.cfg.FALLBACK_SHOW_DESTINATION
                if fdest == "ignore": return
                dmap = {"tv": self.cfg.get_path('TV_SHOWS_DIR'), "anime": self.cfg.get_path('ANIME_SERIES_DIR'), "mismatched": mpath}
                bdir = dmap.get(fdest)
                if not bdir: logging.error(f"Fallback dir '{fdest}' not set."); stats['errors'] += 1; return
                df = bdir / info.get_folder_name() / f"Season {TitleCleaner.extract_season_info(item.name) or 1:02d}"
                if self.fm.move_file_group(files_to_move, df):
                    key = 'tv' if fdest == 'tv' else 'anime_series' if fdest == 'anime' else 'unknown'
                    stats[key] = stats.get(key, 0) + 1
                else: stats['errors'] += 1
            else:
                if self.fm.move_file_group(files_to_move, mpath):
                    stats['unknown'] = stats.get('unknown', 0) + 1
                    if self.cfg.NOTIFY_ON_MISMATCH:
                        send_notification(title="File Needs Review", message=f"'{item.name}' was moved to the Mismatched folder.")
                else: stats['errors'] += 1
            return
            
        type_enabled_map = { MediaType.MOVIE: self.cfg.MOVIES_ENABLED, MediaType.TV_SERIES: self.cfg.TV_SHOWS_ENABLED, MediaType.ANIME_MOVIE: self.cfg.ANIME_MOVIES_ENABLED, MediaType.ANIME_SERIES: self.cfg.ANIME_SERIES_ENABLED }
        if not type_enabled_map.get(info.media_type, True): return
        
        base_dir_map = { MediaType.MOVIE: self.cfg.get_path('MOVIES_DIR'), MediaType.TV_SERIES: self.cfg.get_path('TV_SHOWS_DIR'), MediaType.ANIME_MOVIE: self.cfg.get_path('ANIME_MOVIES_DIR'), MediaType.ANIME_SERIES: self.cfg.get_path('ANIME_SERIES_DIR') }
        base_dir = item.parent if self.cfg.CLEANUP_MODE_ENABLED else base_dir_map.get(info.media_type)
        
        if info.media_type == MediaType.MOVIE and self.cfg.get_path('SPLIT_MOVIES_DIR') and self.cfg.LANGUAGES_TO_SPLIT and not self.cfg.CLEANUP_MODE_ENABLED:
            movie_langs_full = [lang.strip().lower() for lang in (info.language or "").split(',')]
            split_lang_codes = [code.strip().lower() for code in self.cfg.LANGUAGES_TO_SPLIT]
            should_split, matched_code, matched_reason = False, "", ""
            for code in split_lang_codes:
                if any(full_lang.startswith(code) for full_lang in movie_langs_full):
                    should_split, matched_code, matched_reason = True, code, f"API language '{info.language}'"
                    break
            if not should_split:
                original_filename_lower = item.name.lower()
                for lang_name in ['french', 'francais', 'français']:
                    if lang_name in original_filename_lower and 'fr' in split_lang_codes:
                        should_split, matched_code, matched_reason = True, 'fr', f"filename keyword '{lang_name}'"
                        break
                if not should_split:
                    for custom_str in self.cfg.CUSTOM_STRINGS_TO_REMOVE:
                        if custom_str.lower() in original_filename_lower and 'fr' in split_lang_codes:
                             should_split, matched_code, matched_reason = True, 'fr', f"filename keyword '{custom_str}'"
                             break
            if should_split:
                logging.info(f"🔵⚪🔴 Movie matches split rule '{matched_code}' based on {matched_reason}. Moving to split directory.")
                base_dir = self.cfg.get_path('SPLIT_MOVIES_DIR')

        if not base_dir: logging.error(f"Target dir for {info.media_type.value} not set."); stats['errors'] += 1; return
        
        if info.media_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]:
            key = 'anime_movies' if info.media_type == MediaType.ANIME_MOVIE else 'movies'
            if base_dir == self.cfg.get_path('SPLIT_MOVIES_DIR'): key = 'split_lang_movies'
            dest_folder = base_dir / info.get_folder_name()
            if self.cfg.CLEANUP_MODE_ENABLED and dest_folder.resolve() == item.parent.resolve(): stats[key] = stats.get(key, 0) + 1; return
            if self.fm.move_file_group(files_to_move, dest_folder): stats[key] = stats.get(key, 0) + 1
            else: stats['errors'] += 1
        elif info.media_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
            key = 'anime_series' if info.media_type == MediaType.ANIME_SERIES else 'tv'
            dest_folder = base_dir / info.get_folder_name() / f"Season {TitleCleaner.extract_season_info(item.name) or 1:02d}"
            if self.cfg.CLEANUP_MODE_ENABLED and dest_folder.resolve() == item.parent.resolve(): stats[key] = stats.get(key, 0) + 1; return
            if self.fm.move_file_group(files_to_move, dest_folder): stats[key] = stats.get(key, 0) + 1
            else: stats['errors'] += 1

    def reorganize_folder_structure(self, target_path: Path, file_list: Optional[List[Path]] = None):
        self.is_processing = True
        self.stop_event.clear()
        try:
            logging.info(f"--- Starting Folder Reorganization for: '{target_path}' ---")
            files_to_process = file_list or [p for ext in self.cfg.SUPPORTED_EXTENSIONS for p in target_path.glob(f'**/*{ext}') if p.is_file()]
            total_files = len(files_to_process)
            if self.progress_callback: self.progress_callback(0, total_files)
            for i, item in enumerate(files_to_process):
                if self.stop_event.is_set(): logging.warning("Reorganization run aborted."); break
                try:
                    logging.info(f"Analyzing: '{item.relative_to(target_path)}'")
                    info = self.classifier.classify_media(item.name, self.cfg.CUSTOM_STRINGS_TO_REMOVE, item.name)
                    if info.media_type == MediaType.UNKNOWN:
                        logging.warning(f"SKIPPED: Could not identify '{item.name}', cannot determine destination folder.")
                        continue
                    if info.media_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]:
                        dest_folder = target_path / info.get_folder_name()
                    elif info.media_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
                        season = TitleCleaner.extract_season_info(item.name) or 1
                        dest_folder = target_path / info.get_folder_name() / f"Season {season:02d}"
                    else: continue
                    if dest_folder.resolve() == item.parent.resolve():
                        logging.info(f"Already in correct location: '{item.name}'")
                        continue
                    self.fm.move_file_group([item] + self.fm._find_sidecar_files(item), dest_folder)
                except Exception as e:
                    logging.error(f"Fatal error reorganizing '{item.name}': {e}", exc_info=True)
                finally:
                    if self.progress_callback: self.progress_callback(i + 1, total_files)
        finally:
            self.is_processing = False
            logging.info("--- Folder Reorganization Finished ---")
            if self.progress_callback: self.progress_callback(len(files_to_process), len(files_to_process))

    def generate_rename_plan(self, target_path: Path, file_list: List[Path], quick_clean_only: bool) -> Dict[Path, Path]:
        self.is_processing = True
        self.stop_event.clear()
        rename_plan = {}
        total_files = len(file_list)
        log_prefix = "Quick Clean" if quick_clean_only else "API-Based Rename"
        try:
            logging.info(f"--- Generating Rename Plan ({log_prefix}) for {total_files} files ---")
            if self.progress_callback: self.progress_callback(0, total_files)
            for i, item in enumerate(file_list):
                if self.stop_event.is_set(): logging.warning("Rename plan generation aborted."); break
                logging.info(f"Analyzing: '{item.relative_to(target_path)}'")
                if quick_clean_only:
                    new_stem = TitleCleaner.quick_clean_stem(item.stem, self.cfg.CUSTOM_STRINGS_TO_REMOVE)
                else: 
                    is_in_subdir = item.parent.resolve() != target_path.resolve()
                    search_term = item.parent.name if is_in_subdir else item.name
                    info = self.classifier.classify_media(search_term, self.cfg.CUSTOM_STRINGS_TO_REMOVE, item.name)
                    if info.media_type == MediaType.UNKNOWN and is_in_subdir and item.name.lower() != search_term.lower():
                        logging.warning(f"Folder search for '{search_term}' failed. Trying filename stem: '{item.name}'")
                        info = self.classifier.classify_media(item.name, self.cfg.CUSTOM_STRINGS_TO_REMOVE, item.name)
                        if info.media_type != MediaType.UNKNOWN: logging.info("Filename stem fallback successful.")
                    if info.media_type == MediaType.UNKNOWN:
                        logging.warning(f"SKIPPED: Could not identify '{item.name}' via API, cannot generate clean name."); continue
                    if info.media_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]:
                        new_stem = info.get_folder_name()
                    elif info.media_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
                        s = TitleCleaner.extract_season_info(item.name)
                        e = TitleCleaner.extract_episode_info(item.name)
                        if s and e: new_stem = f"{info.title} - S{s:02d}E{e:02d}"
                        elif s: new_stem = f"{info.title} - S{s:02d}"
                        else: logging.warning(f"SKIPPED: Could not extract season/episode from '{item.name}'."); continue
                sanitized_stem = re.sub(r'[<>:"/\\|?*]', '', new_stem).strip()
                if not sanitized_stem or sanitized_stem == item.stem:
                    logging.info(f"No changes needed for '{item.name}'.")
                    continue
                new_path = item.parent / f"{sanitized_stem}{item.suffix}"
                rename_plan[item] = new_path
                logging.info(f"Plan: '{item.name}' -> '{new_path.name}'")
                if self.progress_callback: self.progress_callback(i + 1, total_files)
        finally:
            self.is_processing = False
            logging.info("--- Rename Plan Generation Finished ---")
            if self.progress_callback: self.progress_callback(total_files, total_files)
        return rename_plan

    def rename_files_in_library(self, rename_plan: Dict[Path, Path]):
        self.is_processing = True
        self.stop_event.clear()
        total_files = len(rename_plan)
        try:
            logging.info(f"--- Applying Rename for {total_files} files ---")
            if self.progress_callback: self.progress_callback(0, total_files)
            if not rename_plan: logging.warning("Rename plan is empty. Nothing to do."); return
            for i, (old_path, new_path) in enumerate(rename_plan.items()):
                if self.stop_event.is_set(): logging.warning("Rename execution aborted."); break
                file_group_originals = [old_path] + self.fm._find_sidecar_files(old_path)
                new_stem = new_path.stem
                for file_to_rename in file_group_originals:
                    if file_to_rename != old_path and file_to_rename in rename_plan: continue
                    new_name = f"{new_stem}{file_to_rename.suffix}"
                    new_target_path = file_to_rename.parent / new_name
                    if file_to_rename.resolve() == new_target_path.resolve(): continue
                    if new_target_path.exists():
                        logging.warning(f"SKIPPED: A file named '{new_name}' already exists.")
                        continue
                    log_prefix = "DRY RUN:" if self.dry_run else "Renamed"
                    logging.info(f"{log_prefix}: '{file_to_rename.name}' -> '{new_name}'")
                    if not self.dry_run:
                        try: shutil.move(str(file_to_rename), str(new_target_path))
                        except Exception as ex: logging.error(f"ERROR renaming '{file_to_rename.name}': {ex}")
                if self.progress_callback: self.progress_callback(i + 1, total_files)
        finally:
            self.is_processing = False
            logging.info("--- Filename Rename Finished ---")
            if self.progress_callback: self.progress_callback(total_files, total_files)
    
    def process_source_directory(self):
        self.is_processing = True
        try:
            self.stop_event.clear()
            self.stats = {k: 0 for k in ['processed','movies','tv','anime_movies','anime_series','split_lang_movies','unknown','errors', 'mismatched', 'anime']}
            source_dir = self.cfg.get_path('SOURCE_DIR')
            if not source_dir or not source_dir.exists() or not self.ensure_target_dirs():
                logging.error("Source/Target dir validation failed.")
                return
            logging.info("Starting deep scan of source directory...")
            all_files = [p for ext in self.cfg.SUPPORTED_EXTENSIONS.union(self.cfg.SIDECAR_EXTENSIONS) for p in source_dir.glob(f'**/*{ext}') if p.is_file()]
            mpath = self._get_mismatched_path()
            if mpath and mpath.exists():
                all_files = [f for f in all_files if not f.resolve().is_relative_to(mpath.resolve())]
            media_files = [f for f in all_files if f.suffix.lower() in self.cfg.SUPPORTED_EXTENSIONS]
            total = len(media_files)
            if self.progress_callback: self.progress_callback(0, total)
            logging.info(f"Found {total} primary media files to process.")
            for i, fp in enumerate(media_files):
                if self.stop_event.is_set(): logging.warning("Sort run aborted."); break
                self.stats['processed'] += 1
                try: self.sort_item(fp)
                except Exception as e: self.stats['errors'] += 1; logging.error(f"Fatal error processing '{fp.name}': {e}", exc_info=True)
                if self.progress_callback: self.progress_callback(i + 1, total)
            if not self.stop_event.is_set() and not self.cfg.CLEANUP_MODE_ENABLED:
                self.cleanup_empty_dirs(source_dir)
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
        while not self.stop_event.wait(timeout=interval):
            if watcher.check_for_changes():
                logging.info("Changes detected! Starting new sort...")
                self.process_source_directory() 
                if self.stop_event.is_set():
                    logging.warning("Watch loop interrupted."); break
                logging.info("Processing complete. Resuming watch.")
            else:
                logging.info("No new files found. Continuing to watch.")
        logging.info("Watch mode stopped.")

    def log_summary(self):
        summary = f"\n\n--- PROCESSING SUMMARY ---\n"
        for k, v in self.stats.items(): 
            if v > 0: summary += f"{k.replace('_',' ').title():<20}: {v}\n"
        summary += f"--------------------------\n"
        logging.info(summary)
