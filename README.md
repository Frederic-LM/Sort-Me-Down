SortMeDown a Media Sorter Script Version: 3.1.2
==================

Automatically sorts media files (movies, TV shows, anime) into organized directories
based on metadata from OMDb API and AniList API.
can be run as a one shot, or perpetualy with a includes watch dog that monitor change in the source directory

Features:
- Automatic detection of movies, TV series, and anime
- Multi-language support (English/French movies)
- Season-based organization for TV shows
- Dry-run mode for safe testing
- Comprehensive logging
- Duplicate detection and handling
- Intergrated watchdog
- Dedicated French movies folder if run with --fr argument
- Revised Logic with less bias (no longer reling on "english" as primary key word)

Arguments:

- python bangbang.py                                  # One-time sorting (original behavior)
- python bangbang.py --fr                             # Sorts, and separates French movies
- python bangbang.py --dry-run                        # Preview mode
- python bangbang.py --version                        # Show version
- python bangbang.py --watch                          # Standard watch mode (15 minute intervals)
- python bangbang.py --watch --watch-interval 30      # Custom interval (30 minutes)
- python bangbang.py --watch --dry-run                # Watch mode with dry-run (perfect for testing)




Usage:
CLI (Comand Line Interface)
   - 1) Register your free API Key from http://www.omdbapi.com/
   - 2) Edit bangbang.py with youe API Key 
   - 3) Edit bangbang.py with the path to your source folder (your download folder for exemple
   - 4) Edit bangbang.py with the paths to your medias movies, TV shows, anime, anime series
   - 5) Rdit the path for the log
   - 6) Run the script using the desired argument

Optional:  Have you system runing it at log in  either with the wath dog , or as a sheduled one time (default behavior)

GUI 1.2 (work in progress) ! the GUI has now more feature than the CLI, as it allows to run selectively for Movies, Show, Anime etc

- pip install -r requirement.txt
- python gui.py
- bangbang_backend.py  <= more feat


