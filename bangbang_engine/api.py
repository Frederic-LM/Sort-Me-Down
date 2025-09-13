# bangbang_engine/api.py
import logging
import re
import threading
import time
from time import sleep
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from .config import Config
from .models import MediaInfo, MediaType
from .utils import TitleCleaner

class APIClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'SortMeDown/Engine/6.7.1'})
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
            params = {"apikey": self.config.OMDB_API_KEY, "t": title}
            if year:
                params["y"] = year
            r = self.session.get(self.config.OMDB_URL, params=params, timeout=10)
            r.raise_for_status()
            d = r.json()
            if d.get("Response") == "True":
                return d
            
            # Fallback to search query if direct title match fails
            params.pop("t", None)
            params.pop("y", None)
            params["s"] = title
            r = self.session.get(self.config.OMDB_URL, params=params, timeout=10)
            r.raise_for_status()
            d = r.json()
            if d.get("Response") == "True" and "Search" in d:
                # Get details of the first search result
                id_params = {"i": d["Search"][0]["imdbID"], "apikey": self.config.OMDB_API_KEY}
                id_r = self.session.get(self.config.OMDB_URL, params=id_params, timeout=10)
                return id_r.json()
        except requests.RequestException as e:
            logging.error(f"OMDb API request failed for '{title}': {e}")
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
            if year: # Try to find a result that matches the year
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
        except requests.RequestException as e:
            logging.error(f"TMDB API request failed for '{title}': {e}")
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
            if m:
                logging.info(f"AniList found match for: {title}")
                return m
        except requests.RequestException as e:
            logging.error(f"AniList API request failed for '{title}': {e}")
        return None

class MediaClassifier:
    def __init__(self, config: Config):
        self.api_client = APIClient(config)

    def _detect_content_hints(self, filename: str, clean_name: str) -> Dict[str, bool]:
        hints = {'likely_anime': False, 'likely_series': False, 'likely_movie': False}
        anime_keywords = ['subbed', 'dubbed', 'vostfr', 'anime']
        # BUG FIX: Removed generic '[.*]' pattern which was too aggressive.
        anime_patterns = [r'\b(OVA|ONA|BD|BDRip)\b'] 
        
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

class MediaClassifier:
    def __init__(self, config: Config):
        # This now correctly takes the config and creates its own APIClient
        self.api_client = APIClient(config)

    def _detect_content_hints(self, filename: str, clean_name: str) -> Dict[str, bool]:
        hints = {'likely_anime': False, 'likely_series': False, 'likely_movie': False}
        anime_keywords = ['subbed', 'dubbed', 'vostfr', 'anime']
        # BUG FIX: Removed generic '[.*]' pattern which was too aggressive.
        anime_patterns = [r'\b(OVA|ONA|BD|BDRip)\b'] 
        
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

        if "animation" in genre:
            if mt == MediaType.TV_SERIES: mt = MediaType.ANIME_SERIES
            elif mt == MediaType.MOVIE: mt = MediaType.ANIME_MOVIE
            
        return MediaInfo(title=d.get("Title"), year=(d.get("Year", "") or "").split('–')[0], media_type=mt, language=d.get("Language", ""), genre=d.get("Genre", ""))

    def _classify_from_tmdb(self, d: Dict[str, Any]) -> MediaInfo:
        is_m = "title" in d
        mt = MediaType.MOVIE if is_m else MediaType.TV_SERIES
        t = d.get("title") if is_m else d.get("name")
        y = (d.get("release_date") or d.get("first_air_date") or "{}").split('-')[0]
        genres = [g.get("name", "").lower() for g in d.get("genres", [])]

        if "animation" in genres:
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
        
        is_anime = "anime" in genres or "animation" in genres
        
        if is_anime:
            if media_type == MediaType.MOVIE: media_type = MediaType.ANIME_MOVIE
            elif media_type == MediaType.TV_SERIES: media_type = MediaType.ANIME_SERIES
            
        lang_code = data.get("originalLanguage")
        lang_map = {"eng": "English", "jpn": "Japanese", "fra": "French", "deu": "German", "spa": "Spanish"}
        language = lang_map.get(lang_code, lang_code)
        genre_str = ", ".join([g["name"] for g in data.get("genres", [])])
        
        return MediaInfo(title=title, year=year, media_type=media_type, language=language, genre=genre_str)
