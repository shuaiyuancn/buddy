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
    
    # Generate active and paused icons
    active_icon = controller._draw_tray_icon(is_active=True)
    paused_icon = controller._draw_tray_icon(is_active=False)
    
    # Assert QIcons are correctly generated and valid
    assert isinstance(active_icon, QIcon)
    assert not active_icon.isNull()
    
    assert isinstance(paused_icon, QIcon)
    assert not paused_icon.isNull()

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
