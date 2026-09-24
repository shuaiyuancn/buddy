import os
import sys
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication
from packaging import version

from src.updater import AutoUpdater

# Ensure QApplication exists for Qt Signal/Slot testing
app = QApplication.instance() or QApplication(sys.argv)

def test_auto_updater_initialization():
    updater = AutoUpdater(current_version="0.1.0", config={"GITHUB_REPO": "shuaiyuancn/buddy", "AUTO_UPDATE": True, "UPDATE_CHECK_INTERVAL_HOURS": 2})
    assert updater.current_version == "0.1.0"
    assert updater.repo == "shuaiyuancn/buddy"
    assert updater.enabled is True
    assert updater.interval_hours == 2.0

def test_check_updates_new_version_found():
    updater = AutoUpdater(current_version="0.1.0", config={"GITHUB_REPO": "shuaiyuancn/buddy", "AUTO_UPDATE": False})
    
    mock_payload = {
        "tag_name": "v0.2.0",
        "assets": [
            {
                "name": "Buddy.exe",
                "browser_download_url": "https://github.com/shuaiyuancn/buddy/releases/download/v0.2.0/Buddy.exe",
                "size": 15000000
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    available_signals = []
    updater.update_available.connect(lambda v, url: available_signals.append((v, url)))

    with patch("requests.get", return_value=mock_resp), patch.object(updater, "apply_update_async") as mock_apply:
        updater._check_worker(manual=True)
        mock_apply.assert_called_once_with("0.2.0", "https://github.com/shuaiyuancn/buddy/releases/download/v0.2.0/Buddy.exe")

    assert len(available_signals) == 1
    assert available_signals[0] == ("0.2.0", "https://github.com/shuaiyuancn/buddy/releases/download/v0.2.0/Buddy.exe")

def test_check_updates_already_latest():
    updater = AutoUpdater(current_version="0.1.0", config={"GITHUB_REPO": "shuaiyuancn/buddy", "AUTO_UPDATE": False})
    
    mock_payload = {
        "tag_name": "v0.1.0",
        "assets": [{"name": "Buddy.exe", "browser_download_url": "https://example.com/Buddy.exe"}]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    available_signals = []
    finished_signals = []
    updater.update_available.connect(lambda v, url: available_signals.append((v, url)))
    updater.check_finished.connect(lambda found, msg: finished_signals.append((found, msg)))

    with patch("requests.get", return_value=mock_resp):
        updater._check_worker(manual=True)

    assert len(available_signals) == 0
    assert len(finished_signals) == 1
    assert finished_signals[0][0] is False
    assert "latest version" in finished_signals[0][1]

def test_check_updates_no_exe_asset():
    updater = AutoUpdater(current_version="0.1.0", config={"GITHUB_REPO": "shuaiyuancn/buddy", "AUTO_UPDATE": False})
    
    mock_payload = {
        "tag_name": "v0.3.0",
        "assets": [{"name": "Source_code.zip", "browser_download_url": "https://example.com/src.zip"}]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    available_signals = []
    finished_signals = []
    updater.update_available.connect(lambda v, url: available_signals.append((v, url)))
    updater.check_finished.connect(lambda found, msg: finished_signals.append((found, msg)))

    with patch("requests.get", return_value=mock_resp):
        updater._check_worker(manual=True)

    assert len(available_signals) == 0
    assert len(finished_signals) == 1
    assert finished_signals[0][0] is False
    assert "no .exe" in finished_signals[0][1]

def test_check_updates_network_error():
    updater = AutoUpdater(current_version="0.1.0", config={"GITHUB_REPO": "shuaiyuancn/buddy", "AUTO_UPDATE": False})
    
    error_signals = []
    updater.update_error.connect(lambda msg: error_signals.append(msg))

    with patch("requests.get", side_effect=Exception("Connection timed out")):
        updater._check_worker(manual=True)

    assert len(error_signals) == 1
    assert "Connection timed out" in error_signals[0]

def test_download_and_swap_worker():
    updater = AutoUpdater(current_version="0.1.0", config={"GITHUB_REPO": "shuaiyuancn/buddy", "AUTO_UPDATE": False})
    
    started_signals = []
    progress_signals = []
    completed_signals = []
    updater.update_started.connect(lambda v: started_signals.append(v))
    updater.update_progress.connect(lambda d, t: progress_signals.append((d, t)))
    updater.update_completed.connect(lambda v: completed_signals.append(v))

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.headers = {"content-length": "20"}
    mock_resp.iter_content.return_value = [b"MZ_DUMMY_EXE_PAYLOAD"]

    with patch("requests.get", return_value=mock_resp):
        updater._download_and_swap_worker("0.2.0", "https://example.com/Buddy.exe")

    assert len(started_signals) == 1
    assert started_signals[0] == "0.2.0"
    assert len(progress_signals) == 1
    assert progress_signals[0] == (len(b"MZ_DUMMY_EXE_PAYLOAD"), 20)
    assert len(completed_signals) == 1
    assert completed_signals[0] == "0.2.0"

def test_spawn_windows_restart_script():
    import subprocess
    updater = AutoUpdater(current_version="0.1.0")

    with patch("subprocess.Popen") as mock_popen, patch("os._exit") as mock_exit:
        updater._spawn_windows_restart_script("C:/temp/Buddy_v0.2.0.exe", "C:/app/Buddy.exe")

        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        assert "powershell" in cmd[0]
        assert "Bypass" in cmd
        assert "Start-Transcript" in cmd[-1]
        assert "Stop-Transcript" in cmd[-1]
        assert "Move-Item" in cmd[-1]
        assert "Start-Process" in cmd[-1]
        assert "Unblock-File" in cmd[-1]
        
        # Verify creationflags uses CREATE_NO_WINDOW and strictly excludes DETACHED_PROCESS
        if os.name == "nt":
            assert kwargs.get("creationflags") == subprocess.CREATE_NO_WINDOW
            assert not (kwargs.get("creationflags", 0) & subprocess.DETACHED_PROCESS)

        mock_exit.assert_called_once_with(0)


def _short_path(path: str) -> str:
    import ctypes
    buf = ctypes.create_unicode_buffer(1024)
    n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
    return buf.value if n else path


@pytest.mark.skipif(os.name != "nt", reason="8.3 short names are Windows-only")
def test_spawn_windows_restart_script_expands_short_paths(tmp_path):
    # Windows PowerShell 5.1's Move-Item cannot resolve 8.3 names like C:\Users\SHUAI~1.YUA,
    # which tempfile.gettempdir() can return. The script must only ever see long paths.
    long_dir = tmp_path / "a long directory name"
    long_dir.mkdir()
    staged = long_dir / "Buddy_v0.2.0.exe"
    staged.write_bytes(b"MZ")
    short_staged = _short_path(str(staged))
    if short_staged == str(staged):
        pytest.skip("8.3 short names are disabled on this volume")

    updater = AutoUpdater(current_version="0.1.0")
    with patch("subprocess.Popen") as mock_popen, patch("os._exit"):
        updater._spawn_windows_restart_script(short_staged, str(long_dir / "Buddy.exe"))

    script = mock_popen.call_args[0][0][-1]
    assert f"$staged = '{os.path.realpath(short_staged)}'" in script
    assert "~" not in script.split("$staged = ")[1].split(";")[0]
    assert "Move-Item -LiteralPath $staged" in script
