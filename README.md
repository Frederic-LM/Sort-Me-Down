# SortMeDown & BangBang
<div align="center">

```python      
#    ██████  ▒█████   ██▀███  ▄▄▄█████▓    ███▄ ▄███▓▓█████    ▓█████▄  ▒█████   █     █░███▄    █ 
#  ▒██    ▒ ▒██▒  ██▒▓██ ▒ ██▒▓  ██▒ ▓▒   ▓██▒▀█▀ ██▒▓█   ▀    ▒██▀ ██▌▒██▒  ██▒▓█░ █ ░█░██ ▀█   █ 
#  ░ ▓██▄   ▒██░  ██▒▓██ ░▄█ ▒▒ ▓██░ ▒░   ▓██    ▓██░▒███      ░██   █▌▒██░  ██▒▒█░ █ ░█▓██  ▀█ ██▒
#    ▒   ██▒▒██   ██░▒██▀▀█▄  ░ ▓██▓ ░    ▒██    ▒██ ▒▓█  ▄    ░▓█▄   ▌▒██   ██░░█░ █ ░█▓██▒  ▐▌██▒
#  ▒██████▒▒░ ████▓▒░░██▓ ▒██▒  ▒██▒ ░    ▒██▒   ░██▒░▒████▒   ░▒████▓ ░ ████▓▒░░░██▒██▓▒██░   ▓██░
#  ▒ ▒▓▒ ▒ ░░ ▒░▒░▒░ ░ ▒▓ ░▒▓░  ▒ ░░      ░ ▒░   ░  ░░░ ▒░ ░    ▒▒▓  ▒ ░ ▒░▒░▒░ ░ ▓░▒ ▒ ░ ▒░   ▒ ▒ 
#  ░ ░▒  ░ ░  ░ ▒ ▒░   ░▒ ░ ▒░    ░       ░  ░      ░ ░ ░  ░    ░ ▒  ▒   ░ ▒ ▒░   ▒ ░ ░ ░ ░░   ░ ▒░
#  ░  ░  ░  ░ ░ ░ ▒    ░░   ░   ░         ░      ░      ░       ░ ░  ░ ░ ░ ░ ▒    ░   ░    ░   ░ ░ 
#        ░      ░ ░ CLI ░   Media Sorter Script  ░      ░  ░      ░        ░ ░      ░      5.2.0 ░ 
#                                                               ░
```
    


A powerful, configurable media sorter with both a GUI and CLI.
</div>


