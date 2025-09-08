# bangbang_engine/bangbang.py
import logging
import os
import re
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .api import MediaClassifier
from .config import Config
from .file_manager import DirectoryWatcher, FileManager
from .models import MediaInfo, MediaType
from .utils import TitleCleaner, send_notification

class MediaSorter:
    def __init__(self, cfg: Config, dry_run: bool = False, progress_callback: Optional[Callable[[int, int], None]] = None):
        self.cfg = cfg
        self.dry_run = dry_run
        self.progress_callback = progress_callback
        self.classifier = MediaClassifier(cfg)
        self.fm = FileManager(cfg, dry_run)
        self.stats = {}
        self.stop_event = threading.Event()
        self.is_processing = False

    def signal_stop(self):
        self.stop_event.set()
        logging.info("Stop signal received. Finishing current item...")

    def force_move_item(self, item: Path, folder_name: str, media_type: MediaType, is_split_lang_override: bool = False):
        logging.info(f"FORCE MOVE: Manually classifying '{item.name}' as {media_type.value} into folder '{folder_name}'.")
        files_to_move = [item] + self.fm._find_sidecar_files(item)
        
        dir_map = {
            MediaType.MOVIE: self.cfg.get_path('MOVIES_DIR'), 
            MediaType.TV_SERIES: self.cfg.get_path('TV_SHOWS_DIR'),
            MediaType.ANIME_MOVIE: self.cfg.get_path('ANIME_MOVIES_DIR'), 
            MediaType.ANIME_SERIES: self.cfg.get_path('ANIME_SERIES_DIR')
        }
        base_dir = dir_map.get(media_type)

        if media_type == MediaType.MOVIE and is_split_lang_override and self.cfg.SPLIT_MOVIES_DIR:
            base_dir = self.cfg.get_path('SPLIT_MOVIES_DIR')
            logging.info("Split language movie override selected.")
        
        if not base_dir:
            logging.error(f"Target directory for {media_type.value} is not set. Cannot force move.")
            return

        clean_folder_name = re.sub(r'[<>:"/\\|?*]', '', folder_name).strip()
        dest_folder = base_dir / clean_folder_name
        if media_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
            dest_folder = dest_folder / f"Season {TitleCleaner.extract_season_info(item.name) or 1:02d}"
        
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
        if item.suffix.lower() in self.cfg.SIDECAR_EXTENSIONS:
            return
        
        filename_context = item.name
        search_term = ""
        initial_info = MediaInfo(title="", year=None, media_type=MediaType.UNKNOWN, language=None, genre=None)

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
            self._handle_unknown(item, info, files_to_move)
            return

        type_enabled_map = {
            MediaType.MOVIE: self.cfg.MOVIES_ENABLED, 
            MediaType.TV_SERIES: self.cfg.TV_SHOWS_ENABLED,
            MediaType.ANIME_MOVIE: self.cfg.ANIME_MOVIES_ENABLED, 
            MediaType.ANIME_SERIES: self.cfg.ANIME_SERIES_ENABLED
        }
        if not type_enabled_map.get(info.media_type, True):
            return

        base_dir_map = {
            MediaType.MOVIE: self.cfg.get_path('MOVIES_DIR'), 
            MediaType.TV_SERIES: self.cfg.get_path('TV_SHOWS_DIR'),
            MediaType.ANIME_MOVIE: self.cfg.get_path('ANIME_MOVIES_DIR'), 
            MediaType.ANIME_SERIES: self.cfg.get_path('ANIME_SERIES_DIR')
        }
        base_dir = item.parent if self.cfg.CLEANUP_MODE_ENABLED else base_dir_map.get(info.media_type)

        if info.media_type == MediaType.MOVIE and not self.cfg.CLEANUP_MODE_ENABLED:
            base_dir = self._get_split_language_dir(item, info) or base_dir

        if not base_dir:
            logging.error(f"Target dir for {info.media_type.value} not set.")
            stats['errors'] += 1
            return
        
        if info.media_type in [MediaType.MOVIE, MediaType.ANIME_MOVIE]:
            self._move_movie(item, info, files_to_move, base_dir)
        elif info.media_type in [MediaType.TV_SERIES, MediaType.ANIME_SERIES]:
            self._move_series(item, info, files_to_move, base_dir)

    def _handle_unknown(self, item: Path, info: MediaInfo, files_to_move: List[Path]):
        stats = self.stats
        if self.cfg.CLEANUP_MODE_ENABLED: return
        
        mpath = self._get_mismatched_path()
        if not mpath:
            logging.error("Mismatched dir not set. Skipping.")
            stats['errors'] += 1
            return
        
        is_series = TitleCleaner.extract_season_info(item.name) is not None
        if is_series:
            fdest = self.cfg.FALLBACK_SHOW_DESTINATION
            if fdest == "ignore": return
            
            dmap = {"tv": self.cfg.get_path('TV_SHOWS_DIR'), "anime": self.cfg.get_path('ANIME_SERIES_DIR'), "mismatched": mpath}
            bdir = dmap.get(fdest)
            if not bdir:
                logging.error(f"Fallback dir '{fdest}' not set.")
                stats['errors'] += 1
                return
            
            df = bdir / info.get_folder_name() / f"Season {TitleCleaner.extract_season_info(item.name) or 1:02d}"
            if self.fm.move_file_group(files_to_move, df):
                key = 'tv' if fdest == 'tv' else 'anime_series' if fdest == 'anime' else 'unknown'
                stats[key] = stats.get(key, 0) + 1
            else: stats['errors'] += 1
        else:
            if self.fm.move_file_group(files_to_move, mpath):
                stats['unknown'] = stats.get('unknown', 0) + 1
                if self.cfg.NOTIFY_ON_MISMATCH:
                    send_notification(title="File Needs Review", message=f"'{item.name}' was moved to Mismatched.")
            else:
                stats['errors'] += 1

    def _get_split_language_dir(self, item: Path, info: MediaInfo) -> Optional[Path]:
        split_dir = self.cfg.get_path('SPLIT_MOVIES_DIR')
        if not (split_dir and self.cfg.LANGUAGES_TO_SPLIT):
            return None

        movie_langs_full = [lang.strip().lower() for lang in (info.language or "").split(',')]
        split_lang_codes = [code.strip().lower() for code in self.cfg.LANGUAGES_TO_SPLIT]
        
        should_split, matched_code, matched_reason = False, "", ""
        for code in split_lang_codes:
            if any(full_lang.startswith(code) for full_lang in movie_langs_full):
                should_split, matched_code, matched_reason = True, code, f"API language '{info.language}'"
                break
        
        if not should_split:
            original_filename_lower = item.name.lower()
            # You can add more language keywords here if needed
            french_keywords = ['french', 'francais', 'français']
            if 'fr' in split_lang_codes and any(kw in original_filename_lower for kw in french_keywords):
                should_split, matched_code, matched_reason = True, 'fr', "filename keyword"

            if not should_split and any(cs.lower() in original_filename_lower for cs in self.cfg.CUSTOM_STRINGS_TO_REMOVE):
                 if 'fr' in split_lang_codes: # Example for French custom strings
                    should_split, matched_code, matched_reason = True, 'fr', "custom string keyword"
        
        if should_split:
            logging.info(f"🔵⚪🔴 Movie matches split rule '{matched_code}' based on {matched_reason}. Moving to split directory.")
            return split_dir
        return None

    def _move_movie(self, item: Path, info: MediaInfo, files_to_move: List[Path], base_dir: Path):
        stats = self.stats
        key = 'anime_movies' if info.media_type == MediaType.ANIME_MOVIE else 'movies'
        if base_dir == self.cfg.get_path('SPLIT_MOVIES_DIR'):
            key = 'split_lang_movies'
        
        dest_folder = base_dir / info.get_folder_name()
        if self.cfg.CLEANUP_MODE_ENABLED and dest_folder.resolve() == item.parent.resolve():
            stats[key] = stats.get(key, 0) + 1
            return
        
        if self.fm.move_file_group(files_to_move, dest_folder):
            stats[key] = stats.get(key, 0) + 1
        else:
            stats['errors'] += 1

    def _move_series(self, item: Path, info: MediaInfo, files_to_move: List[Path], base_dir: Path):
        stats = self.stats
        key = 'anime_series' if info.media_type == MediaType.ANIME_SERIES else 'tv'
        
        dest_folder = base_dir / info.get_folder_name() / f"Season {TitleCleaner.extract_season_info(item.name) or 1:02d}"
        if self.cfg.CLEANUP_MODE_ENABLED and dest_folder.resolve() == item.parent.resolve():
            stats[key] = stats.get(key, 0) + 1
            return

        if self.fm.move_file_group(files_to_move, dest_folder):
            stats[key] = stats.get(key, 0) + 1
        else:
            stats['errors'] += 1

    def process_source_directory(self):
        self.is_processing = True
        try:
            self.stop_event.clear()
            self.stats = {k: 0 for k in ['processed','movies','tv','anime_movies','anime_series','split_lang_movies','unknown','errors', 'mismatched', 'anime']}
            source_dir = self.cfg.get_path('SOURCE_DIR')
            if not source_dir or not source_dir.exists() or not self.ensure_target_dirs():
                logging.error("Source/Target dir validation failed.")
                self.is_processing = False
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
                if self.stop_event.is_set():
                    logging.warning("Sort run aborted.")
                    break
                self.stats['processed'] += 1
                try:
                    self.sort_item(fp)
                except Exception as e:
                    self.stats['errors'] += 1
                    logging.error(f"Fatal error processing '{fp.name}': {e}", exc_info=True)
                if self.progress_callback:
                    self.progress_callback(i + 1, total)

            if not self.stop_event.is_set() and not self.cfg.CLEANUP_MODE_ENABLED:
                self.cleanup_empty_dirs(source_dir)
            self.log_summary()
        finally:
            self.is_processing = False

    def cleanup_empty_dirs(self, path: Path):
        if self.dry_run:
            logging.info("DRY RUN: Skipping cleanup of empty directories.")
            return
        
        logging.info("Sweeping for empty directories...")
        mpath = self._get_mismatched_path()
        for dirpath, _, _ in os.walk(path, topdown=False):
            dp = Path(dirpath).resolve()
            if dp == path.resolve() or (mpath and dp == mpath.resolve()):
                continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
                    logging.info(f"Removed empty directory: {dirpath}")
            except OSError as e:
                logging.error(f"Error removing directory {dirpath}: {e}")

    def start_watch_mode(self):
        self.stop_event.clear()
        logging.info("Watch mode started. Performing initial sort...")
        self.process_source_directory()
        if self.stop_event.is_set():
            logging.info("Watch mode stopped during initial sort.")
            return
        
        watcher = DirectoryWatcher(self.cfg)
        interval = self.cfg.WATCH_INTERVAL
        logging.info(f"Initial sort complete. Now watching for changes every {interval // 60} minutes.")
        
        while not self.stop_event.wait(timeout=interval):
            if watcher.check_for_changes():
                logging.info("Changes detected! Starting new sort...")
                self.process_source_directory() 
                if self.stop_event.is_set():
                    logging.warning("Watch loop interrupted.")
                    break
                logging.info("Processing complete. Resuming watch.")
            else:
                logging.info("No new files found. Continuing to watch.")
        logging.info("Watch mode stopped.")

    def log_summary(self):
        summary = f"\n\n--- PROCESSING SUMMARY ---\n"
        for k, v in self.stats.items(): 
            if v > 0:
                summary += f"{k.replace('_',' ').title():<20}: {v}\n"
        summary += f"--------------------------\n"
        logging.info(summary)