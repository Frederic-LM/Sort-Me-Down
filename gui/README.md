The GUI may be used as is providing you have Python on your devise

You may want to compile it to an executable for your machine:

Step 1: Preparation
    Install PyInstaller: If you don't have it, open your command prompt or terminal and install it:
         
    pip install pyinstaller
 
Project Structure: Make sure your final files are in a clean directory. Your structure should look like this:
      
your-project-folder/
├── gui.py
├── bangbang_backend.py
└── icon.ico

    
Step 2: The PyInstaller Command

On windows: 
Open a command prompt or terminal in your project folder and run the following command:
 
pyinstaller --onefile --windowed --hidden-import="pystray._win32" --icon="icon.ico" gui.py

Inside the dist this folder, you will find your final gui.exe file that can be shared and run without python installed.


on MacOS

# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
# Install Python
brew install python
#Install Dependencies
pip3 install pyinstaller customtkinter requests pystray
You will need to use icon.icns file instead of the icon.ico

then run :
pyinstaller --onefile --windowed --hidden-import="pystray._darwin" --icon="icon.icns" gui.py

this will create the executable inside the dist folder
Security & Gatekeeper (IMPORTANT!): The very first time you run the app, macOS security (Gatekeeper) will likely block it because it's from an "unidentified developer" (i.e., you haven't paid Apple for a developer certificate). To run it, your users must right-click the gui.app file and select "Open". They will then get a dialog box that has a new "Open" button, allowing them to run the app. They only need to do this once.Config File Location: The config.json file will be created next to gui.app inside the dist folder.
Distribute: You can zip the gui.app file and give it to any other Mac user. Just remember to include the instructions for them to "Right-click and Open" it the first time.


    
