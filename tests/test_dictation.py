import os
import json
import tempfile
import shutil
from pathlib import Path
import pytest
from src.config import load_full_config, RECENT_TRANSCRIPTS_FILE
from src.ui.recent_transcripts import RecentTranscriptsManager

@pytest.fixture
def temp_storage_dir():
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)

def test_config_dictation_defaults():
    config = load_full_config()
    assert "DICTATION_HOTKEY" in config
    assert config["DICTATION_HOTKEY"] == "right_alt"
    assert RECENT_TRANSCRIPTS_FILE is not None

def test_recent_transcripts_manager_add_and_cap(temp_storage_dir):
    json_path = temp_storage_dir / "recent_transcripts.json"
    manager = RecentTranscriptsManager(file_path=json_path, max_items=5)

    # Initially empty
    assert manager.get_recent() == []

    # Add 6 transcripts
    for i in range(6):
        manager.add_transcript(f"Transcript number {i}")

    recent = manager.get_recent()
    # Must only retain the 5 most recent
    assert len(recent) == 5
    # The most recent must be at index 0
    assert recent[0]["text"] == "Transcript number 5"
    assert recent[4]["text"] == "Transcript number 1"
    assert "timestamp" in recent[0]

def test_recent_transcripts_persistence(temp_storage_dir):
    json_path = temp_storage_dir / "recent_transcripts.json"
    manager1 = RecentTranscriptsManager(file_path=json_path, max_items=5)
    manager1.add_transcript("Saved to disk test")

    assert json_path.exists()

    # Create a new manager pointing to the same file to verify persistence
    manager2 = RecentTranscriptsManager(file_path=json_path, max_items=5)
    items = manager2.get_recent()
    assert len(items) == 1
    assert items[0]["text"] == "Saved to disk test"

def test_recent_transcripts_clear(temp_storage_dir):
    json_path = temp_storage_dir / "recent_transcripts.json"
    manager = RecentTranscriptsManager(file_path=json_path, max_items=5)
    manager.add_transcript("Item to clear")
    assert len(manager.get_recent()) == 1

    manager.clear()
    assert len(manager.get_recent()) == 0

    # Ensure disk file is also cleared
    manager2 = RecentTranscriptsManager(file_path=json_path, max_items=5)
    assert len(manager2.get_recent()) == 0

def test_audio_stream_handler_dictation_lifecycle():
    import numpy as np
    from src.audio.stream_handler import AudioStreamHandler

    handler = AudioStreamHandler(target_sr=16000, window_duration_sec=60)
    assert handler._is_dictating is False

    handler.start_dictation()
    assert handler._is_dictating is True
    assert handler._dictation_buffer == []

    # Simulate mic audio chunks in mic_queue
    t = np.linspace(0, 1.0, 16000, endpoint=False)
    tone = (np.sin(2 * np.pi * 440.0 * t) * 0.5).astype(np.float32)
    handler.mic_queue.put(tone)

    wav_bytes = handler.stop_dictation()
    assert handler._is_dictating is False
    assert wav_bytes is not None
    assert len(wav_bytes) > 44
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"

def test_transcribe_dictation_silent():
    from src.ai.transcriber import TranscriberService
    service = TranscriberService(api_key="mock-key")
    # Empty or silent returns empty string
    assert service.transcribe_dictation(b"") == ""

def test_transcribe_dictation_with_gemini(temp_storage_dir):
    from unittest.mock import MagicMock
    import numpy as np
    from src.ai.transcriber import TranscriberService, FileAppender
    from src.audio.mixer import AudioMixer

    service = TranscriberService(api_key="mock-key")
    service.appender = FileAppender(temp_storage_dir)

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "Me: This is my dictation statement."
    mock_resp.candidates = []
    mock_client.models.generate_content.return_value = mock_resp
    service.client = mock_client

    t = np.linspace(0, 1.0, 16000, endpoint=False)
    tone = (np.sin(2 * np.pi * 440.0 * t) * 0.5).astype(np.float32)
    wav_bytes = AudioMixer.convert_to_wav_bytes(tone, sample_rate=16000)

    result = service.transcribe_dictation(wav_bytes)
    # Prefix like "Me:" should be stripped for clean dictation
    assert result == "This is my dictation statement."

