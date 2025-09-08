# bangbang_engine/config.py
import json
import logging
from pathlib import Path
from typing import Optional

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
        p = getattr(self, key)
        return Path(p) if p else None

    def to_dict(self):
        d = {}
        [d.update({k: list(v) if isinstance(v, set) else v}) for k, v in self.__dict__.items() if not k.startswith('_')]
        return d

    @classmethod
    def from_dict(cls, data):
        c = cls()
        for k, v in data.items():
            if hasattr(c, k):
                setattr(c, k, set(v) if isinstance(getattr(c, k), set) else v)
        return c

    def save(self, path: Path):
        try:
            with open(path, 'w') as f:
                json.dump(self.to_dict(), f, indent=4)
        except Exception as e:
            logging.error(f"Failed to save config to '{path}': {e}")

    @classmethod
    def load(cls, path: Path):
        if not path.exists():
            return cls()
        try:
            with open(path, 'r') as f:
                content = f.read()
            if not content.strip():
                return cls()
            return cls.from_dict(json.loads(content))
        except Exception as e:
            logging.error(f"Error loading config from '{path}': {e}. Loading defaults.")
            return cls()

    def validate(self) -> (bool, str):
        if self.API_PROVIDER == "omdb" and (not self.OMDB_API_KEY or self.OMDB_API_KEY == "yourkey"):
            return False, "Primary provider (OMDb) API key is not configured."
        if self.API_PROVIDER == "tmdb" and (not self.TMDB_API_KEY or self.TMDB_API_KEY == "yourkey"):
            return False, "Primary provider (TMDB) API key is not configured."
        if self.API_PROVIDER == "tvdb" and (not self.TVDB_API_KEY or self.TVDB_API_KEY == "yourkey"):
            return False, "Primary provider (TVDB) API key is not configured."
        sd = self.get_path('SOURCE_DIR')
        if not sd or not sd.exists():
            return False, f"Source directory not found or not set: {sd}"
        return True, "Validation successful."