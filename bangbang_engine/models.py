# bangbang_engine/models.py
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import re

class MediaType(Enum):
    MOVIE = "movie"
    TV_SERIES = "series"
    ANIME_MOVIE = "anime_movie"
    ANIME_SERIES = "anime_series"
    UNKNOWN = "unknown"

@dataclass
class MediaInfo:
    title: str
    year: Optional[str]
    media_type: MediaType
    language: Optional[str]
    genre: Optional[str]
    season: Optional[int] = None

    def get_folder_name(self) -> str:
        if not self.title:
            return "Unknown"
        folder_title = re.sub(r'[<>:"/\\|?*]', '', self.title).strip()
        if self.year and self.year not in folder_title:
            return f"{folder_title} ({self.year})"
        return folder_title