def test_optimize_dictation_success():
    from unittest.mock import MagicMock
    from src.ai.transcriber import TranscriberService

    service = TranscriberService(api_key="mock-key")
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "Testing dictation. Here is the clean text."
    mock_client.models.generate_content.return_value = mock_resp
    service.client = mock_client

    result = service.optimize_dictation("um testing dictation uh here is the clean text")
    assert result == "Testing dictation. Here is the clean text."
    mock_client.models.generate_content.assert_called_once()

def test_optimize_dictation_fallback_on_error():
    from unittest.mock import MagicMock
    from src.ai.transcriber import TranscriberService

    service = TranscriberService(api_key="mock-key")
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API timeout")
    service.client = mock_client

    raw_text = "um hello world"
    result = service.optimize_dictation(raw_text)
    # Must fallback to the raw text gracefully
    assert result == "um hello world"

def test_parse_hotkey():
    from src.ui.hotkey import parse_hotkey, MOD_NOREPEAT, MOD_CONTROL, MOD_SHIFT, MOD_ALT

    mod, vk = parse_hotkey("right_alt")
    assert vk == 0xA5
    assert mod == MOD_NOREPEAT

    mod, vk = parse_hotkey("ralt")
    assert vk == 0xA5
    assert mod == MOD_NOREPEAT

    mod, vk = parse_hotkey("f9")
    assert vk == 0x78
    assert mod == MOD_NOREPEAT

    mod, vk = parse_hotkey("ctrl+shift+d")
    assert vk == ord("D")
    assert mod & MOD_CONTROL
    assert mod & MOD_SHIFT
    assert mod & MOD_NOREPEAT

def test_text_injector():
    from unittest.mock import patch, MagicMock
    from src.ui.text_injector import TextInjector

    with patch("src.ui.text_injector.QGuiApplication") as mock_qapp, \
         patch("src.ui.text_injector.TextInjector._simulate_paste") as mock_paste:
        mock_clipboard = MagicMock()
        mock_qapp.clipboard.return_value = mock_clipboard

        success = TextInjector.paste_text("Hello injected text")
        assert success is True
        mock_clipboard.setText.assert_called_once_with("Hello injected text")
        mock_paste.assert_called_once()

def test_tray_dictating_state_icon_and_tooltip():
    import sys
    from unittest.mock import MagicMock
    from PySide6.QtWidgets import QApplication
    from src.ui.tray_icon import TrayIconController

    app = QApplication.instance() or QApplication(sys.argv)
    mock_audio = MagicMock()
    mock_transcriber = MagicMock()

    controller = TrayIconController(mock_audio, mock_transcriber)
    icon = controller._draw_tray_icon("dictating")
    assert not icon.isNull()

    controller.set_status("dictating")
    assert controller._current_state == "dictating"
    assert "Dictating" in controller.tray.toolTip()

def test_tray_recent_dictations_menu(temp_storage_dir):
    import sys
    from unittest.mock import MagicMock, patch
    from PySide6.QtWidgets import QApplication
    from src.ui.tray_icon import TrayIconController

    app = QApplication.instance() or QApplication(sys.argv)
    mock_audio = MagicMock()
    mock_transcriber = MagicMock()

    controller = TrayIconController(mock_audio, mock_transcriber)
    assert hasattr(controller, "recent_menu")

    # Add transcripts to manager
    controller.recent_transcripts.add_transcript("First dictation entry")
    controller.recent_transcripts.add_transcript("Second dictation entry")
    controller._update_recent_menu()

    actions = [a.text() for a in controller.recent_menu.actions()]
    assert any("Second dictation entry" in a for a in actions)
    assert any("First dictation entry" in a for a in actions)
    assert any("Clear History" in a for a in actions)

def test_tray_hotkey_toggle_dictation():
    import sys
    from unittest.mock import MagicMock, patch
    from PySide6.QtWidgets import QApplication
    from src.ui.tray_icon import TrayIconController

    app = QApplication.instance() or QApplication(sys.argv)
    mock_audio = MagicMock()
    mock_audio._is_dictating = False
    mock_transcriber = MagicMock()

    controller = TrayIconController(mock_audio, mock_transcriber)

    # First toggle: should start dictation
    controller.on_dictation_hotkey()
    mock_audio.start_dictation.assert_called_once()
    assert controller._current_state == "dictating"

    # Second toggle: should stop dictation
    mock_audio._is_dictating = True
    mock_audio.stop_dictation.return_value = b"RIFF_mock"
    with patch.object(controller.executor, "submit") as mock_submit:
        controller.on_dictation_hotkey()
        mock_audio.stop_dictation.assert_called_once()
        mock_submit.assert_called_once()

