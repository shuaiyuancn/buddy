import sys
from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from src.ui.tray_icon import TrayIconController

@pytest.fixture(scope="module")
def qt_app():
    # Setup single QApplication instance for Qt-level tests
    app = QApplication.instance() or QApplication(sys.argv)
    yield app

def test_draw_tray_icon(qt_app):
    # Setup mocks
    mock_audio = MagicMock()
    mock_transcriber = MagicMock()
    
    controller = TrayIconController(mock_audio, mock_transcriber)
    
    # Generate all state icons
    states = ["sleeping", "active", "paused", True, False]
    for state in states:
        icon = controller._draw_tray_icon(state)
        assert isinstance(icon, QIcon)
        assert not icon.isNull()

def test_set_status_and_speech_activity_changed(qt_app):
    mock_audio = MagicMock()
    mock_audio._is_paused = False
    mock_audio._is_speech_active = False
    mock_transcriber = MagicMock()
    
    controller = TrayIconController(mock_audio, mock_transcriber)
    assert controller._current_state == "sleeping"
    assert "Sleeping" in controller.tray.toolTip()
    
    # Simulate speech activity detected
    controller._on_speech_activity_changed(True)
    assert controller._current_state == "active"
    assert "Recording & Transcribing" in controller.tray.toolTip()
    
    # Simulate speech ending (falling back to sleep)
    controller._on_speech_activity_changed(False)
    assert controller._current_state == "sleeping"
    assert "Sleeping" in controller.tray.toolTip()
    
    # Set paused state
    controller.set_status("paused")
    assert controller._current_state == "paused"
    assert "Paused" in controller.tray.toolTip()


def test_on_toggle_listening(qt_app):
    mock_audio = MagicMock()
    mock_transcriber = MagicMock()
    
    # Set initially unpaused state
    mock_audio._is_paused = False
    
    controller = TrayIconController(mock_audio, mock_transcriber)
    
    # Act: Trigger toggle
    controller.on_toggle_listening()
    
    # Assert: Should pause the handler and modify context text
    mock_audio.pause.assert_called_once()
    assert controller.toggle_action.text() == "Resume Listening"
    
    # Reset mock and mock paused state
    mock_audio.reset_mock()
    mock_audio._is_paused = True
    
    # Act: Trigger toggle again
    controller.on_toggle_listening()
    
    # Assert: Should resume the handler and update text
    mock_audio.resume.assert_called_once()
    assert controller.toggle_action.text() == "Pause Listening"

def test_pause_until_8am_schedules_timer_and_auto_resumes(qt_app):
    mock_audio = MagicMock()
    mock_audio._is_paused = False
    mock_audio._is_speech_active = False
    mock_audio.pause.side_effect = lambda: setattr(mock_audio, "_is_paused", True)
    mock_audio.resume.side_effect = lambda: setattr(mock_audio, "_is_paused", False)
    mock_transcriber = MagicMock()
    
    controller = TrayIconController(mock_audio, mock_transcriber)
    
    # Act: Trigger pause until 8am
    controller.on_pause_until_8am()
    
    # Assert: audio handler is paused, timer is started, status updated
    mock_audio.pause.assert_called_once()
    assert controller._auto_resume_timer.isActive()
    assert controller._current_state == "paused"
    assert "Resumes tomorrow at 8:00 AM" in controller.tray.toolTip()
    assert controller.toggle_action.text() == "Resume Listening"

    # Simulate timer fire
    controller._on_auto_resume_timer_fired()
    
    mock_audio.resume.assert_called_once()
    assert controller._current_state == "sleeping"
    assert controller.toggle_action.text() == "Pause Listening"

def test_on_toggle_cancels_auto_resume_timer(qt_app):
    mock_audio = MagicMock()
    mock_audio._is_paused = False
    mock_transcriber = MagicMock()
    
    controller = TrayIconController(mock_audio, mock_transcriber)
    controller.on_pause_until_8am()
    assert controller._auto_resume_timer.isActive()
    
    # Manually resuming should cancel auto-resume timer
    mock_audio._is_paused = True
    controller.on_toggle_listening()
    assert not controller._auto_resume_timer.isActive()
    mock_audio.resume.assert_called_once()

def test_on_audio_chunk_ready_submits_to_executor(qt_app):
    mock_audio = MagicMock()
    mock_transcriber = MagicMock()
    
    controller = TrayIconController(mock_audio, mock_transcriber)
    controller.executor = MagicMock()
    dummy_wav = b"RIFFaudio..."
    
    # Act: Trigger audio chunk ready callback
    controller.on_audio_chunk_ready(dummy_wav)
    
    # Assert: Submits task to bounded thread pool
    controller.executor.submit.assert_called_once()
    args, _ = controller.executor.submit.call_args
    assert args[0] == controller._safe_transcribe
    assert args[1] == dummy_wav

def test_safe_transcribe_handles_errors(qt_app):
    mock_audio = MagicMock()
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe_chunk.side_effect = Exception("API connection timeout")

    controller = TrayIconController(mock_audio, mock_transcriber)
    controller._safe_transcribe(b"dummy")

    # Warning signal should be emitted
    mock_audio.warning_logged.emit.assert_called_once()
    assert "API connection timeout" in mock_audio.warning_logged.emit.call_args[0][0]

def test_on_exit_shuts_down_cleanly(qt_app):
    mock_audio = MagicMock()
    mock_transcriber = MagicMock()

    controller = TrayIconController(mock_audio, mock_transcriber)
    controller.executor = MagicMock()

    with patch("sys.exit") as mock_exit:
        controller.on_exit()

        mock_audio.stop.assert_called_once()
        controller.executor.shutdown.assert_called_once_with(wait=True, cancel_futures=False)
        mock_exit.assert_called_once_with(0)
