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
SUMMARIES_DIR = USER_BUDDY_DIR / "summaries"
CONFIG_FILE = USER_BUDDY_DIR / "config.json"
RECENT_TRANSCRIPTS_FILE = USER_BUDDY_DIR / "recent_transcripts.json"
APP_VERSION = __version__

def initialize_directories():
    """
    Ensure the user's storage folders exist.
    """
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

def load_config():
    """
    Load configuration from CONFIG_FILE. If missing, auto-creates a 
    template config.json with {"GEMINI_API_KEY": ""}.
    Returns the parsed GEMINI_API_KEY or empty string if empty/missing/invalid.
    """
    USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"GEMINI_API_KEY": ""}, f, indent=4)
        except Exception as e:
            print(f"[Warning] Failed to write default config template to {CONFIG_FILE}: {e}", file=sys.stderr)
        return ""

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("GEMINI_API_KEY", "")
    except Exception as e:
        print(f"[Warning] Failed to parse {CONFIG_FILE}: {e}", file=sys.stderr)
        return ""

def load_full_config():
    """
    Load full configuration from CONFIG_FILE. If missing, auto-creates a 
    template config.json with all options.
    Returns the parsed configuration dictionary.
    """
    USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    
    default_config = {
        "GEMINI_API_KEY": "",
        "GEMINI_MODEL": "gemini-3.5-transcribe",
        "GITHUB_REPO": "shuaiyuancn/buddy",
        "AUTO_UPDATE": True,
        "UPDATE_CHECK_INTERVAL_HOURS": 1,
        "AUTO_START": True,
        "DICTATION_HOTKEY": "right_alt",
        "DICTATION_MODEL": "gemini-3.5-flash-lite"
    }

    if not CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
        except Exception as e:
            print(f"[Warning] Failed to write default config template to {CONFIG_FILE}: {e}", file=sys.stderr)
        return default_config

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return default_config
            merged = {**default_config, **data}
            return merged
    except Exception as e:
        print(f"[Warning] Failed to parse {CONFIG_FILE}: {e}", file=sys.stderr)
        return default_config


def save_config_key(key: str, value) -> bool:
    """
    Updates or inserts a key-value pair in CONFIG_FILE.
    Returns True if successfully saved, False otherwise.
    """
    try:
        current_config = load_full_config()
        current_config[key] = value
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(current_config, f, indent=4)
        return True
    except Exception as e:
        print(f"[Warning] Failed to update {key} in {CONFIG_FILE}: {e}", file=sys.stderr)
        return False


def trigger_toast_and_exit(message: str):
    """
    Triggers a native Windows critical Toast notification and exits immediately.
    """
    print(f"CRITICAL CONFIGURATION ERROR: {message}", file=sys.stderr)
    
    # Initialize a dummy QApplication for native tray notification
    app = QApplication.instance() or QApplication(sys.argv)
    tray = QSystemTrayIcon()
    
    # We can use standard critical MessageBox icon
    style = app.style() if app else QApplication.style()
    critical_icon = style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical)
    tray.setIcon(critical_icon)
    tray.show()
    
    # Send Toast message instructing user of the specific configuration error
    tray.showMessage(
        "Buddy - Config Error",
        message,
        QSystemTrayIcon.MessageIcon.Critical,
        10000  # Show for 10 seconds
    )
    
    # Allow Qt event loop to process the toast draw event
    time.sleep(3.0)
    sys.exit(1)

def get_secure_api_key(service_name: str = "Buddy", username: str = "GEMINI_API_KEY") -> str:
    """
    Attempts to retrieve the API key from the OS secure Credential Manager/Keyring.
    """
    try:
        import keyring
        val = keyring.get_password(service_name, username)
        return val or ""
    except Exception:
        return ""

def set_secure_api_key(api_key: str, service_name: str = "Buddy", username: str = "GEMINI_API_KEY") -> bool:
    """
    Attempts to store the API key securely into the OS Credential Manager/Keyring.
    """
    try:
        import keyring
        keyring.set_password(service_name, username, api_key)
        return True
    except Exception:
        return False

def check_api_key_or_toast_and_exit():
    """
    Verifies that the GEMINI_API_KEY is configured.
    Checks config.json first, then environment variables, then the OS secure keyring.
    If missing/empty everywhere, fires a native Windows Toast notification and exits immediately.
    """
    # 1. Load full config
    config = load_full_config()
    api_key = config.get("GEMINI_API_KEY", "")

    # 2. Fallback to GEMINI_API_KEY environment variable
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "")

    # 3. Fallback to secure OS keyring
    if not api_key:
        api_key = get_secure_api_key()

    # Always verify GEMINI_API_KEY (needed for speech-to-text)
    if not api_key:
        trigger_toast_and_exit(f"GEMINI_API_KEY is missing! Enter your key in {CONFIG_FILE} and restart.")

    return api_key

# Auto-initialize directories upon module load
initialize_directories()


