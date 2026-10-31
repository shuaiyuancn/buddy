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

def test_text_injector_releases_held_alt_with_menu_mask():
    """
    A still-held Right Alt is released before Ctrl+V (else it becomes Ctrl+Alt+V), preceded by the
    menu-mask key so the release does not activate the target app's menu bar.
    """
    from unittest.mock import patch
    from src.ui.text_injector import TextInjector
    from src.ui.hotkey import VK_MENU_MASK

    held = {0xA5}
    with patch("ctypes.windll.user32.GetAsyncKeyState", side_effect=lambda vk: 0x8000 if vk in held else 0), \
         patch("ctypes.windll.user32.keybd_event") as mock_keybd:
        TextInjector._simulate_paste()

    events = [(c[0][0], c[0][2]) for c in mock_keybd.call_args_list]
    assert events.index((VK_MENU_MASK, 0)) < events.index((0xA5, 2)) < events.index((0x11, 0))
    assert (0xA4, 2) not in events and (0x12, 2) not in events
    assert [e for e in events if e[0] in (0x11, 0x56)] == [(0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2)]


def test_text_injector_sends_no_stray_alt_keyups_when_alt_is_released():
    """
    A lone Alt key-up can itself open the target app's menu bar and swallow the paste,
    so nothing but Ctrl+V is sent when no Alt key is held.
    """
    from unittest.mock import patch
    from src.ui.text_injector import TextInjector

    with patch("ctypes.windll.user32.GetAsyncKeyState", return_value=0), \
         patch("ctypes.windll.user32.keybd_event") as mock_keybd:
        TextInjector._simulate_paste()

    assert [(c[0][0], c[0][2]) for c in mock_keybd.call_args_list] == [(0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2)]


def test_hotkey_sends_menu_mask_on_right_alt_press():
    """
    Pressing the Right Alt hotkey taps the menu-mask key while Alt is still down, so releasing it
    is not a lone Alt tap (which would focus the menu bar in Chrome, Slack, Office on non-AltGr layouts).
    """
    from unittest.mock import patch
    from src.ui.hotkey import GlobalHotkeyListener, VK_MENU_MASK

    listener = GlobalHotkeyListener(hotkey="right_alt")
    fired = []
    listener.hotkey_triggered.connect(lambda: fired.append(True))
    states = iter([0x8000, 0x8000, 0])

    def key_state(vk):
        try:
            return next(states)
        except StopIteration:
            listener._is_running = False
            return 0

    with patch("ctypes.windll.user32.GetAsyncKeyState", side_effect=key_state), \
         patch("ctypes.windll.user32.keybd_event") as mock_keybd, \
         patch("src.ui.hotkey.time.sleep"):
        listener._is_running = True
        listener._run_async_key_loop()

    assert fired == [True]
    assert [(c[0][0], c[0][2]) for c in mock_keybd.call_args_list] == [(VK_MENU_MASK, 0), (VK_MENU_MASK, 2)]


def test_hotkey_does_not_mask_non_alt_hotkeys():
    from unittest.mock import patch
    from src.ui.hotkey import GlobalHotkeyListener

    listener = GlobalHotkeyListener(hotkey="f9")
    states = iter([0x8000, 0])

    def key_state(vk):
        try:
            return next(states)
        except StopIteration:
            listener._is_running = False
            return 0

    with patch("ctypes.windll.user32.GetAsyncKeyState", side_effect=key_state), \
         patch("ctypes.windll.user32.keybd_event") as mock_keybd, \
         patch("src.ui.hotkey.time.sleep"):
        listener._is_running = True
        listener._run_async_key_loop()

    mock_keybd.assert_not_called()


