#!/usr/bin/env python3
# cli.py
"""
/!\ MAJOR CHANGES /!\
SortMeDown - Command-Line Interface (v6.0.0)
============================================
This script provides a command-line interface to the SortMeDown engine.
It uses an action-based command structure (`sort` or `watch`) to clearly
define the desired operation.
/!\ MAJOR CHANGES /!\
All settings are read from `config.json` by default. Optional flags can
be used to override these settings for a single run.

--------------------
COMMANDS
--------------------
  sort          Perform a single, one-time sort of the source directory.
  watch         Start the watchdog to monitor the source directory for changes.

Type `python cli.py [command] --help` for more information on a specific command.
"""

import argparse
import sys
import logging
from pathlib import Path

# Import the shared engine components
from bangbang import Config, MediaSorter, setup_logging

# ASCII Art Logo
ASCII_ART = """
#    ██████  ▒█████   ██▀███  ▄▄▄█████▓    ███▄ ▄███▓▓█████    ▓█████▄  ▒█████   █     █░███▄    █ 
#  ▒██    ▒ ▒██▒  ██▒▓██ ▒ ██▒▓  ██▒ ▓▒   ▓██▒▀█▀ ██▒▓█   ▀    ▒██▀ ██▌▒██▒  ██▒▓█░ █ ░█░██ ▀█   █ 
#  ░ ▓██▄   ▒██░  ██▒▓██ ░▄█ ▒▒ ▓██░ ▒░   ▓██    ▓██░▒███      ░██   █▌▒██░  ██▒▒█░ █ ░█▓██  ▀█ ██▒
#    ▒   ██▒▒██   ██░▒██▀▀█▄  ░ ▓██▓ ░    ▒██    ▒██ ▒▓█  ▄    ░▓█▄   ▌▒██   ██░░█░ █ ░█▓██▒  ▐▌██▒
#  ▒██████▒▒░ ████▓▒░░██▓ ▒██▒  ▒██▒ ░    ▒██▒   ░██▒░▒████▒   ░▒████▓ ░ ████▓▒░░░██▒██▓▒██░   ▓██░
#  ▒ ▒▓▒ ▒ ░░ ▒░▒░▒░ ░ ▒▓ ░▒▓░  ▒ ░░      ░ ▒░   ░  ░░░ ▒░ ░    ▒▒▓  ▒ ░ ▒░▒░▒░ ░ ▓░▒ ▒ ░ ▒░   ▒ ▒ 
#  ░ ░▒  ░ ░  ░ ▒ ▒░   ░▒ ░ ▒░    ░       ░  ░      ░ ░ ░  ░    ░ ▒  ▒   ░ ▒ ▒░   ▒ ░ ░ ░ ░░   ░ ▒░
#  ░  ░  ░  ░ ░ ░ ▒    ░░   ░   ░         ░      ░      ░       ░ ░  ░ ░ ░ ░ ▒    ░   ░    ░   ░ ░ 
#        ░      ░ ░ CLI ░   Media Sorter Script  ░      ░  ░      ░        ░ ░      ░      6.0.0 ░ 
#                                                               ░                                    
"""

