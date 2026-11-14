import os
import sys
import time
import json
from pathlib import Path
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QStyle
from PySide6.QtGui import QIcon
from src.version import __version__

# 1. Resolve and Establish Directories in user's hidden home directory
USER_BUDDY_DIR = Path(os.environ.get("USERPROFILE", "C:\\")) / ".buddy"
TRANSCRIPTS_DIR = USER_BUDDY_DIR / "transcripts"
RECORDINGS_DIR = USER_BUDDY_DIR / "recordings"
DICTATIONS_DIR = USER_BUDDY_DIR / "dictations"
LOGS_DIR = USER_BUDDY_DIR / "logs"
DICTATION_VOCABULARY_FILE = USER_BUDDY_DIR / "dictation_vocabulary.txt"
SUMMARIES_DIR = USER_BUDDY_DIR / "summaries"
CONFIG_FILE = USER_BUDDY_DIR / "config.json"
RECENT_TRANSCRIPTS_FILE = USER_BUDDY_DIR / "recent_transcripts.json"
APP_VERSION = __version__

def initialize_directories():
    """
    Ensure the user's storage folders exist.
    """
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    DICTATIONS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

def load_full_config():
    """
    Load full configuration from CONFIG_FILE. If missing, auto-creates a 
    template config.json with all options.
    Returns the parsed configuration dictionary.
    The Gemini API key is read only from the GEMINI_API_KEY environment variable, so a legacy
    GEMINI_API_KEY entry in config.json is ignored and never included in the returned dictionary.
    """
    USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    
    default_config = {
        "GEMINI_MODEL": "gemini-3.5-transcribe",
        "GITHUB_REPO": "shuaiyuancn/buddy",
        "AUTO_UPDATE": True,
        "UPDATE_CHECK_INTERVAL_HOURS": 1,
        "AUTO_START": True,
        "DICTATION_HOTKEY": "right_alt",
        "DICTATION_MODEL": "gemini-3.1-flash-lite",
        "DICTATION_THINKING_LEVEL": "",
        "MICROPHONE_DEVICE_ID": "",
        "SPEAKER_DEVICE_ID": "",
        "SAVE_AUDIO_RECORDINGS": True,
        "RECORDING_FORMAT": "mp3",
        "RECORDING_CHUNK_MINUTES": 10,
        "RECORDING_SAVE_SILENT_CHUNKS": False
    }

    if not CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
        except Exception as e:
            print(f"[Warning] Failed to write default config template to {CONFIG_FILE}: {e}", file=sys.stderr)
        return default_config

    try:
        # utf-8-sig also accepts files written with a BOM (e.g. by older installers on PowerShell 5.1)
        with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return default_config
            merged = {**default_config, **data}
            merged.pop("GEMINI_API_KEY", None)
            return merged
    except Exception as e:
        print(f"[Warning] Failed to parse {CONFIG_FILE}: {e}", file=sys.stderr)
        return default_config


def save_config_key(key: str, value) -> bool:
    """
    Updates or inserts a key-value pair in CONFIG_FILE.
    Only the keys already in the file plus this one are written: persisting every default would
    pin them (e.g. DICTATION_MODEL) and stop future releases from improving them.
    Returns True if successfully saved, False otherwise.
    """
    try:
        current_config = {}
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                current_config = loaded
        current_config[key] = value
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(current_config, f, indent=4)
        return True
    except Exception as e:
        print(f"[Warning] Failed to update {key} in {CONFIG_FILE}: {e}", file=sys.stderr)
        return False


def trigger_toast_and_exit(message: str, title: str = "Buddy - Config Error", critical: bool = True, exit_code: int = 1):
    """
    Triggers a native Windows Toast notification and exits immediately.
    Defaults to a critical configuration-error toast; pass critical=False for an informational one.
    """
    if critical:
        print(f"CRITICAL CONFIGURATION ERROR: {message}", file=sys.stderr)
    else:
        print(f"[Buddy] {message}")

    # Initialize a dummy QApplication for native tray notification
    app = QApplication.instance() or QApplication(sys.argv)
    tray = QSystemTrayIcon()

    # We can use standard MessageBox icons
    style = app.style() if app else QApplication.style()
    pixmap = QStyle.StandardPixmap.SP_MessageBoxCritical if critical else QStyle.StandardPixmap.SP_MessageBoxInformation
    tray.setIcon(style.standardIcon(pixmap))
    tray.show()

    # Send Toast message instructing user of the specific issue
    tray.showMessage(
        title,
        message,
        QSystemTrayIcon.MessageIcon.Critical if critical else QSystemTrayIcon.MessageIcon.Information,
        10000  # Show for 10 seconds
    )

    # Allow Qt event loop to process the toast draw event
    time.sleep(3.0)
    sys.exit(exit_code)

def _config_file_has_legacy_api_key() -> bool:
    """
    True if config.json still holds a non-empty GEMINI_API_KEY from an older version of Buddy.
    The value itself is never returned, used or logged; it only drives a hint in the startup toast.
    """
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        value = data.get("GEMINI_API_KEY") if isinstance(data, dict) else None
        return isinstance(value, str) and bool(value.strip())
    except Exception:
        return False

def check_api_key_or_toast_and_exit():
    """
    Verifies that the GEMINI_API_KEY environment variable is set; it is the only source of the key.
    If it is missing or blank, fires a native Windows Toast notification and exits immediately.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    # Always verify GEMINI_API_KEY (needed for speech-to-text)
    if not api_key:
        message = (
            "GEMINI_API_KEY is not set. Buddy reads it only from the environment variable. "
            'Run: setx GEMINI_API_KEY "your-key" then start Buddy again.'
        )
        if _config_file_has_legacy_api_key():
            message += " The key in config.json is no longer read."
        trigger_toast_and_exit(message)

    return api_key

# Auto-initialize directories upon module load
initialize_directories()