def test_process_dictation_saves_result_to_local_history(isolate_dictation_history):
    from unittest.mock import MagicMock
    from src.ai.transcriber import TranscriberService
    from src.audio.mixer import AudioMixer
    import numpy as np

    service = TranscriberService(api_key="fake-key", config_dict={"DICTATION_MODEL": "gemini-3.8-flash"})
    service.client = MagicMock()
    service.client.models.generate_content.return_value = MagicMock(text="Ship it on Thursday.")
    wav_bytes = AudioMixer.convert_to_wav_bytes(np.full(32000, 0.2, dtype=np.float32), sample_rate=16000)

    assert service.process_dictation(wav_bytes) == "Ship it on Thursday."

    files = list(isolate_dictation_history.glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert content.startswith("# Buddy Dictations - ")
    assert "Ship it on Thursday." in content
    assert "gemini-3.8-flash" in content and "2.0s audio" in content


def test_process_dictation_saves_nothing_when_no_speech(isolate_dictation_history):
    from unittest.mock import MagicMock, patch
    from src.ai.transcriber import TranscriberService
    from src.audio.mixer import AudioMixer
    import numpy as np

    service = TranscriberService(api_key="fake-key")
    service.client = MagicMock()
    service.client.models.generate_content.return_value = MagicMock(text="")
    wav_bytes = AudioMixer.convert_to_wav_bytes(np.zeros(16000, dtype=np.float32), sample_rate=16000)

    with patch.object(service, "transcribe_dictation", return_value=""):
        assert service.process_dictation(wav_bytes) == ""
    assert not isolate_dictation_history.exists() or not list(isolate_dictation_history.glob("*.md"))


def test_microphone_keeps_recording_for_dictation_while_listening_is_paused():
    """
    Pausing background listening must not silently break dictation: the mic thread keeps
    reading while a dictation is in progress.
    """
    from unittest.mock import MagicMock, patch
    import numpy as np
    from src.audio.stream_handler import AudioStreamHandler

    handler = AudioStreamHandler(config_dict={"SAVE_AUDIO_RECORDINGS": False})
    handler._is_running = True
    handler._is_paused = True
    handler.start_dictation()
    reads = []

    class Recorder:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def record(self, numframes):
            reads.append(numframes)
            if len(reads) >= 3:
                handler._is_running = False
            return np.full((numframes, 1), 0.1, dtype=np.float32)

    mic = MagicMock(id="mic")
    mic.recorder.return_value = Recorder()
    fake_sc = MagicMock()
    fake_sc.default_microphone.return_value = mic
    with patch("src.audio.stream_handler.sc", fake_sc):
        handler._record_microphone()

    assert len(reads) == 3
    assert handler.mic_queue.qsize() == 3

def test_process_dictation_single_pass_success():
    """
    Verifies process_dictation executes single-pass prompt and parses response.
    """
    from unittest.mock import MagicMock
    from src.ai.transcriber import TranscriberService
    from src.audio.mixer import AudioMixer
    import numpy as np

    service = TranscriberService(api_key="fake-key", config_dict={"DICTATION_MODEL": "gemini-3.5-flash-lite"})
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "Hello, this is fast single pass dictation."
    mock_client.models.generate_content.return_value = mock_resp
    service.client = mock_client

    t = np.linspace(0, 1.0, 16000, endpoint=False)
    tone = (np.sin(2 * np.pi * 440.0 * t) * 0.5).astype(np.float32)
    wav_bytes = AudioMixer.convert_to_wav_bytes(tone, sample_rate=16000)

    result = service.process_dictation(wav_bytes)
    assert result == "Hello, this is fast single pass dictation."
    assert mock_client.models.generate_content.call_count == 1
    call_args = mock_client.models.generate_content.call_args[1]
    assert call_args["model"] == "gemini-3.5-flash-lite"

def test_process_dictation_fallback_to_two_pass():
    """
    Verifies that if single-pass fails, process_dictation falls back to transcribe + optimize.
    """
    from unittest.mock import MagicMock, patch
    from src.ai.transcriber import TranscriberService
    from src.audio.mixer import AudioMixer
    import numpy as np

    service = TranscriberService(api_key="fake-key")
    mock_client = MagicMock()
    # First call (single-pass) raises exception
    mock_client.models.generate_content.side_effect = Exception("Single pass error")
    service.client = mock_client

    t = np.linspace(0, 1.0, 16000, endpoint=False)
    tone = (np.sin(2 * np.pi * 440.0 * t) * 0.5).astype(np.float32)
    wav_bytes = AudioMixer.convert_to_wav_bytes(tone, sample_rate=16000)

    with patch.object(service, "transcribe_dictation", return_value="raw speech") as mock_transcribe, \
         patch.object(service, "optimize_dictation", return_value="Optimized speech.") as mock_opt:
        result = service.process_dictation(wav_bytes)
        assert result == "Optimized speech."
        mock_transcribe.assert_called_once_with(wav_bytes)
        mock_opt.assert_called_once_with("raw speech")

def test_text_injector_win32_clipboard_synchronous():
    """
    Verifies that _set_clipboard_win32 sets the native OS clipboard.
    """
    import sys
    from src.ui.text_injector import TextInjector
    if sys.platform == "win32":
        test_phrase = "Buddy Win32 Clipboard Verification!"
        success = TextInjector._set_clipboard_win32(test_phrase)
        assert success is True

        # Read back via Qt clipboard
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QGuiApplication
        app = QApplication.instance() or QApplication(sys.argv)
        assert QGuiApplication.clipboard().text() == test_phrase



def test_process_dictation_uses_recommended_model_by_default():
    from unittest.mock import MagicMock
    from src.ai.transcriber import TranscriberService
    from src.audio.mixer import AudioMixer
    import numpy as np

    service = TranscriberService(api_key="fake-key", config_dict={})
    service.client = MagicMock()
    service.client.models.generate_content.return_value = MagicMock(text="Done.")
    service.process_dictation(AudioMixer.convert_to_wav_bytes(np.full(16000, 0.2, dtype=np.float32), sample_rate=16000))

    kwargs = service.client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "gemini-3.1-flash-lite"
    assert kwargs["config"] is None


def test_process_dictation_passes_configured_thinking_level():
    from unittest.mock import MagicMock
    from src.ai.transcriber import TranscriberService
    from src.audio.mixer import AudioMixer
    import numpy as np

    service = TranscriberService(api_key="fake-key", config_dict={"DICTATION_MODEL": "gemini-3.5-flash", "DICTATION_THINKING_LEVEL": "minimal"})
    service.client = MagicMock()
    service.client.models.generate_content.return_value = MagicMock(text="Done.")
    service.process_dictation(AudioMixer.convert_to_wav_bytes(np.full(16000, 0.2, dtype=np.float32), sample_rate=16000))

    kwargs = service.client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "gemini-3.5-flash"
    assert kwargs["config"].thinking_config.thinking_level.value.lower() == "minimal"


def test_silent_dictation_warns_without_calling_gemini():
    """A muted mic (digital silence) gets an immediate, specific warning instead of a slow empty API round trip."""
    from unittest.mock import MagicMock, patch
    import numpy as np
    from src.ui.tray_icon import TrayIconController
    from src.audio.mixer import AudioMixer

    audio = MagicMock(_is_dictating=True, _is_paused=False, current_mic_name="Microphone Array")
    audio.stop_dictation.return_value = AudioMixer.convert_to_wav_bytes(np.zeros(32000, dtype=np.float32), sample_rate=16000)
    controller = TrayIconController(audio_handler=audio, transcriber_service=MagicMock(), updater=MagicMock(), config_dict={})
    with patch.object(controller.executor, "submit") as submit, \
         patch.object(controller.tray, "showMessage") as toast:
        controller.on_dictation_hotkey()
        controller._on_dictation_completed("")

    submit.assert_not_called()
    assert toast.call_count == 1
    assert "Microphone Array recorded only silence" in toast.call_args[0][1]
