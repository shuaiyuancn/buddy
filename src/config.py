import os
import sys
import time
import json
from pathlib import Path
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QStyle
from PySide6.QtGui import QIcon

# 1. Resolve and Establish Directories in user's hidden home directory
USER_BUDDY_DIR = Path(os.environ.get("USERPROFILE", "C:\\")) / ".buddy"
TRANSCRIPTS_DIR = USER_BUDDY_DIR / "transcripts"
SUMMARIES_DIR = USER_BUDDY_DIR / "summaries"
CONFIG_FILE = USER_BUDDY_DIR / "config.json"

def initialize_directories():
    """
    Ensure the user's storage folders exist.
    """
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)

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

def check_api_key_or_toast_and_exit():
    """
    Verifies that the GEMINI_API_KEY is configured.
    Checks the local configuration file config.json first, and falls back to
    the environment variable. If missing/empty everywhere, fires a native Windows 
    Toast notification and exits immediately.
    """
    # 1. Look up in ~/.buddy/config.json
    api_key = load_config()

    # 2. Fallback to GEMINI_API_KEY environment variable
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "")

    if api_key:
        return api_key

    # Both missing - trigger native Windows notification
    print("CRITICAL CONFIGURATION ERROR: GEMINI_API_KEY is not configured.", file=sys.stderr)
    print(f"Please write your key inside '{CONFIG_FILE}' or set the GEMINI_API_KEY environment variable.", file=sys.stderr)
    
    # Initialize a dummy QApplication for native tray notification
    app = QApplication.instance() or QApplication(sys.argv)
    tray = QSystemTrayIcon()
    
    # We can use standard critical MessageBox icon
    style = app.style() if app else QApplication.style()
    critical_icon = style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical)
    tray.setIcon(critical_icon)
    tray.show()
    
    # Send Toast message instructing user to check the newly created config file
    tray.showMessage(
        "Buddy - Config Error",
        f"GEMINI_API_KEY is missing! Enter your key in {CONFIG_FILE} and restart.",
        QSystemTrayIcon.MessageIcon.Critical,
        10000  # Show for 10 seconds
    )
    
    # Allow Qt event loop to process the toast draw event
    time.sleep(3.0)
    sys.exit(1)

# Auto-initialize directories upon module load
initialize_directories()

