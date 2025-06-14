#!/usr/bin/env python3
# cli.py

"""
SortMeDown - Command-Line Interface (v4.2.0)
============================================

This script provides a command-line interface to the SortMeDown engine.
It handles user input, displays progress in the console, and calls the
core logic from `bangbang.py`.
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
#        ░      ░ ░ CLI ░   Media Sorter Script  ░      ░  ░      ░        ░ ░      ░      4.2.0 ░ 
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
    parser.add_argument("--version", action="version", version="SortMeDown CLI 4.2.0")

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
            sorter.start_watch_mode()
            while sorter._watcher_thread.is_alive():
                sorter._watcher_thread.join(timeout=1.0)
        else:
            sorter.process_source_directory()
            
    except KeyboardInterrupt:
        logging.info("\n⏹️ Operation cancelled by user. Shutting down gracefully...")
        sorter.signal_stop()
        if sorter._watcher_thread and sorter._watcher_thread.is_alive():
            sorter._watcher_thread.join()
        logging.info("Shutdown complete.")
    except Exception as e:
        logging.error(f"A fatal error occurred: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
