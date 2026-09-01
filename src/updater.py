import os
import sys
import time
import json
import tempfile
import subprocess
import threading
import requests
from pathlib import Path
from packaging import version
from PySide6.QtCore import QObject, Signal, QTimer, Slot

from src.version import __version__
from src.config import load_full_config

class AutoUpdater(QObject):
    """
    Manages periodic background checking for updates via GitHub Releases API,
    downloading new versions, and orchestrating safe atomic in-place updates on Windows.
    """
    update_available = Signal(str, str)     # version, download_url
    update_started = Signal(str)           # version
    update_completed = Signal(str)         # version
    update_error = Signal(str)             # error_message
    check_finished = Signal(bool, str)     # update_found, message_or_version

    def __init__(self, current_version: str = __version__, config: dict = None, parent=None):
        super().__init__(parent)
        self.current_version = current_version
        self.config = config or load_full_config()
        self.repo = self.config.get("GITHUB_REPO", "shuaiyuancn/buddy")
        self.enabled = self.config.get("AUTO_UPDATE", True)
        self.interval_hours = float(self.config.get("UPDATE_CHECK_INTERVAL_HOURS", 1))

        self._is_updating = False
        self._lock = threading.Lock()

        # Qt Timer for 1-hour periodic background checks
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_for_updates_async)

    def start(self):
        """
        Starts the auto-update timer (and triggers an initial check after 15 seconds).
        """
        if not self.enabled:
            return

        # Schedule initial check 15 seconds after app startup
        QTimer.singleShot(15000, self.check_for_updates_async)

        # Convert hours to milliseconds (1 hour = 3,600,000 ms)
        interval_ms = int(max(0.1, self.interval_hours) * 3600 * 1000)
        self.timer.start(interval_ms)

    def stop(self):
        """
        Stops the periodic timer.
        """
        if self.timer.isActive():
            self.timer.stop()

    def check_for_updates_async(self, manual: bool = False):
        """
        Dispatches an update check in a background worker thread.
        """
        worker = threading.Thread(target=self._check_worker, args=(manual,), daemon=True)
        worker.start()

    def _check_worker(self, manual: bool = False):
        """
        Queries GitHub API and evaluates release versions.
        """
        try:
            headers = {
                "User-Agent": f"Buddy-App/{self.current_version}",
                "Accept": "application/vnd.github.v3+json"
            }
            api_url = f"https://api.github.com/repos/{self.repo}/releases/latest"
            
            resp = requests.get(api_url, headers=headers, timeout=10)
            if resp.status_code == 404:
                # Fallback to general releases if latest is not indexed yet
                fallback_url = f"https://api.github.com/repos/{self.repo}/releases"
                fallback_resp = requests.get(fallback_url, headers=headers, timeout=10)
                if fallback_resp.status_code == 200 and fallback_resp.json():
                    release_data = fallback_resp.json()[0]
                else:
                    if manual:
                        self.check_finished.emit(False, "No releases found on GitHub.")
                    return
            elif resp.status_code == 200:
                release_data = resp.json()
            else:
                msg = f"GitHub API returned status {resp.status_code}"
                if manual:
                    self.update_error.emit(msg)
                    self.check_finished.emit(False, msg)
                return

            tag_name = release_data.get("tag_name", "").lstrip("v")
            if not tag_name:
                if manual:
                    self.check_finished.emit(False, "Release tag format invalid.")
                return

            # Compare semantic versions
            current_v = version.parse(self.current_version)
            latest_v = version.parse(tag_name)

            if latest_v > current_v:
                # Find exe download URL
                assets = release_data.get("assets", [])
                exe_asset = next(
                    (a for a in assets if a.get("name", "").endswith(".exe")),
                    None
                )
                if exe_asset:
                    download_url = exe_asset.get("browser_download_url")
                    self.update_available.emit(tag_name, download_url)
                    self.check_finished.emit(True, tag_name)
                    
                    # If auto-update is enabled, proceed to download and install
                    if self.enabled and not manual:
                        self.apply_update_async(tag_name, download_url)
                else:
                    if manual:
                        self.check_finished.emit(False, f"New version {tag_name} found, but no .exe asset attached.")
            else:
                if manual:
                    self.check_finished.emit(False, f"You are running the latest version (v{self.current_version}).")

        except Exception as e:
            if manual:
                self.update_error.emit(f"Update check failed: {str(e)}")
                self.check_finished.emit(False, str(e))

    def apply_update_async(self, new_version_tag: str, download_url: str):
        """
        Dispatches download and binary swap in a background worker thread.
        """
        with self._lock:
            if self._is_updating:
                return
            self._is_updating = True

        worker = threading.Thread(
            target=self._download_and_swap_worker,
            args=(new_version_tag, download_url),
            daemon=True
        )
        worker.start()

    def _download_and_swap_worker(self, new_version_tag: str, download_url: str):
        """
        Downloads the new executable and triggers detached process restart.
        """
        self.update_started.emit(new_version_tag)
        try:
            # Determine current executable path
            if getattr(sys, 'frozen', False):
                current_exe = sys.executable
            else:
                # Running from source, simulate download to temp
                current_exe = os.path.abspath(sys.argv[0])

            # Download new binary to temporary file
            temp_dir = tempfile.gettempdir()
            staged_exe = os.path.join(temp_dir, f"Buddy_v{new_version_tag}.exe")

            resp = requests.get(download_url, stream=True, timeout=60)
            resp.raise_for_status()

            with open(staged_exe, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

            self.update_completed.emit(new_version_tag)

            # If we're running as a compiled frozen .exe, perform the atomic process restart swap
            if getattr(sys, 'frozen', False):
                self._spawn_windows_restart_script(staged_exe, current_exe)

        except Exception as e:
            with self._lock:
                self._is_updating = False
            self.update_error.emit(f"Failed to apply update: {str(e)}")

    def _spawn_windows_restart_script(self, staged_exe: str, current_exe: str):
        """
        Launches a detached hidden PowerShell helper process that waits for the current
        PID to exit, replaces Buddy.exe with the new binary, and launches the updated application.
        """
        pid = os.getpid()
        ps_command = (
            f"$targetPid = {pid}; "
            f"$staged = '{staged_exe}'; "
            f"$dest = '{current_exe}'; "
            f"while (Get-Process -Id $targetPid -ErrorAction SilentlyContinue) {{ Start-Sleep -Milliseconds 200 }}; "
            f"Move-Item -Path $staged -Destination $dest -Force; "
            f"Start-Process -FilePath $dest"
        )

        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-Command", ps_command],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS if os.name == 'nt' else 0,
            close_fds=True
        )

        # Trigger clean exit of current instance
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.quit()
        sys.exit(0)
