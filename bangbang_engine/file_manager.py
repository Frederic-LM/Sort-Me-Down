# bangbang_engine/file_manager.py
import logging
import os
import shutil
from pathlib import Path
from typing import List

from .config import Config

class FileManager:
    def __init__(self, cfg: Config, dry_run: bool):
        self.cfg = cfg
        self.dry_run = dry_run

    def _find_sidecar_files(self, primary_file: Path) -> List[Path]:
        sidecars, stem = [], primary_file.stem
        for sibling in primary_file.parent.iterdir():
            if sibling != primary_file and sibling.stem == stem and sibling.suffix.lower() in self.cfg.SIDECAR_EXTENSIONS:
                sidecars.append(sibling)
        return sidecars

    def ensure_dir(self, path: Path) -> bool:
        if self.dry_run:
            logging.info(f"DRY RUN: Would ensure directory '{path}' exists.")
            return True
        if not path:
            logging.error("Destination directory path is not set.")
            return False
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logging.error(f"Could not create directory '{path}': {e}")
                return False
        return True

    def move_file_group(self, file_group: List[Path], dest_dir: Path) -> bool:
        if self.dry_run:
            logging.info(f"DRY RUN: Would ensure directory '{dest_dir}' exists.")
            for file_to_move in file_group:
                log_prefix = "DRY RUN:"
                if file_to_move != file_group[0]:
                    log_prefix += " (sidecar)"
                logging.info(f"{log_prefix}: '{file_to_move.name}' -> '{dest_dir.name}'")
            return True
        
        try:
            if not dest_dir.exists():
                dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logging.error(f"FATAL ERROR: Destination path '{dest_dir}' is not accessible. Error: {e}")
            return False

        primary_file, all_ok = file_group[0], True
        for file_to_move in file_group:
            target = dest_dir / file_to_move.name
            if str(file_to_move.resolve()) == str(target.resolve()):
                logging.info(f"Skipping move: '{file_to_move.name}' is already in correct location.")
                continue
            if target.exists():
                logging.warning(f"SKIPPED: File '{target.name}' already exists in '{dest_dir.name}'.")
                continue
            
            log_prefix = "Moved"
            if file_to_move != primary_file:
                log_prefix += " (sidecar)"
            logging.info(f"{log_prefix}: '{file_to_move.name}' -> '{dest_dir.name}'")
            try:
                shutil.move(str(file_to_move), str(target))
            except Exception as e:
                logging.error(f"ERROR moving file '{file_to_move.name}': {e}")
                all_ok = False
        return all_ok

    def delete_file_group(self, primary_file: Path):
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
    def __init__(self, config: Config):
        self.config = config
        self.last_mtime = 0
        self._scan()

    def _scan(self):
        if (sd := self.config.get_path('SOURCE_DIR')) and sd.exists():
            self.last_mtime = sd.stat().st_mtime

    def check_for_changes(self) -> bool:
        if (sd := self.config.get_path('SOURCE_DIR')) and sd.exists():
            current_mtime = sd.stat().st_mtime
            if current_mtime > self.last_mtime:
                self.last_mtime = current_mtime
                return True
        return False