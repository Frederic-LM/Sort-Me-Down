# cli.py
"""
v6.4.0
- FEATURE: TVDB API Integration
- FEATURE: Improved smart API provider logic

v6.2
installer and portable suport

v6.1
Access to reorganize fucntions:
for ex: python cli.py reorganize-folders --target-dir "D:/My Media Library/Movies" --dry-run
see python cli.py reorganize-folders --help

v6.0.1
small rafinement for daemonisation

! MAJOR CHANGES !
SortMeDown - Command-Line Interface (v6.0.0)
============================================
This script provides a command-line interface to the SortMeDown engine.
It uses an action-based command structure (`sort` or `watch`) to clearly
define the desired operation.
! MAJOR CHANGES !
All settings are read from `config.json` by default. Optional flags can
be used to override these settings for a single run.

--------------------
COMMANDS
--------------------
  sort                 Perform a single, one-time sort of the source directory.
  watch                Start the watchdog to monitor the source directory for changes.
  reorganize-folders   Organize an existing library into a clean folder structure.
  rename-files         Rename files within an existing library to a clean format.

Type `python cli.py [command] --help` for more information on a specific command.
"""

import argparse
import sys
import logging
import os
from pathlib import Path

# Import the shared engine components
from bangbang import Config, MediaSorter, setup_logging

APP_NAME = "SortMeDown"

def get_config_path() -> Path:
    try:
        if hasattr(sys, '_MEIPASS'):
            portable_path = Path(sys.executable).parent / "config.json"
        else:
            portable_path = Path(__file__).parent / "config.json"
        
        if portable_path.exists():
            print(f"INFO: Running in PORTABLE mode. Using config at: {portable_path}")
            return portable_path
    except Exception:
        pass

    if sys.platform == "win32": app_data_dir = Path(os.getenv("APPDATA")) / APP_NAME
    elif sys.platform == "darwin": app_data_dir = Path.home() / "Library" / "Application Support" / APP_NAME
    else: app_data_dir = Path.home() / ".config" / APP_NAME
        
    app_data_dir.mkdir(parents=True, exist_ok=True)
    return app_data_dir / "config.json"

ASCII_ART = """
#    █████  ░█████   ██▀███  ▄▄▄█████▓    ████▄ ▄███▓▓█████    ▓█████▄  ░█████   █     █░█████▄    █ 
#  ░██    ░ ░██░  ██░▓██ ░ ██░▓  ██░ ▓░   ▓██░▀█▀ ██░▓█   ▀    ░██▀ ██▌░██░  ██░▓█░ █ ░█░██ ▀█   █ 
#  ░ ▓██▄   ░██░  ██░▓██ ░▄█ ░▄██ ░ ▓██░ ░░   ▓██    ▓████░░░██   █▌░██░  ██░░█░ █ ░█▓██  ▀█ ██░
#    ░   ██░░██   ██░▒██▀▀█▄  ░ ▓██▓ ░    ░██    ░██ ░▓█  ▄    ░▓█▄   ▌░██   ██░░█░ █ ░█▓██░  ▐▌██░
#  ░██████░░ ████▓░░██▓ ░██▓  ░██▒░   ░██░   ░██░░░███▒▒██    ░░████▓ ░ ████▓░░██▓░██░▓██░   ▓███░
#  ░ ░▓░ ░ ░ ░░▒░░░ ░ ▒░   ░  ░▓░      ░ ░░   ░  ░░░ ░▒ ░    ░░▓  ░ ░ ░▒░░░ ░ ▒░   ░ ░ 
#  ░ ░░  ░ ░  ░ ░ ░░   ░    ░░   ░░ ░   ░    ░ ░  ░   ░ ░    ░ ░░   ░ ░ ░ ░░   ░ ░░
#  ░  ░  ░  ░ ░ ░    ░░   ░   ░         ░      ░         ░      ░      ░ ░      ░        ░ ░      ░      6.4.0 ░ 
#        ░      ░ ░      ░░   CLI Media Sorter Script  ░      ░  ░      ░        ░ ░      ░        ░   
#                                                               ░                                    
"""

