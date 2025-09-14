# bangbang_engine/utils.py
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Set, Tuple

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = Path(sys._MEIPASS)
    except Exception:
        base_path = Path(sys.argv[0]).parent.absolute()
        
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
        
def setup_logging(log_file: Path, log_to_console: bool = False):
    """Configures the logging for the application."""
    handlers = [logging.FileHandler(log_file, encoding='utf-8')]
    if log_to_console:
        handlers.append(logging.StreamHandler(sys.stdout))
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
        force=True
    )

class TitleCleaner:
    METADATA_BREAKPOINT_PATTERN = re.compile(r'('
                                           r'\s[\(\[]?\d{4}[\)\]]?\b'
                                           r'|\s[Ss]\d{1,2}[Ee]\d{1,2}\b'
                                           r'|\s[Ss]\d{1,2}\b'
                                           r'|\sSeason\s\d{1,2}\b'
                                           r'|\s\d{3,4}p\b'
                                           r'|\s(WEBRip|BluRay|BDRip|DVDRip|HDRip|WEB-DL|HDTV|CR)\b'
                                           r'|\s(x264|x265|H\.?264|H\.?265|HEVC|AVC|AAC2\.0)\b'
                                           r'|\s(Msub)\b'
                                           r')', re.IGNORECASE)

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
            if m := re.search(p, filename, re.IGNORECASE):
                return int(m.group(1))
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
        cy = datetime.now().year
        py = [m for m in ms if 1900 <= int(m) <= cy + 2]
        return py[-1] if py else None
