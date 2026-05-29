import os
import sys
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QStyle
from PySide6.QtGui import QIcon

# 1. Resolve and Establish Directories in user's home Documents folder
USER_DOCUMENTS = Path(os.environ.get("USERPROFILE", "C:\\")) / "Documents" / "Buddy"
TRANSCRIPTS_DIR = USER_DOCUMENTS / "transcripts"
SUMMARIES_DIR = USER_DOCUMENTS / "summaries"

def initialize_directories():
    """
    Ensure the user's storage folders exist.
    """
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)

def check_api_key_or_toast_and_exit():
    """
    Verifies that the GEMINI_API_KEY environment variable is set.
    If missing, fires a Windows native Toast notification and exits immediately.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return api_key

    # Environment variable is missing - trigger native Windows notification
    print("CRITICAL CONFIGURATION ERROR: GEMINI_API_KEY is not set in environment variables.", file=sys.stderr)
    
    # Initialize a dummy QApplication for native tray notification
    app = QApplication.instance() or QApplication(sys.argv)
    tray = QSystemTrayIcon()
    
    # We can use standard warning icon
    style = app.style() if app else QApplication.style()
    critical_icon = style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical)
    tray.setIcon(critical_icon)
    tray.show()
    
    # Send Toast message
    tray.showMessage(
        "Buddy - Config Error",
        "GEMINI_API_KEY is missing! Set the variable in Windows Environment Settings and restart.",
        QSystemTrayIcon.MessageIcon.Critical,
        10000  # Show for 10 seconds
    )
    
    # Allow Qt event loop to process the toast draw event
    time.sleep(3.0)
    sys.exit(1)

# Auto-initialize directories upon module load
initialize_directories()
