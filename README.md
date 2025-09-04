# SortMeDown & BangBang

<div align="center">

```
    ██████  ▒█████   ██▀███  ▄▄▄█████▓    ███▄ ▄███▓▓█████    ▓█████▄  ▒█████   █     █░███▄    █ 
  ▒██    ▒ ▒██▒  ██▒▓██ ▒ ██▒▓  ██▒ ▓▒   ▓██▒▀█▀ ██▒▓█   ▀    ▒██▀ ██▌▒██▒  ██▒▓█░ █ ░█░██ ▀█   █ 
  ░ ▓██▄   ▒██░  ██▒▓██ ░▄█ ▒▒ ▓██░ ▒░   ▓██    ▓██░▒███      ░██   █▌▒██░  ██▒▒█░ █ ░█▓██  ▀█ ██▒
    ▒   ██▒▒██   ██░▒██▀▀█▄  ░ ▓██▓ ░    ▒██    ▒██ ▒▓█  ▄    ░▓█▄   ▌▒██   ██░░█░ █ ░█▓██▒  ▐▌██▒
  ▒██████▒▒░ ████▓▒░░██▓ ▒██▒  ▒██▒ ░    ▒██▒   ░██▒░▒████▒   ░▒████▓ ░ ████▓▒░░░██▒██▓▒██░   ▓██░
  ▒ ▒▓▒ ▒ ░░ ▒░▒░▒░ ░ ▒▓ ░▒▓░  ▒ ░░      ░ ▒░   ░  ░░░ ▒░ ░    ▒▒▓  ▒ ░ ▒░▒░▒░ ░ ▓░▒ ▒ ░ ▒░   ▒ ▒ 
  ░ ░▒  ░ ░  ░ ▒ ▒░   ░▒ ░ ▒░    ░       ░  ░      ░ ░ ░  ░    ░ ▒  ▒   ░ ▒ ▒░   ▒ ░ ░ ░ ░░   ░ ▒░
  ░  ░  ░  ░ ░ ░ ▒    ░░   ░   ░         ░      ░      ░       ░ ░  ░ ░ ░ ░ ▒    ░   ░    ░   ░ ░ 
        ░      ░ ░      ░                        ░      ░  ░      ░        ░ ░      ░        ░   
                     CLI Media Sorter Script                                           v6.0.1
```

**A powerful, configurable media sorter with both GUI and CLI interfaces**