def test_altgr_hotkey_parsing():
    from src.ui.hotkey import parse_hotkey, MOD_NOREPEAT

    mod, vk = parse_hotkey("altgr")
    assert vk == 0xA5
    assert mod == MOD_NOREPEAT

    mod, vk = parse_hotkey("alt_gr")
    assert vk == 0xA5
    assert mod == MOD_NOREPEAT

def test_async_key_loop_edge_detection():
    from unittest.mock import patch, MagicMock
    from src.ui.hotkey import GlobalHotkeyListener

    listener = GlobalHotkeyListener(hotkey="right_alt")
    signals_received = []
    listener.hotkey_triggered.connect(lambda: signals_received.append(True))

    # Simulate key sequence: Up -> Down -> Down -> Up -> Down
    # 0x8000 means pressed, 0 means released
    key_states = [0, 0x8000, 0x8000, 0, 0x8000]
    
    with patch("ctypes.windll.user32.GetAsyncKeyState") as mock_get_async:
        mock_get_async.side_effect = lambda vk: key_states.pop(0) if key_states else 0
        with patch("time.sleep") as mock_sleep:
            # Stop the loop after 5 iterations
            def stop_loop(_):
                if not key_states:
                    listener._is_running = False
            mock_sleep.side_effect = stop_loop

            listener._run_async_key_loop()

    # Leading edge should trigger exactly 2 times (first Down, and second Down after release)
    assert len(signals_received) == 2

def test_transcribe_dictation_with_gemini_audio_transcription_parts(temp_storage_dir):
    """
    Verifies that candidate parts with audio_transcription (as returned by gemini-3.5-transcribe)
    are properly extracted rather than returning empty text.
    """
    from unittest.mock import MagicMock
    import numpy as np
    from src.ai.transcriber import TranscriberService, FileAppender
    from src.audio.mixer import AudioMixer

    service = TranscriberService(api_key="mock-key")
    service.appender = FileAppender(temp_storage_dir)

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = None

    mock_part = MagicMock()
    mock_part.text = None
    mock_part.audio_transcription.text = "This is dictated speech from gemini 3.5 transcribe."

    mock_candidate = MagicMock()
    mock_candidate.content.parts = [mock_part]
    mock_resp.candidates = [mock_candidate]
    mock_client.models.generate_content.return_value = mock_resp
    service.client = mock_client

    t = np.linspace(0, 1.0, 16000, endpoint=False)
    tone = (np.sin(2 * np.pi * 440.0 * t) * 0.5).astype(np.float32)
    wav_bytes = AudioMixer.convert_to_wav_bytes(tone, sample_rate=16000)

    result = service.transcribe_dictation(wav_bytes)
    assert result == "This is dictated speech from gemini 3.5 transcribe."

def test_tray_dictation_completed_gui_thread_paste():
    """
    Verifies that _on_dictation_completed on the GUI thread triggers paste and updates history.
    """
    import sys
    from unittest.mock import MagicMock, patch
    from PySide6.QtWidgets import QApplication
    from src.ui.tray_icon import TrayIconController

    app = QApplication.instance() or QApplication(sys.argv)
    mock_audio = MagicMock()
    mock_transcriber = MagicMock()

    controller = TrayIconController(mock_audio, mock_transcriber)
    with patch("src.ui.tray_icon.TextInjector.paste_text") as mock_paste:
        controller._on_dictation_completed("Dictated output for cursor")
        mock_paste.assert_called_once_with("Dictated output for cursor")
        recent = controller.recent_transcripts.get_recent()
        assert len(recent) > 0
        assert recent[0]["text"] == "Dictated output for cursor"

def test_text_injector_releases_alt_modifiers():
    """
    Verifies that _simulate_paste releases Alt modifier keys prior to synthesizing Ctrl+V.
    """
    from unittest.mock import patch, call
    from src.ui.text_injector import TextInjector

    with patch("ctypes.windll.user32.keybd_event") as mock_keybd:
        TextInjector._simulate_paste()
        # Ensure VK_RMENU (0xA5), VK_LMENU (0xA4), VK_MENU (0x12) were called with KEYEVENTF_KEYUP (2)
        key_ups = [c for c in mock_keybd.call_args_list if c[0][2] == 2]
        released_vks = [c[0][0] for c in key_ups]
        assert 0xA5 in released_vks
        assert 0xA4 in released_vks
        assert 0x12 in released_vks