def main():
    # --- Main Parser ---
    parser = argparse.ArgumentParser(
        description="SortMeDown Media Sorter",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--config", type=str, default="config.json", help="Path to the configuration file (default: config.json).")
    parser.add_argument("--version", action="version", version="SortMeDown CLI 6.0.0")

    subparsers = parser.add_subparsers(dest='command', required=True, help="The action to perform.")

    # --- 'sort' Command Parser ---
    sort_parser = subparsers.add_parser('sort', help="Perform a single, one-time sort of the source directory.")
    sort_parser.add_argument("--dry-run", action="store_true", help="Preview actions without moving files.")
    sort_parser.add_argument("--tmdb", action="store_true", help="Set TMDB as the primary metadata provider for this run.")
    sort_parser.add_argument("--split-languages", type=str, help='Comma-separated languages to split (e.g., "fr,de" or "all").')
    sort_parser.add_argument("--cleanup-in-place", action="store_true", help="Sort files within the source directory (mutually exclusive with watch).")
    sort_parser.add_argument("--mismatched-dir", type=str, help="Override the Mismatched Files directory.")
    sort_parser.add_argument("--fallback", choices=["ignore", "mismatched", "tv", "anime"], help="Override fallback destination for mismatched shows.")

    # --- 'watch' Command Parser ---
    watch_parser = subparsers.add_parser('watch', help="Start the watchdog to monitor the source directory for changes.")
    watch_parser.add_argument("--dry-run", action="store_true", help="Preview actions without moving files for all subsequent sorts.")
    watch_parser.add_argument("--watch-interval", type=int, metavar="MIN", help="Override watch interval in minutes.")

    # --- Argument Parsing and Config Loading ---
    args = parser.parse_args()
    
    config_path = Path(args.config)
    cfg = Config.load(config_path)

    # --- Apply Overrides from Arguments ---
    # These checks are safe because of the subparser structure.
    if hasattr(args, 'tmdb') and args.tmdb:
        cfg.API_PROVIDER = "tmdb"
    if hasattr(args, 'split_languages') and args.split_languages is not None:
        cfg.LANGUAGES_TO_SPLIT = [lang.strip().lower() for lang in args.split_languages.split(',') if lang.strip()]
    if hasattr(args, 'cleanup_in_place') and args.cleanup_in_place:
        cfg.CLEANUP_MODE_ENABLED = True
    if hasattr(args, 'watch_interval') and args.watch_interval:
        cfg.WATCH_INTERVAL = args.watch_interval * 60
    if hasattr(args, 'mismatched_dir') and args.mismatched_dir:
        cfg.MISMATCHED_DIR = args.mismatched_dir
    if hasattr(args, 'fallback') and args.fallback:
        cfg.FALLBACK_SHOW_DESTINATION = args.fallback

    # --- Setup Logging ---
    log_file = Path(__file__).parent / "bangbangSMD.log"
    setup_logging(log_file=log_file, log_to_console=True)

    print(ASCII_ART)
    
    is_valid, message = cfg.validate()
    if not is_valid:
        logging.error(f"Configuration error: {message}")
        logging.error("Please edit your configuration file or check paths.")
        if not config_path.exists():
            logging.info(f"A default configuration file will be created at '{config_path}'.")
            logging.info("Please edit it with your API key(s) and directory paths.")
            cfg.save(config_path)
        sys.exit(1)

    # --- Log Final Settings ---
    if args.dry_run:
        logging.info("🧪 DRY RUN MODE - No files will be moved or directories created.")
    logging.info(f"⚙️ PRIMARY PROVIDER: {cfg.API_PROVIDER.upper()}")
    if cfg.SPLIT_MOVIES_DIR and cfg.LANGUAGES_TO_SPLIT:
        logging.info(f"🔵⚪🔴 Language Split is ENABLED for: {cfg.LANGUAGES_TO_SPLIT}")
    if cfg.CLEANUP_MODE_ENABLED:
        logging.info("🧹 CLEANUP IN-PLACE MODE - Files will be sorted within the source directory.")
    if hasattr(args, 'fallback') and args.fallback:
        logging.info(f"🔧 FALLBACK OVERRIDE: Mismatched shows will be sent to '{cfg.FALLBACK_SHOW_DESTINATION}'.")

    sorter = MediaSorter(cfg, dry_run=args.dry_run)
    
    # --- Execute Command ---
    try:
        if args.command == 'sort':
            logging.info("Starting a single shot sort...")
            sorter.process_source_directory()
        elif args.command == 'watch':
            if cfg.CLEANUP_MODE_ENABLED:
                logging.error("--cleanup-in-place mode cannot be used with the 'watch' command.")
                sys.exit(1)
            logging.info("Launching watchdog...")
            sorter.start_watch_mode()
            
    except KeyboardInterrupt:
        logging.info("\n⏹️ Operation cancelled by user. Shutting down gracefully...")
        sorter.signal_stop()
        logging.info("Shutdown complete.")
    except Exception as e:
        logging.error(f"A fatal error occurred: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