![alt text](https://img.shields.io/badge/python-3.9+-blue.svg) ![alt text](https://img.shields.io/badge/License-MIT-yellow.svg)

SortMeDown automatically organizes your movies, TV shows, and anime into a clean, structured library. It fetches metadata from OMDb and AniList to correctly identify and rename your files, then moves them to your specified library directories.
✨ Key Features

    🤖 Automatic Sorting: Intelligently detects and sorts Movies, TV Series, Anime Movies, and Anime Series.

    🎭 Dual Interfaces: Choose between a user-friendly Graphical User Interface (GUI) or a powerful Command-Line Interface (CLI).

    🧠 Intelligent Conflict Resolution: Compares filenames to API results to detect mismatches (e.g., wrong year, series vs. movie) and handles them based on your rules.

    📂 Configurable Fallbacks: You decide what to do with mismatched files: move them to a review folder, a default library, or leave them in place.

    ⏱️ Watch Mode: Automatically monitors your source folder and processes new files as they arrive.

    🧪 Safe Dry-Run Mode: Preview all file operations without actually moving or renaming anything.

    🇫🇷 French Language Support: Optionally route French-language movies to a dedicated directory.

    🛠️ Clean Architecture: Built on a UI-agnostic core engine (bangbang.py) that can be controlled by any frontend.

🖼️ Screenshots
Example GUI Layout:

![Screenshot GUI 2025](https://github.com/user-attachments/assets/0f1b180a-3e74-4717-8f04-8b7701e75ad3)


⚙️ Installation & Setup

Follow these steps to get SortMeDown up and running.

1. Clone the Repository

      
git clone https://github.com/Frederic-LM/Sort-Me-Down.git
cd your-repo-name

    

2. Install Dependencies

The GUI has a few dependencies. You can install them using the provided requirements.txt file (if you create one) or install them manually.
      
 Recommended: Create a requirements.txt with the following and run:
 pip install -r requirements.txt

# Manual installation:
pip install requests customtkinter pystray Pillow

    
3. Get an OMDb API Key

This project requires a free API key from the OMDb (Open Movie Database).

    Go to http://www.omdbapi.com/apikey.aspx

    Select the "FREE" plan and enter your email.

    You will receive your API key via email.

4. Create Your Configuration

The easiest way to create your configuration file is to run either the GUI or CLI once.

      
python gui.py
# OR
python cli.py

    


The application will detect that config.json is missing and create a default one for you.

5. Edit config.json

Open the newly created config.json file and fill in the required paths and your API key.

Here is a minimal sample:
      
```json
{

    
    "SOURCE_DIR": "C:/Path/To/Your/Downloads",
    "MOVIES_DIR": "D:/Media/Movies",
    "TV_SHOWS_DIR": "D:/Media/TV Shows",
    "ANIME_MOVIES_DIR": "D:/Media/Anime Movies",
    "ANIME_SERIES_DIR": "D:/Media/Anime Series",
    "MISMATCHED_DIR": "C:/Path/To/Your/Downloads/_Mismatched",
    "OMDB_API_KEY": "your_omdb_api_key_here",
   
}
```

    

    Note: For Windows paths, use forward slashes (/) or double backslashes (\\) to avoid issues.

🚀 Usage

You can run the application using either the GUI or the CLI.
Graphical User Interface (GUI)

The GUI provides an easy-to-use interface for all settings and actions.
    
python gui.py

   
    Actions Tab: Start a one-time sort, enable watch mode, and configure fallback behavior.

    Settings Tab: Configure all your library paths, API key, and other advanced options.

Command-Line Interface (CLI)

The CLI is perfect for scripting, automation, or for users who prefer the terminal.

🖼️ Screenshots
![Screenshot 2025CLI](https://github.com/user-attachments/assets/cbd214fd-6afb-4ed1-ab85-7b24a86e9054)

Basic Commands:

      
# Perform a one-time sort using settings from config.json
python cli.py

# Preview all actions without moving any files
python cli.py --dry-run

# Start watch mode to monitor the source directory
python cli.py --watch
  

All CLI Arguments:
| Argument | Description | Example |
|---|---|---|
| --help | Show the help message. | |
| --version | Show the program version. | |
| --config [PATH] | Use a specific config file. | --config C:/alt_config.json |
| --dry-run | Simulate a run without changing files. | |
| --watch | Enable watch mode. | |
| --watch-interval [MIN] | Set watch mode interval in minutes. | --watch --watch-interval 5 |
| --cleanup-in-place| Organize files within the source folder. | |
| --fr | Enable sorting for French movies. | |
| --mismatched-dir [PATH] | Override the directory for mismatched files. | --mismatched-dir "D:/Review"|
| --fallback [choice] | Override fallback for mismatched shows. <br> Choices: ignore, mismatched, tv, anime. | --fallback tv |
🔧 Configuration Details

Your config.json file holds all the settings for the sorter.

    SOURCE_DIR: The folder where your unsorted media is located.

    ..._DIR: The destination library folders for each media type.

    MISMATCHED_DIR: Where to send files with conflicting metadata for manual review. If left blank, a _Mismatched folder will be created inside your SOURCE_DIR.

    FALLBACK_SHOW_DESTINATION: Default behavior for mismatched shows ("ignore", "mismatched", "tv", or "anime").

    OMDB_API_KEY: Your personal key from OMDb.

    SUPPORTED_EXTENSIONS: File types to be considered primary media files.

    SIDECAR_EXTENSIONS: File types (like subtitles or posters) to move alongside the primary media file.


# Option : Compiling into a Standalone Executable

This method bundles the application and all its dependencies into a single file that can be run on other computers without needing to install Python.

#### Prerequisites

1.  **Install PyInstaller:** This tool is used to create the executable.
    ```bash
    pip install pyinstaller
    ```
2.  **Prepare Project Files:**
    Ensure your project directory is clean and contains the necessary files. You will also need an icon file appropriate for your operating system.
    ```
    your-project-folder/
    ├── gui.py
    ├── bangbang.py
    └── icon.ico  (for Windows) OR icon.icns (for macOS)
    ```

---

#### For Windows (.exe)

1.  **Run the PyInstaller Command:**
    Open a command prompt or terminal in your project directory and execute the following command:
    ```bash
    pyinstaller --onefile --windowed --hidden-import="pystray._win32" --icon="icon.ico" gui.py
    ```
2.  **Find Your Executable:**
    After the process completes, a `dist` folder will be created. Inside this folder, you will find your final `gui.exe` file. This file can be shared and run on any modern Windows machine.

---

#### For macOS (.app)

> **Important:** You must compile the macOS application **on a macOS machine**.

1.  **Install Prerequisites (on a Mac):**
    If you don't have them, install Homebrew and the required Python packages via the Terminal.
    ```bash
    # Install Homebrew (if not already installed)
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Install Python and dependencies
    brew install python
    pip3 install pyinstaller customtkinter requests pystray
    ```
2.  **Prepare Icon:**
    Make sure you have an `icon.icns` file for your application icon.

3.  **Run the PyInstaller Command:**
    In your project directory, execute the following command:
    ```bash
    pyinstaller --onefile --windowed --name="Sort-Me-Down" --hidden-import="pystray._win32" --icon="icon.ico" gui.py

    ```

4.  **Find and Run Your Application:**
    The `dist` folder will contain your final `gui.app` bundle.

    > **Gatekeeper Security Warning (CRITICAL!)**
    > The first time you run the app, macOS will likely block it as it's from an "unidentified developer."
    >
    > **To run it, you must right-click the `gui.app` file and select "Open" from the context menu.**
    >
    > A dialog will appear with an "Open" button that will allow you to run the application. This only needs to be done once.

    

📜 License

This project is licensed under the MIT License - see the LICENSE.md file for details.
