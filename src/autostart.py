"""
Windows Auto-Start Manager for Buddy.
Manages application startup on user login via Windows Startup folder shortcuts.
"""

import os
import sys
import subprocess
from pathlib import Path


def get_startup_shortcut_path(app_name: str = "Buddy") -> Path:
    """
    Returns the path to the application's shortcut inside the Windows Startup folder.
    """
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{app_name}.lnk"


def is_autostart_enabled(app_name: str = "Buddy") -> bool:
    """
    Checks if the autostart shortcut exists in the Windows Startup folder.
    """
    return get_startup_shortcut_path(app_name).exists()


def set_autostart_enabled(enable: bool, app_name: str = "Buddy", exe_path: str = None) -> bool:
    """
    Enables or disables auto-start on Windows login by creating or deleting
    the shortcut in the Windows Startup directory.
    """
    shortcut_path = get_startup_shortcut_path(app_name)

    if not enable:
        if shortcut_path.exists():
            try:
                shortcut_path.unlink()
                return True
            except Exception as e:
                print(f"[Warning] Failed to remove autostart shortcut: {e}", file=sys.stderr)
                return False
        return True

    # Enable autostart
    try:
        shortcut_path.parent.mkdir(parents=True, exist_ok=True)
        if not exe_path:
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = os.path.expandvars(r"%LOCALAPPDATA%\Buddy\Buddy.exe")

        work_dir = os.path.dirname(os.path.abspath(exe_path))

        ps_cmd = (
            f"$w = New-Object -ComObject WScript.Shell; "
            f"$s = $w.CreateShortcut('{str(shortcut_path)}'); "
            f"$s.TargetPath = '{exe_path}'; "
            f"$s.WorkingDirectory = '{work_dir}'; "
            f"$s.Description = 'Buddy - Background Audio Transcriber (Auto-Start)'; "
            f"$s.Save()"
        )

        subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-NoProfile", "-Command", ps_cmd],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            capture_output=True,
            check=True
        )
        return shortcut_path.exists()
    except Exception as e:
        print(f"[Warning] Failed to create autostart shortcut: {e}", file=sys.stderr)
        return False


def ensure_autostart_state(enabled: bool, app_name: str = "Buddy", exe_path: str = None) -> bool:
    """
    Idempotently ensures that the auto-start shortcut state matches the configuration.
    """
    current = is_autostart_enabled(app_name)
    if current != enabled:
        return set_autostart_enabled(enabled, app_name, exe_path)
    return True