def main():
    SCRIPT_DIR = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="SortMeDown Media Sorter", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--config", type=str, default=str(get_config_path()), help="Path to the configuration file.")
    parser.add_argument("--version", action="version", version="SortMeDown CLI 6.4.0")

    subparsers = parser.add_subparsers(dest='command', required=True, help="The action to perform.")

    sort_parser = subparsers.add_parser('sort', help="Perform a single, one-time sort of the source directory.")
    sort_parser.add_argument("--dry-run", action="store_true", help="Preview actions without moving files.")
    
    # --- FIX: Mutually exclusive provider flags ---
    provider_group = sort_parser.add_mutually_exclusive_group()
    provider_group.add_argument("--tmdb", action="store_true", help="Set TMDB as the primary metadata provider for this run.")
    provider_group.add_argument("--tvdb", action="store_true", help="Set TVDB as the primary metadata provider for this run.")
    
    sort_parser.add_argument("--split-languages", type=str, help='Comma-separated languages to split (e.g., "fr,de" or "all").')
    sort_parser.add_argument("--mismatched-dir", type=str, help="Override the Mismatched Files directory.")
    sort_parser.add_argument("--fallback", choices=["ignore", "mismatched", "tv", "anime"], help="Override fallback destination for mismatched shows.")

    watch_parser = subparsers.add_parser('watch', help="Start the watchdog to monitor the source directory for changes.")
    watch_parser.add_argument("--dry-run", action="store_true", help="Preview actions without moving files for all subsequent sorts.")
    watch_parser.add_argument("--watch-interval", type=int, metavar="MIN", help="Override watch interval in minutes.")

    reorganize_parser = subparsers.add_parser('reorganize-folders', help="Organize an existing library into a clean folder structure (e.g., 'Title (Year)/Season 01/').")
    reorganize_parser.add_argument("--target-dir", type=str, required=True, help="The path to the library folder you want to reorganize.")
    reorganize_parser.add_argument("--dry-run", action="store_true", help="Preview folder changes without moving any files.")

    rename_parser = subparsers.add_parser('rename-files', help="Rename media files within a library to a clean format (e.g., 'Title - S01E02.ext').")
    rename_parser.add_argument("--target-dir", type=str, required=True, help="The path to the library folder whose files you want to rename.")
    rename_parser.add_argument("--dry-run", action="store_true", help="Preview renames without changing any filenames.")
    rename_parser.add_argument("--quick-clean", action="store_true", help="Use quick local cleaning without API calls.")

    args = parser.parse_args()
    config_path = Path(args.config)
    cfg = Config.load(config_path)

    if hasattr(args, 'tmdb') and args.tmdb: cfg.API_PROVIDER = "tmdb"
    if hasattr(args, 'tvdb') and args.tvdb: cfg.API_PROVIDER = "tvdb"
    if hasattr(args, 'split_languages') and args.split_languages is not None: cfg.LANGUAGES_TO_SPLIT = [lang.strip().lower() for lang in args.split_languages.split(',') if lang.strip()]
    if hasattr(args, 'watch_interval') and args.watch_interval: cfg.WATCH_INTERVAL = args.watch_interval * 60
    if hasattr(args, 'mismatched_dir') and args.mismatched_dir: cfg.MISMATCHED_DIR = args.mismatched_dir
    if hasattr(args, 'fallback') and args.fallback: cfg.FALLBACK_SHOW_DESTINATION = args.fallback

    log_file = SCRIPT_DIR / "bangbangSMD.log"
    setup_logging(log_file=log_file, log_to_console=True)

    is_interactive = sys.stdout.isatty()
    if is_interactive:
        print(ASCII_ART)
    
    if args.command in ['sort', 'watch']:
        is_valid, message = cfg.validate()
        if not is_valid:
            logging.error(f"Configuration error: {message}")
            if not config_path.exists():
                logging.info(f"A default configuration file will be created at '{config_path}'.")
                logging.info("Please edit it with your API key(s) and directory paths.")
                cfg.save(config_path)
            sys.exit(1)

    if args.dry_run and is_interactive: logging.info("🧪 DRY RUN MODE - No files will be moved or directories created.")
    if args.command in ['sort', 'watch']:
        logging.info(f"⚙️ PRIMARY PROVIDER: {cfg.API_PROVIDER.upper()}")
        if cfg.SPLIT_MOVIES_DIR and cfg.LANGUAGES_TO_SPLIT: logging.info(f"🔵⚪🔴 Language Split is ENABLED for: {cfg.LANGUAGES_TO_SPLIT}")
        if hasattr(args, 'fallback') and args.fallback: logging.info(f"🔧 FALLBACK OVERRIDE: Mismatched shows will be sent to '{cfg.FALLBACK_SHOW_DESTINATION}'.")

    sorter = MediaSorter(cfg, dry_run=args.dry_run)
    
    try:
        if args.command == 'sort':
            logging.info("Starting a single shot sort...")
            sorter.process_source_directory()
        elif args.command == 'watch':
            sorter.start_watch_mode()
        elif args.command == 'reorganize-folders':
            target_dir = Path(args.target_dir)
            if not target_dir.is_dir():
                logging.error(f"Error: The specified target directory does not exist: {target_dir}")
                sys.exit(1)
            logging.info(f"Starting to reorganize folder structure in: {target_dir}")
            sorter.reorganize_folder_structure(target_dir)
        elif args.command == 'rename-files':
            target_dir = Path(args.target_dir)
            if not target_dir.is_dir():
                logging.error(f"Error: The specified target directory does not exist: {target_dir}")
                sys.exit(1)
            
            # --- FIX: Refactored and simplified logic ---
            use_quick_clean = hasattr(args, 'quick_clean') and args.quick_clean
            mode_str = "quick clean (no API)" if use_quick_clean else "API-based"
            logging.info(f"Starting to rename files in '{target_dir}' using {mode_str} mode.")
            
            all_files = [p for ext in cfg.SUPPORTED_EXTENSIONS for p in target_dir.glob(f'**/*{ext}') if p.is_file()]
            rename_plan = sorter.generate_rename_plan(target_dir, all_files, quick_clean_only=use_quick_clean)
            sorter.rename_files_in_library(rename_plan)
            
    except KeyboardInterrupt:
        logging.info("\n⏹️ Operation cancelled by user. Shutting down gracefully...")
        sorter.signal_stop()
    except Exception as e:
        logging.error(f"A fatal error occurred: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
