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
    load_config
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
         patch("src.config.CONFIG_FILE", tmp_path / "config.json"):
        yield

def test_initialize_directories():
    # Execute folder check (should use mocked tmp_path)
    initialize_directories()
    
    # Assert folder exists under mock
    assert src.config.TRANSCRIPTS_DIR.exists()

def test_load_config_creates_template():
    # Ensure config file doesn't exist initially
    assert not src.config.CONFIG_FILE.exists()
    
    # load_config should create template and return empty string
    key = load_config()
    assert key == ""
    assert src.config.CONFIG_FILE.exists()
    
    # Verify content is JSON with empty key
    with open(src.config.CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data == {"GEMINI_API_KEY": ""}

def test_load_config_reads_existing_key():
    # Pre-create config with key
    src.config.USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    with open(src.config.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"GEMINI_API_KEY": "file-secret-key-123"}, f)
        
    key = load_config()
    assert key == "file-secret-key-123"

def test_load_config_handles_invalid_json():
    # Pre-create corrupt file
    src.config.USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    with open(src.config.CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write("{invalid-json")
        
    key = load_config()
    assert key == ""

def test_check_api_key_valid_from_file(clean_env):
    # Setup key in file
    src.config.USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    with open(src.config.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"GEMINI_API_KEY": "file-key-abc"}, f)
        
    key = check_api_key_or_toast_and_exit()
    assert key == "file-key-abc"

def test_check_api_key_valid_from_env(clean_env):
    # Setup empty key in file to trigger environment fallback
    src.config.USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    with open(src.config.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"GEMINI_API_KEY": ""}, f)
        
    with patch.dict(os.environ, {"GEMINI_API_KEY": "env-key-xyz"}):
        key = check_api_key_or_toast_and_exit()
        assert key == "env-key-xyz"

def test_check_api_key_missing_everywhere_exits(clean_env):
    # Ensure empty file config
    src.config.USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    with open(src.config.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"GEMINI_API_KEY": ""}, f)
        
    # Mock QApplication, QSystemTrayIcon, and time.sleep to assert sys.exit(1)
    with patch('src.config.QApplication'), \
         patch('src.config.QSystemTrayIcon'), \
         patch('time.sleep'), \
         pytest.raises(SystemExit) as exc_info:
        
        check_api_key_or_toast_and_exit()
        
    assert exc_info.value.code == 1

def test_check_api_key_valid_from_keyring(clean_env):
    src.config.USER_BUDDY_DIR.mkdir(parents=True, exist_ok=True)
    with open(src.config.CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"GEMINI_API_KEY": ""}, f)

    with patch("src.config.get_secure_api_key", return_value="keyring-stored-secret-key"):
        key = check_api_key_or_toast_and_exit()
        assert key == "keyring-stored-secret-key"

def test_load_full_config_defaults():
    from src.config import load_full_config
    cfg = load_full_config()
    assert cfg.get("GEMINI_MODEL") == "gemini-3.5-transcribe"
    assert cfg.get("STT_PROVIDER") == "gemini"
    assert cfg.get("AUTO_UPDATE") is True

