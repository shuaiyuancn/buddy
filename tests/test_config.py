import os
import pytest
from unittest.mock import patch, MagicMock
from src.config import initialize_directories, check_api_key_or_toast_and_exit, TRANSCRIPTS_DIR, SUMMARIES_DIR

def test_initialize_directories():
    # Execute folder check
    initialize_directories()
    
    # Assert folders exist
    assert TRANSCRIPTS_DIR.exists()
    assert SUMMARIES_DIR.exists()

def test_check_api_key_valid_env():
    # Mock environment variable
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-abc-123"}):
        key = check_api_key_or_toast_and_exit()
        assert key == "test-key-abc-123"

def test_check_api_key_missing_env_exits():
    # Ensure GEMINI_API_KEY is missing
    with patch.dict(os.environ, {}, clear=True):
        # Mock QApplication and QSystemTrayIcon to prevent actual UI rendering during automated test runs
        with patch('src.config.QApplication'), \
             patch('src.config.QSystemTrayIcon'), \
             patch('time.sleep'), \
             pytest.raises(SystemExit) as exc_info:
            
            check_api_key_or_toast_and_exit()
            
        assert exc_info.value.code == 1
