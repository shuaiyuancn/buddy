import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.autostart import (
    get_startup_shortcut_path,
    is_autostart_enabled,
    set_autostart_enabled,
    ensure_autostart_state
)


def test_get_startup_shortcut_path():
    path = get_startup_shortcut_path("Buddy")
    assert path.name == "Buddy.lnk"
    assert "Startup" in str(path)


def test_is_autostart_enabled():
    with patch("pathlib.Path.exists", return_value=True):
        assert is_autostart_enabled("Buddy") is True
    with patch("pathlib.Path.exists", return_value=False):
        assert is_autostart_enabled("Buddy") is False


def test_set_autostart_disabled_removes_file(tmp_path):
    fake_lnk = tmp_path / "Buddy.lnk"
    fake_lnk.touch()
    assert fake_lnk.exists()

    with patch("src.autostart.get_startup_shortcut_path", return_value=fake_lnk):
        res = set_autostart_enabled(False, "Buddy")
        assert res is True
        assert not fake_lnk.exists()


def test_set_autostart_disabled_when_not_existing(tmp_path):
    fake_lnk = tmp_path / "NonExistent.lnk"
    with patch("src.autostart.get_startup_shortcut_path", return_value=fake_lnk):
        res = set_autostart_enabled(False, "NonExistent")
        assert res is True


def test_set_autostart_enabled_executes_powershell(tmp_path):
    fake_lnk = tmp_path / "Buddy.lnk"
    with patch("src.autostart.get_startup_shortcut_path", return_value=fake_lnk), \
         patch("subprocess.run") as mock_run:
        # Simulate powershell creating the link
        def side_effect(*args, **kwargs):
            fake_lnk.touch()
            return MagicMock()
        mock_run.side_effect = side_effect

        res = set_autostart_enabled(True, "Buddy", exe_path="C:\\app\\Buddy.exe")
        assert res is True
        assert fake_lnk.exists()
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert "powershell" in cmd[0]
        assert "CreateShortcut" in cmd[-1]
        assert "C:\\app\\Buddy.exe" in cmd[-1]


def test_ensure_autostart_state_noop_if_already_matches():
    with patch("src.autostart.is_autostart_enabled", return_value=True), \
         patch("src.autostart.set_autostart_enabled") as mock_set:
        res = ensure_autostart_state(True)
        assert res is True
        mock_set.assert_not_called()


def test_ensure_autostart_state_updates_if_different():
    with patch("src.autostart.is_autostart_enabled", return_value=False), \
         patch("src.autostart.set_autostart_enabled", return_value=True) as mock_set:
        res = ensure_autostart_state(True)
        assert res is True
        mock_set.assert_called_once_with(True, "Buddy", None)
