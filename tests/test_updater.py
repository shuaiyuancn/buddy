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

    with patch("requests.get", return_value=mock_resp):
        updater._check_worker(manual=True)

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
    completed_signals = []
    updater.update_started.connect(lambda v: started_signals.append(v))
    updater.update_completed.connect(lambda v: completed_signals.append(v))

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.iter_content.return_value = [b"MZ_DUMMY_EXE_PAYLOAD"]

    with patch("requests.get", return_value=mock_resp):
        updater._download_and_swap_worker("0.2.0", "https://example.com/Buddy.exe")

    assert len(started_signals) == 1
    assert started_signals[0] == "0.2.0"
    assert len(completed_signals) == 1
    assert completed_signals[0] == "0.2.0"
