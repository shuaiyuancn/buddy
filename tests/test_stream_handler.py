import time
import numpy as np
from unittest.mock import MagicMock, patch
from src.audio.stream_handler import AudioStreamHandler

def test_stream_handler_init():
    handler = AudioStreamHandler(target_sr=16000, window_duration_sec=30, overlap_duration_sec=5, energy_threshold_db=-50.0)
    assert handler.target_sr == 16000
    assert handler.window_duration_sec == 30
    assert handler.overlap_duration_sec == 5
    assert handler.total_target_samples == 480000
    assert handler.overlap_samples == 80000
    assert handler.vad.energy_threshold_db == -50.0
    assert handler._is_running is False
    assert handler._is_paused is False

def test_stream_handler_pause_and_resume():
    handler = AudioStreamHandler(target_sr=16000, window_duration_sec=10)
    
    # 1. Test pause
    handler.pause()
    assert handler._is_paused is True

    # 2. Add stagnant elements to queues while paused
    handler.mic_queue.put(np.zeros(16000, dtype=np.float32))
    handler.speaker_queue.put(np.zeros(48000, dtype=np.float32))
    assert not handler.mic_queue.empty()
    assert not handler.speaker_queue.empty()

    # 3. Test resume drains queues
    handler.resume()
    assert handler._is_paused is False
    assert handler.mic_queue.empty()
    assert handler.speaker_queue.empty()

def test_stream_handler_stop_joins_threads():
    handler = AudioStreamHandler()
    handler._is_running = True
    
    mock_mic_thread = MagicMock()
    mock_mic_thread.is_alive.return_value = True
    mock_spk_thread = MagicMock()
    mock_spk_thread.is_alive.return_value = True

    handler.mic_thread = mock_mic_thread
    handler.speaker_thread = mock_spk_thread

    with patch.object(handler, "wait") as mock_wait:
        handler.stop()
        assert handler._is_running is False
        mock_wait.assert_called_once()
        mock_mic_thread.join.assert_called_once_with(timeout=1.0)
        mock_spk_thread.join.assert_called_once_with(timeout=1.0)
