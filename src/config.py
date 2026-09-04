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
        "STT_PROVIDER": "gemini",
        "GCP_PROJECT_ID": "",
        "GCP_REGION": "us",
        "GCP_SERVICE_ACCOUNT_KEY_PATH": "",
        "GCP_LANGUAGES": ["zh-CN", "en-US"],
        "GITHUB_REPO": "shuaiyuancn/buddy",
        "AUTO_UPDATE": True,
        "UPDATE_CHECK_INTERVAL_HOURS": 1
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
    
    If STT_PROVIDER is "gcp", it also verifies GCP_PROJECT_ID is present, and
    that either GCP_SERVICE_ACCOUNT_KEY_PATH is specified or GOOGLE_APPLICATION_CREDENTIALS
    is present in the environment.
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

    # 4. If STT_PROVIDER is gcp, perform additional checks
    stt_provider = config.get("STT_PROVIDER", "gemini").lower()
    if stt_provider == "gcp":
        project_id = config.get("GCP_PROJECT_ID", "") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        if not project_id:
            trigger_toast_and_exit("GCP_PROJECT_ID is missing for GCP STT! Configure it in config.json.")

        sa_path = config.get("GCP_SERVICE_ACCOUNT_KEY_PATH", "")
        has_env_credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") is not None
        if not sa_path and not has_env_credentials:
            trigger_toast_and_exit("GCP credentials missing! Provide a service account key path or environment credentials.")

    return api_key

# Auto-initialize directories upon module load
initialize_directories()


