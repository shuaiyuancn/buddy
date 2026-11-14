import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import config module. Note: when imported, module-level initialization runs.
import src.config
from src.config import (
    initialize_directories, 
    check_api_key_or_toast_and_exit, 
    load_full_config
)

@pytest.fixture
def clean_env():
    """Ensure GEMINI_API_KEY is clean in environment during tests."""
    with patch.dict(os.environ, {}, clear=True):
        yield

@pytest.fixture(autouse=True)
def mock_config_paths(tmp_path):
    """Isolate all config operations to a temporary directory."""
    with patch("src.config.USER_BUDDY_DIR", tmp_path), \
         patch("src.config.TRANSCRIPTS_DIR", tmp_path / "transcripts"), \
         patch("src.config.RECORDINGS_DIR", tmp_path / "recordings"), \
         patch("src.config.CONFIG_FILE", tmp_path / "config.json"):
        yield

def test_initialize_directories():
    # Execute folder check (should use mocked tmp_path)
    initialize_directories()
    
    # Assert folders exist under mock
    assert src.config.TRANSCRIPTS_DIR.exists()
    assert src.config.RECORDINGS_DIR.exists()

def _missing_key_message():
    """Run the key check with the toast stubbed out; return the toast message it would show."""
    with patch("src.config.trigger_toast_and_exit", side_effect=SystemExit(1)) as mock_toast, \
         pytest.raises(SystemExit):
        check_api_key_or_toast_and_exit()
    mock_toast.assert_called_once()
    return mock_toast.call_args.args[0]

def test_check_api_key_valid_from_env(clean_env):
    with patch.dict(os.environ, {"GEMINI_API_KEY": "env-key-xyz"}):
        key = check_api_key_or_toast_and_exit()
        assert key == "env-key-xyz"

def test_check_api_key_missing_env_exits(clean_env):
    # Mock QApplication, QSystemTrayIcon, and time.sleep to assert sys.exit(1)
    with patch('src.config.QApplication'), \
         patch('src.config.QSystemTrayIcon'), \
         patch('time.sleep'), \
         pytest.raises(SystemExit) as exc_info:
        
        check_api_key_or_toast_and_exit()
        
    assert exc_info.value.code == 1

def test_check_api_key_missing_env_message(clean_env):
    message = _missing_key_message()
    assert "GEMINI_API_KEY is not set" in message
    assert 'setx GEMINI_API_KEY "your-key"' in message
    assert "config.json" not in message

def test_check_api_key_blank_env_counts_as_missing(clean_env):
    with patch.dict(os.environ, {"GEMINI_API_KEY": "   "}):
        message = _missing_key_message()
    assert "GEMINI_API_KEY is not set" in message

def test_check_api_key_ignores_key_in_config_file(clean_env):
    src.config.USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    with open(src.config.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"GEMINI_API_KEY": "file-key-abc"}, f)

    # The file key is not used: without the env var the check still fails, with the legacy hint
    message = _missing_key_message()
    assert "The key in config.json is no longer read." in message
    assert "file-key-abc" not in message

    # With the env var set, the env value wins and the file is left untouched
    with patch.dict(os.environ, {"GEMINI_API_KEY": "env-key-xyz"}):
        assert check_api_key_or_toast_and_exit() == "env-key-xyz"
    with open(src.config.CONFIG_FILE, "r", encoding="utf-8") as f:
        assert json.load(f) == {"GEMINI_API_KEY": "file-key-abc"}

def test_check_api_key_no_legacy_hint_for_empty_file_key(clean_env):
    src.config.USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    with open(src.config.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"GEMINI_API_KEY": ""}, f)

    assert "config.json" not in _missing_key_message()

def test_load_full_config_strips_legacy_api_key():
    src.config.USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    with open(src.config.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"GEMINI_API_KEY": "file-key-abc", "AUTO_START": False}, f)

    cfg = load_full_config()
    assert "GEMINI_API_KEY" not in cfg
    assert cfg["AUTO_START"] is False

def test_load_full_config_template_has_no_api_key():
    assert not src.config.CONFIG_FILE.exists()
    cfg = load_full_config()
    assert "GEMINI_API_KEY" not in cfg
    with open(src.config.CONFIG_FILE, "r", encoding="utf-8") as f:
        assert "GEMINI_API_KEY" not in json.load(f)

def test_load_full_config_accepts_utf8_bom():
    # Windows PowerShell 5.1's Set-Content -Encoding UTF8 writes a BOM; older installs have such files
    src.config.USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    with open(src.config.CONFIG_FILE, "w", encoding="utf-8-sig") as f:
        json.dump({"AUTO_START": False, "GEMINI_MODEL": "custom-model"}, f)
    assert src.config.CONFIG_FILE.read_bytes().startswith(b"\xef\xbb\xbf")

    cfg = load_full_config()
    assert cfg["AUTO_START"] is False
    assert cfg["GEMINI_MODEL"] == "custom-model"

def test_save_config_key_accepts_utf8_bom():
    from src.config import save_config_key
    src.config.USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    with open(src.config.CONFIG_FILE, "w", encoding="utf-8-sig") as f:
        json.dump({"GEMINI_MODEL": "custom-model"}, f)

    assert save_config_key("AUTO_START", False) is True
    with open(src.config.CONFIG_FILE, "r", encoding="utf-8") as f:
        assert json.load(f) == {"GEMINI_MODEL": "custom-model", "AUTO_START": False}

def test_load_full_config_defaults():
    cfg = load_full_config()
    assert cfg.get("GEMINI_MODEL") == "gemini-3.5-transcribe"
    assert cfg.get("AUTO_UPDATE") is True
    assert cfg.get("AUTO_START") is True
    assert cfg.get("SAVE_AUDIO_RECORDINGS") is True
    assert cfg.get("RECORDING_FORMAT") == "mp3"
    assert cfg.get("RECORDING_CHUNK_MINUTES") == 10
    assert cfg.get("RECORDING_SAVE_SILENT_CHUNKS") is False


def test_save_config_key(clean_env):
    from src.config import save_config_key, load_full_config
    assert save_config_key("AUTO_START", False) is True
    cfg = load_full_config()
    assert cfg.get("AUTO_START") is False
    assert save_config_key("AUTO_START", True) is True
    cfg2 = load_full_config()
    assert cfg2.get("AUTO_START") is True




def test_save_config_key_does_not_pin_defaults():
    from src.config import save_config_key, load_full_config
    src.config.USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    with open(src.config.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"GEMINI_API_KEY": "k"}, f)

    assert save_config_key("AUTO_START", False) is True

    with open(src.config.CONFIG_FILE, "r", encoding="utf-8") as f:
        assert json.load(f) == {"GEMINI_API_KEY": "k", "AUTO_START": False}
    assert load_full_config()["DICTATION_MODEL"] == "gemini-3.1-flash-lite"
