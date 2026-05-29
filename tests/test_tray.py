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

@patch("threading.Thread")
def test_on_audio_chunk_ready_dispatches_thread(mock_thread_class, qt_app):
    mock_audio = MagicMock()
    mock_transcriber = MagicMock()
    
    controller = TrayIconController(mock_audio, mock_transcriber)
    dummy_wav = b"RIFFaudio..."
    
    # Act: Trigger audio chunk ready callback
    controller.on_audio_chunk_ready(dummy_wav)
    
    # Assert: Spawns daemon worker thread for background transcription to keep UI thread unblocked
    mock_thread_class.assert_called_once()
    args, kwargs = mock_thread_class.call_args
    assert kwargs.get("daemon") is True
    assert kwargs.get("target") == mock_transcriber.transcribe_chunk
    assert kwargs.get("args") == (dummy_wav,)
    
    # Thread must be started
    mock_thread_class.return_value.start.assert_called_once()
