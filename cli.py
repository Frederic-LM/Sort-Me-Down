#!/usr/bin/env python3
# cli.py
"""
SortMeDown - Command-Line Interface (v5.1)
============================================

This script provides a command-line interface to the SortMeDown engine.
It handles user input, displays progress in the console, and calls the
core logic from `bangbang.py`.

--------------------
COMMAND-LINE OPTIONS
--------------------

All command-line flags are optional and are used to override the settings 
found in `config.json` for a single run.

--help
    Show the help message and exit.

--version
    Show the program's version number and exit.

--config [PATH]
    Specifies the path to the configuration file.
    Default: `config.json` in the same directory as the script.
    Example: python cli.py --config /path/to/my/custom_config.json

--dry-run
    Perform a "dry run" of the sorting process. The script will log all
    actions it *would* have taken (classifying, creating folders, moving
    files) without actually modifying the filesystem. This is highly
    recommended for the first run to ensure your paths are correct.

--watch
    Enable "watch mode." After an initial sort of the source directory,
    the script will remain active and monitor the directory for new files,
    processing them as they are added. This is mutually exclusive with
   `--cleanup-in-place`.

--watch-interval [MINUTES]
    Override the watch interval defined in the config file.
    Example: python cli.py --watch --watch-interval 5
             (Checks for new files every 5 minutes)

--cleanup-in-place
    Enable "cleanup mode." Instead of moving files to separate library
    directories, this mode organizes files *within* the source directory.
    It will create subfolders for shows/movies inside the source directory
    and move the files there. This is useful for tidying up a single large
    download folder. This mode is mutually exclusive with `--watch`.

--fr
    Enable "French mode" for this run. If a movie is identified as being
    in French, it will be moved to the `FRENCH_MOVIES_DIR` instead of the
    standard `MOVIES_DIR`.

--mismatched-dir [PATH]
    Override the `MISMATCHED_DIR` setting from the config file. This is
    the folder where files with conflicting metadata (e.g., year mismatch)
    are sent for manual review.
    Example: python cli.py --mismatched-dir "C:/Sorting/Review"

--fallback [choice]
    Override the fallback behavior for shows that have conflicting metadata.
    This is for files that look like a series (e.g., S01E01) but the API
    returns a movie, or for shows where no API data is found at all.

    Available choices:
      - ignore:     Leave the file where it is. Do not move it.
      - mismatched: Move the file to the "Mismatched" directory. (Default)
      - tv:         Assume it's a regular TV show and move it to the
                    TV Shows library.
      - anime:      Assume it's an anime series and move it to the
                    Anime Series library.
    
    Example: python cli.py --fallback tv

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
#        ░      ░ ░ CLI ░   Media Sorter Script  ░      ░  ░      ░        ░ ░      ░         5.1 ░ 
#                                                               ░                                    
"""

def main():
    parser = argparse.ArgumentParser(
        description="SortMeDown Media Sorter",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Usage Examples:
---------------
# One-time recursive sort using settings from config.json
python cli.py

# Preview all actions without moving any files
python cli.py --dry-run

# For mismatched shows, move them to the TV Shows folder for this run only
python cli.py --fallback tv

# Monitor the source directory for new files and sort them automatically
python cli.py --watch
"""
    )
    # --- Standard Arguments ---
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without moving files.")
    parser.add_argument("--watch", action="store_true", help="Monitor source directory for new files.")
    parser.add_argument("--config", type=str, default="config.json", help="Path to the configuration file (default: config.json).")
    parser.add_argument("--version", action="version", version="SortMeDown CLI 4.9.1")

    # --- Override Arguments ---
    parser.add_argument("--fr", action="store_true", help="Enable sorting of French-language movies to a separate directory.")
    parser.add_argument("--cleanup-in-place", action="store_true", help="Sort and rename files within the source directory.")
    parser.add_argument("--watch-interval", type=int, metavar="MIN", help="Override watch interval in minutes from config.")
    
    # --- ADDED: New Arguments for Fallback Control ---
    parser.add_argument("--mismatched-dir", type=str, help="Override the Mismatched Files directory from config.")
    parser.add_argument(
        "--fallback", 
        choices=["ignore", "mismatched", "tv", "anime"],
        help="Override fallback destination for mismatched shows. 'ignore' leaves them in place."
    )

    args = parser.parse_args()
    
    # --- Configuration ---
    config_path = Path(args.config)
    cfg = Config.load(config_path)

    # --- CLI arguments override settings from the config file for this specific run ---
    if args.fr:
        cfg.FRENCH_MODE_ENABLED = True
    if args.cleanup_in_place:
        cfg.CLEANUP_MODE_ENABLED = True
    if args.watch_interval:
        cfg.WATCH_INTERVAL = args.watch_interval * 60
    # --- ADDED: Handle new override arguments ---
    if args.mismatched_dir:
        cfg.MISMATCHED_DIR = args.mismatched_dir
    if args.fallback:
        cfg.FALLBACK_SHOW_DESTINATION = args.fallback

    # --- Setup ---
    log_file = Path(__file__).parent / "bangbangSMD.log"
    setup_logging(log_file=log_file, log_to_console=True)

    print(ASCII_ART)
    
    # Validate configuration
    is_valid, message = cfg.validate()
    if not is_valid:
        logging.error(f"Configuration error: {message}")
        logging.error("Please edit your configuration file or check paths.")
        if not config_path.exists():
            logging.info(f"A default configuration file will be created at '{config_path}'.")
            logging.info("Please edit it with your API key and directory paths.")
            cfg.save(config_path)
        sys.exit(1)

    # --- Log status messages for overridden settings ---
    if args.dry_run:
        logging.info("🧪 DRY RUN MODE - No files will be moved or directories created.")
    if cfg.FRENCH_MODE_ENABLED:
        logging.info("🔵⚪🔴 French mode is ENABLED.")
    if cfg.CLEANUP_MODE_ENABLED:
        logging.info("🧹 CLEANUP IN-PLACE MODE - Files will be sorted within the source directory.")
    if args.fallback:
        logging.info(f"🔧 FALLBACK OVERRIDE: Mismatched shows will be sent to '{cfg.FALLBACK_SHOW_DESTINATION}'.")


    # Instantiate the engine's sorter
    sorter = MediaSorter(cfg, dry_run=args.dry_run)
    
    # --- Execution ---
    try:
        if args.watch:
            if args.cleanup_in_place:
                logging.error("--watch and --cleanup-in-place modes are mutually exclusive.")
                sys.exit(1)
            # With the corrected backend, start_watch_mode is now a blocking call
            # that runs until it is stopped. The old while loop is no longer needed.
            sorter.start_watch_mode()
        else:
            # This remains a simple, one-off call.
            sorter.process_source_directory()
            
    except KeyboardInterrupt:
        logging.info("\n⏹️ Operation cancelled by user. Shutting down gracefully...")
        # The signal_stop() method is now the only thing needed to stop
        # either a watch or a regular sort.
        sorter.signal_stop()
        logging.info("Shutdown complete.")
    except Exception as e:
        logging.error(f"A fatal error occurred: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
