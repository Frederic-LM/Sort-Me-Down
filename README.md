SortMeDown Media Sorter Script
==================

Automatically sorts media files (movies, TV shows, anime) into organized directories
based on metadata from OMDb API and AniList API.
can be run as a one shot, or perpetualy with a includes watch dog that monitor change in the source directory

Features:
- Automatic detection of movies, TV series, and Anime & Anime serie
- Season-based organization for TV shows
- Dry-run mode for safe testing
- Comprehensive logging
- Duplicate detection and handling
- Intergrated watchdog
- Dual Api logic for better detection

python bangbang.py                # One-time sorting (original behavior)
python bangbang.py --dry-run      # Preview mode
python bangbang.py --version      # Show version
python bangbang.py --watch                          # Standard watch mode (15 minute intervals)
python bangbang.py --watch --watch-interval 30      # Custom interval (30 minutes)
python bangbang.py --watch --dry-run                # Watch mode with dry-run (perfect for testing)


Version: 2.6i
