## Usage

There are two primary ways to run the SortMeDown GUI for bangbang.py

### Option 1: Running from Source (with Python)

This is the recommended method for developers or users who have Python installed on their system.

1.  **Install Dependencies:**
    Open a terminal or command prompt and install the required Python packages:
    ```bash
    pip install customtkinter requests pystray
    ```
    > **Note for Linux Users:** You may need to install `tkinter` separately if it wasn't included with your Python installation. For Debian/Ubuntu, use: `sudo apt install python3-tk`.

2.  **Run the Application:**
    Navigate to the project directory and run the `gui.py` script:
    ```bash
    python gui.py
    ```

---

### Option 2: Compiling into a Standalone Executable

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
    pyinstaller --onefile --windowed --hidden-import="pystray._darwin" --icon="icon.icns" gui.py
    ```

4.  **Find and Run Your Application:**
    The `dist` folder will contain your final `gui.app` bundle.

    > **Gatekeeper Security Warning (CRITICAL!)**
    > The first time you run the app, macOS will likely block it as it's from an "unidentified developer."
    >
    > **To run it, you must right-click the `gui.app` file and select "Open" from the context menu.**
    >
    > A dialog will appear with an "Open" button that will allow you to run the application. This only needs to be done once.