![Python](https://img.shields.io/badge/python-3.9+-blue.svg?style=flat-square&logo=python&logoColor=white)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg?style=flat-square)](https://opensource.org/licenses/Apache-2.0)
![Platform](https://img.shields.io/badge/platform-Windows%20|%20macOS%20|%20Linux-lightgrey.svg?style=flat-square)
![Status](https://img.shields.io/badge/status-Active-brightgreen.svg?style=flat-square)

</div>

---

## 🌟 Overview

SortMeDown automatically organizes your movies, TV shows, and anime into a clean, structured library. It fetches metadata from OMDb , AniList, TMDB or TVDB to correctly identify and rename your files, then moves them to your specified library directories with intelligent conflict resolution.

## ✨ Key Features

<table>
<tr>
<td width="50%">

### 🎯 **Smart Organization**
- 🤖 **Automatic Detection** - Movies, TV Series, Anime Movies & Series
- 🧠 **Intelligent Conflict Resolution** - Compares filenames to API results
- 📂 **Configurable Fallbacks** - Handle mismatched files your way
- 🇫🇷 **Language Support** - Route specific language content to dedicated directories

</td>
<td width="50%">

### 🚀 **Powerful Interfaces**
- 🎭 **Dual Modes** - GUI for ease, CLI for power users
- ⏱️ **Watch Mode** - Monitor folders for new files automatically
- 🧪 **Dry-Run Mode** - Preview operations safely
- 🛠️ **Clean Architecture** - UI-agnostic core engine

</td>
</tr>
</table>

---

## 📸 Screenshots

### GUI Interface
<p align="center">
  <img src="https://github.com/user-attachments/assets/5cd92668-bc3a-4c7d-a6d1-3fb3febc43a1" width="200" />
  <img src="https://github.com/user-attachments/assets/44c92305-601b-4c2d-afac-fe54bf72c53c" width="200" />
  <img src="https://github.com/user-attachments/assets/d5a7fdc6-b3ce-4416-a8c9-cef841d5ee8a" width="200" />
  <img src="https://github.com/user-attachments/assets/38579906-235b-483d-8346-e55b517cb6a4" width="200" />
</p>

### CLI Interface
<div align="center">

<img width="724" alt="CLI Interface" src="https://github.com/user-attachments/assets/2e422370-5867-411b-8d40-b1cd48d12f8a" />

</div>

---

## 🚀 Quick Start

### 1️⃣ Clone & Install

```bash
# Clone the repository
git clone https://github.com/Frederic-LM/Sort-Me-Down.git
cd Sort-Me-Down

# Install dependencies
pip install -r requirements.txt
```

### 2️⃣ Get Your API Key

> 🔑 **Free OMDb API Key Required**
> 
> 1. Visit [omdbapi.com/apikey.aspx](http://www.omdbapi.com/apikey.aspx)
> 2. Select the **FREE** plan
> 3. Enter your email
> 4. Check your inbox for the API key

### 3️⃣ Initial Configuration

```bash
# Run once to create default config
python gui.py
# OR
python cli.py
```

### 4️⃣ Configure Your Paths

Edit the generated `config.json`:

```json
{
    "SOURCE_DIR": "C:/Path/To/Your/Downloads",
    "MOVIES_DIR": "D:/Media/Movies",
    "TV_SHOWS_DIR": "D:/Media/TV Shows",
    "ANIME_MOVIES_DIR": "D:/Media/Anime Movies",
    "ANIME_SERIES_DIR": "D:/Media/Anime Series",
    "MISMATCHED_DIR": "C:/Path/To/Your/Downloads/_Mismatched",
    "OMDB_API_KEY": "your_omdb_api_key_here"
}
```

> 💡 **Windows Users**: Use forward slashes `/` or double backslashes `\\` in paths

---

## 🎮 Usage

### 🖼️ Graphical Interface

Perfect for beginners and occasional users:

```bash
python gui.py
```

**Features:**
- **Actions Tab** - Start sorting, enable watch mode, configure fallbacks
- **Settings Tab** - Manage library paths, API keys, and advanced options
- **Real-time Status** - See what's happening as it happens

### 💻 Command Line Interface

Ideal for power users and automation:

#### Basic Commands

```bash
# One-time sort using config.json settings
python cli.py sort

# Monitor directory for new files
python cli.py watch

# Preview operations without moving files
python cli.py sort --dry-run
```

#### Advanced Usage

<details>
<summary><strong>📖 Click to expand full CLI reference</strong></summary>

### Global Arguments
| Argument | Description | Example |
|----------|-------------|---------|
| `--help` | Show help message | `python cli.py sort --help` |
| `--version` | Show program version | `python cli.py --version` |
| `--config [PATH]` | Use specific config file | `python cli.py sort --config /path/to/config.json` |

### Sort Command Options
```bash
python cli.py sort [OPTIONS]
```

| Argument | Description | Example |
|----------|-------------|---------|
| `--dry-run` | Simulate without moving files | `python cli.py sort --dry-run` |
| `--tmdb` | Use TMDB as primary API | `python cli.py sort --tmdb` |
| `--split-languages` | Split languages into folders | `python cli.py sort --split-languages "fr,de"` |
| `--cleanup-in-place` | Organize within source folder | `python cli.py sort --cleanup-in-place` |
| `--mismatched-dir` | Override mismatched directory | `python cli.py sort --mismatched-dir "D:/Review"` |
| `--fallback [choice]` | Fallback behavior for mismatches | `python cli.py sort --fallback tv` |

### Watch Command Options
```bash
python cli.py watch [OPTIONS]
```

| Argument | Description | Example |
|----------|-------------|---------|
| `--dry-run` | Run watchdog in simulation mode | `python cli.py watch --dry-run` |
| `--watch-interval [MIN]` | Override check interval | `python cli.py watch --watch-interval 5` |

</details>

---

## ⚙️ Configuration

<details>
<summary><strong>🔧 Click to see all configuration options</strong></summary>

### Core Settings
- **`SOURCE_DIR`** - Folder with unsorted media
- **`MOVIES_DIR`** - Destination for movies
- **`TV_SHOWS_DIR`** - Destination for TV series
- **`ANIME_MOVIES_DIR`** - Destination for anime movies
- **`ANIME_SERIES_DIR`** - Destination for anime series
- **`MISMATCHED_DIR`** - Files with conflicting metadata

### API & Behavior
- **`OMDB_API_KEY`** - Your OMDb API key
- **`FALLBACK_SHOW_DESTINATION`** - Default for mismatched shows (`"ignore"`, `"mismatched"`, `"tv"`, or `"anime"`)

### File Types
- **`SUPPORTED_EXTENSIONS`** - Primary media file types
- **`SIDECAR_EXTENSIONS`** - Files to move with media (subtitles, posters, etc.)

</details>

---

## 📦 Building Executables

<details>
<summary><strong>🏗️ Create standalone executables</strong></summary>

### Prerequisites
```bash
pip install pyinstaller
pip install -r requirements.txt
```

### Windows (.exe)
```bash
pyinstaller --onefile --windowed --hidden-import="pystray._win32" --add-data "icon.ico;." --add-data "icon.png;." --icon="icon.ico" --name="Sort-Me-Down" gui.py
```

### macOS (.app)
> ⚠️ **Must be compiled on macOS**

```bash
pyinstaller --onefile --windowed --name="Sort-Me-Down" --hidden-import="pystray._win32" --icon="icon.ico" --add-data="icon.ico;." --add-data="icon.png;." gui.py

```

> 🛡️ **macOS Security**: First run requires right-click → "Open" to bypass Gatekeeper

</details>

---

## 🤖 Running as a Service/Daemon

<details>
<summary><strong>⚙️ Set up automatic background processing</strong></summary>

### Linux/macOS (systemd)

Create `/etc/systemd/system/sortmedown.service`:

```ini
[Unit]
Description=SortMeDown Media Sorter
After=network.target

[Service]
User=your_username
Group=your_username
WorkingDirectory=/path/to/sortmedown/
ExecStart=/path/to/python /path/to/cli.py watch
Restart=on-failure
RestartSec=30
SyslogIdentifier=sortmedown

[Install]
WantedBy=multi-user.target
```

**Manage the service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable sortmedown.service
sudo systemctl start sortmedown.service
sudo systemctl status sortmedown.service
```

### Windows (NSSM)

1. **Download [NSSM](https://nssm.cc/download)**
2. **Install as service:**
   ```cmd
   nssm.exe install SortMeDown
   ```
3. **Configure in the GUI:**
   - **Path**: Your Python executable
   - **Arguments**: `cli.py watch --config "C:\path\to\config.json"`
   - **Startup directory**: Your project folder

**Manage the service:**
```cmd
sc start SortMeDown
sc stop SortMeDown
sc query SortMeDown
```

</details>

---

## 🛡️ File Safety

### How SortMeDown Handles Active Downloads

<details>
<summary><strong>🔒 Click to understand the safety mechanisms</strong></summary>

**The Most Common (Safe) Scenario:**

1. **Download in Progress** → OS locks the file
2. **SortMeDown Scans** → Finds and classifies the file
3. **Move Attempt** → OS denies access (file locked)
4. **Graceful Handling** → Error logged, file skipped
5. **Download Completes** → Lock released
6. **Next Scan** → File successfully processed

**Key Safety Features:**
- ✅ **OS File Locking** - Prevents moving incomplete files
- ✅ **Error Handling** - Gracefully handles locked files
- ✅ **Retry Logic** - Picks up files on subsequent scans
- ✅ **Detailed Logging** - Track what happens and why

**Why No "Stale File" Check?**
SortMeDown prioritizes **maximum throughput** over additional safety checks, relying on robust OS-level file locking for protection. This approach handles 99% of real-world scenarios effectively.

</details>

---

## 🆘 Troubleshooting

<details>
<summary><strong>🐛 Common issues and solutions</strong></summary>

### API Issues
- **"Invalid API Key"** → Verify your OMDb key in `config.json`
- **"API Limit Exceeded"** → Wait for reset or upgrade your OMDb plan

### File Operations
- **"Permission Denied"** → Check folder permissions and file locks
- **"Path Not Found"** → Verify all paths in `config.json` exist

### Configuration
- **"Config Not Found"** → Run the application once to generate default config
- **Windows Path Issues** → Use forward slashes `/` or double backslashes `\\`

### Performance
- **Slow Processing** → API rate limits are normal, consider TMDB option
- **High Memory Usage** → Large directories may require system resources

</details>

---

## 📄 License

This project is licensed under the **Apache License 2.0** - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Made with ❤️ for media enthusiasts**

[Report Bug](https://github.com/Frederic-LM/Sort-Me-Down/issues) · [Request Feature](https://github.com/Frederic-LM/Sort-Me-Down/issues) · [Contribute](https://github.com/Frederic-LM/Sort-Me-Down/pulls)

</div>
