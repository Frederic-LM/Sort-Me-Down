# bangbang_engine/__init__.py

# Expose the main classes and enums at the top level of the package
# This allows the GUI to import them with `import bangbang_engine as backend`
# and access them like `backend.MediaSorter`, `backend.MediaType`, etc.

from .bangbang import MediaSorter
from .api import APIClient
from .config import Config
from .file_manager import FileManager
from .models import MediaType, MediaInfo
from .utils import TitleCleaner, setup_logging
