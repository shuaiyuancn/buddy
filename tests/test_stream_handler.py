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

def test_stream_handler_speech_activity_tracking():
    handler = AudioStreamHandler()
    assert handler._is_speech_active is False
    assert handler._silence_hangover_sec == 3
    assert hasattr(handler, "speech_activity_changed")



class _FakeDevice:
    def __init__(self, device_id, on_open):
        self.id = device_id
        self.name = f"Fake {device_id}"
        self._on_open = on_open

    def recorder(self, samplerate, channels=None):
        device = self

        class _Recorder:
            def __enter__(self):
                device._on_open(device)
                return self

            def __exit__(self, *exc):
                return False

            def record(self, numframes):
                return np.zeros((numframes, 1), dtype=np.float32)

        return _Recorder()


def _run_until_second_open(handler, opened):
    handler._is_running = True
    handler.device_check_interval_sec = 0.0

    def on_open(device):
        opened.append(device.id)
        if len(opened) >= 2:
            handler._is_running = False

    return on_open


def test_microphone_capture_follows_default_device_change():
    handler = AudioStreamHandler()
    opened = []
    fake_sc = MagicMock()
    on_open = _run_until_second_open(handler, opened)
    laptop_mic = _FakeDevice("laptop-mic", on_open)
    headset_mic = _FakeDevice("headset-mic", on_open)
    # Default is the laptop mic at startup, then the headset is plugged in
    defaults = iter([laptop_mic, laptop_mic, headset_mic])
    current = {"device": None}

    def default_microphone():
        current["device"] = next(defaults, current["device"])
        return current["device"]

    fake_sc.default_microphone.side_effect = default_microphone

    with patch("src.audio.stream_handler.sc", fake_sc):
        handler._record_microphone()

    assert opened == ["laptop-mic", "headset-mic"]
    assert not handler.mic_queue.empty()


def test_speaker_loopback_follows_default_device_change_and_matches_by_id():
    handler = AudioStreamHandler()
    opened = []
    fake_sc = MagicMock()
    on_open = _run_until_second_open(handler, opened)
    speakers = MagicMock(id="speakers-endpoint")
    speakers.name = "Speakers (Realtek(R) Audio)"
    headphones = MagicMock(id="headphones-endpoint")
    headphones.name = "Realtek HD Audio 2nd output (Realtek(R) Audio)"
    defaults = iter([speakers, speakers, headphones])
    current = {"device": None}

    def default_speaker():
        current["device"] = next(defaults, current["device"])
        return current["device"]

    fake_sc.default_speaker.side_effect = default_speaker
    fake_sc.get_microphone.side_effect = lambda id, include_loopback: _FakeDevice(id, on_open)

    with patch("src.audio.stream_handler.sc", fake_sc):
        handler._record_speaker_loopback()

    assert opened == ["speakers-endpoint", "headphones-endpoint"]
    for call in fake_sc.get_microphone.call_args_list:
        assert call.kwargs["include_loopback"] is True
    assert [c.kwargs["id"] for c in fake_sc.get_microphone.call_args_list] == ["speakers-endpoint", "headphones-endpoint"]


def test_default_device_lookup_failure_counts_as_change():
    handler = AudioStreamHandler()

    def broken_default():
        raise RuntimeError("endpoint removed")

    assert handler._default_device_changed(broken_default, "any-id") is True
    assert handler._default_device_changed(lambda: MagicMock(id="same"), "same") is False
