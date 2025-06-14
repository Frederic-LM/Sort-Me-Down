#!/usr/bin/env python3
# cli.py

"""
SortMeDown - Command-Line Interface (v4.1.0)
============================================

This script provides a command-line interface to the SortMeDown engine.
It handles user input, displays progress in the console, and calls the
core logic from `bangbang.py`.
"""

import argparse
import sys
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
#        ░      ░ ░ CLI ░   Media Sorter Script  ░      ░  ░      ░        ░ ░      ░      4.1.0 ░ 
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

# Enable French movie sorting for this run
python cli.py --fr

# Sort files IN-PLACE within the source directory for this run
python cli.py --cleanup-in-place

# Monitor the source directory for new files and sort them automatically
python cli.py --watch
"""
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without moving files.")
    parser.add_argument("--fr", action="store_true", help="Enable sorting of French-language movies to a separate directory.")
    parser.add_argument("--cleanup-in-place", action="store_true", help="Sort and rename files within the source directory.")
    parser.add_argument("--watch", action="store_true", help="Monitor source directory for new files.")
    parser.add_argument("--watch-interval", type=int, metavar="MIN", help="Override watch interval in minutes from config.")
    parser.add_argument("--config", type=str, default="config.json", help="Path to the configuration file (default: config.json).")
    parser.add_argument("--version", action="version", version="SortMeDown CLI 4.1.0")
    args = parser.parse_args()
    
    # --- Configuration ---
    config_path = Path(args.config)
    
    # Load config from file first. If it doesn't exist, a default one is created.
    cfg = Config.load(config_path)

    # CLI arguments override settings from the config file for this specific run
    if args.fr:
        cfg.FRENCH_MODE_ENABLED = True
    if args.cleanup_in_place:
        cfg.CLEANUP_MODE_ENABLED = True
    if args.watch_interval:
        cfg.WATCH_INTERVAL = args.watch_interval * 60

    # --- Setup ---
    log_file = Path(__file__).parent / "bangbangSMD.log"
    setup_logging(log_file=log_file, log_to_console=True) # Show logs in console

    print(ASCII_ART)
    
    # Validate configuration
    is_valid, message = cfg.validate()
    if not is_valid:
        logging.error(f"Configuration error: {message}")
        logging.error("Please edit your configuration file or check paths.")
        # If the file doesn't exist, we can prompt to save a default one.
        if not config_path.exists():
            logging.info(f"A default configuration file will be created at '{config_path}'.")
            logging.info("Please edit it with your API key and directory paths.")
            cfg.save(config_path)
        sys.exit(1)

    if args.dry_run:
        logging.info("🧪 DRY RUN MODE - No files will be moved or directories created.")
    if cfg.FRENCH_MODE_ENABLED:
        logging.info("🔵⚪🔴 French mode is ENABLED.")
    if cfg.CLEANUP_MODE_ENABLED:
        logging.info("🧹 CLEANUP IN-PLACE MODE - Files will be sorted within the source directory.")


    # Instantiate the engine's sorter
    sorter = MediaSorter(cfg, dry_run=args.dry_run)
    
    # --- Execution ---
    try:
        if args.watch:
            if args.cleanup_in_place:
                logging.error("--watch and --cleanup-in-place modes are mutually exclusive.")
                sys.exit(1)
            sorter.start_watch_mode()
            # Keep the main thread alive to listen for KeyboardInterrupt
            while sorter._watcher_thread.is_alive():
                sorter._watcher_thread.join(timeout=1.0)
        else:
            sorter.process_source_directory()
            
    except KeyboardInterrupt:
        logging.info("\n⏹️ Operation cancelled by user. Shutting down gracefully...")
        sorter.signal_stop()
        # Wait for the thread to finish if it exists
        if sorter._watcher_thread and sorter._watcher_thread.is_alive():
            sorter._watcher_thread.join()
        logging.info("Shutdown complete.")
    except Exception as e:
        logging.error(f"A fatal error occurred: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
