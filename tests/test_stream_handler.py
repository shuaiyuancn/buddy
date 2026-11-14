import time
import itertools
import logging
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from src.audio.stream_handler import (
    AudioStreamHandler, _install_backlog_guard, ZERO_FILL_CAP_SEC, MIC_SAMPLE_RATE, SPEAKER_SAMPLE_RATE,
    MIC_BLOCK_SEC, SPEAKER_BLOCK_SEC, QUEUE_MAX_SEC, MAX_STEP_SEC, CAPTURE_BUFFER_SEC,
)

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

    def recorder(self, samplerate, channels=None, blocksize=None):
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


def test_stream_handler_recorder_integration():
    handler = AudioStreamHandler()
    assert hasattr(handler, "recorder")
    assert handler.recorder is not None

    handler.recorder = MagicMock()
    handler.recorder.get_current_recording_filename.return_value = "recording_test.mp3"

    assert handler.get_current_recording_filename() == "recording_test.mp3"

    handler.pause()
    handler.recorder.flush.assert_called_once()

    handler.recorder.flush.reset_mock()
    with patch.object(handler, "wait"):
        handler.stop()
        handler.recorder.flush.assert_called_once()


class _ChunkRecorder:
    """Stands in for soundcard's _Recorder: only the private _record_chunk the guard wraps."""
    def __init__(self, chunk):
        self.chunk = chunk

    def _record_chunk(self):
        return self.chunk


def test_backlog_guard_truncates_standby_zero_fill_and_reports_the_drop():
    # What soundcard returns after 10 minutes frozen in its idle wait: one zero array for the whole gap
    rec = _ChunkRecorder(np.zeros(MIC_SAMPLE_RATE * 600, dtype=np.float32))
    guard = _install_backlog_guard(rec, MIC_SAMPLE_RATE, 1, "Microphone")

    out = rec._record_chunk()

    cap = int(MIC_SAMPLE_RATE * ZERO_FILL_CAP_SEC)
    assert len(out) == cap
    assert out.base is None  # a fresh copy, not a view pinning the giant array
    assert guard.take_dropped_sec() == pytest.approx(600 - ZERO_FILL_CAP_SEC)
    assert guard.take_dropped_sec() == 0


def test_backlog_guard_passes_normal_chunks_through_unchanged():
    chunk = np.ones(int(SPEAKER_SAMPLE_RATE * 0.5) * 2, dtype=np.float32)  # 0.5 s of stereo
    rec = _ChunkRecorder(chunk)
    guard = _install_backlog_guard(rec, SPEAKER_SAMPLE_RATE, 2, "Speaker")

    assert rec._record_chunk() is chunk
    assert guard.take_dropped_sec() == 0


def test_backlog_guard_on_recorder_without_record_chunk_does_not_raise(caplog):
    class _Bare:
        pass

    with caplog.at_level(logging.INFO, logger="buddy.audio"):
        assert _install_backlog_guard(_Bare(), MIC_SAMPLE_RATE, 1, "Microphone") is None
    assert "guard not installed" in caplog.text


class _StandbyMic:
    """Fake microphone whose recorder behaves like soundcard's: record() reads via _record_chunk()."""
    id = "mic"
    name = "Fake mic"

    def __init__(self, handler, first_record):
        self.handler = handler
        self.first_record = first_record
        self.blocksizes = []
        self.opens = 0

    def recorder(self, samplerate, channels=None, blocksize=None):
        device = self
        device.blocksizes.append(blocksize)

        class _Recorder:
            def __enter__(self):
                device.opens += 1
                if device.opens >= 2:
                    device.handler._is_running = False
                return self

            def __exit__(self, *exc):
                return False

            def _record_chunk(self):
                return np.zeros(MIC_SAMPLE_RATE * 600, dtype=np.float32)

            def record(self, numframes):
                return device.first_record(self, numframes)

        return _Recorder()


def _run_mic_until_reopen(first_record, clock=None):
    handler = AudioStreamHandler(config_dict={"SAVE_AUDIO_RECORDINGS": False})
    handler._is_running = True
    warnings_seen = []
    handler.warning_logged.connect(warnings_seen.append)
    mic = _StandbyMic(handler, first_record)
    fake_sc = MagicMock()
    fake_sc.default_microphone.return_value = mic
    fake_time = MagicMock(wraps=time)
    if clock is not None:
        fake_time.monotonic.side_effect = clock
    with patch("src.audio.stream_handler.sc", fake_sc), patch("src.audio.stream_handler.time", fake_time):
        handler._record_microphone()
    return handler, mic, warnings_seen


def test_mic_capture_discards_standby_backlog_and_reopens():
    handler, mic, warnings_seen = _run_mic_until_reopen(
        lambda rec, numframes: rec._record_chunk()[:numframes].reshape(-1, 1)
    )

    assert mic.opens == 2
    assert handler.mic_queue.empty()  # the block read after the standby was discarded
    assert warnings_seen == []
    assert mic.blocksizes == [int(MIC_SAMPLE_RATE * CAPTURE_BUFFER_SEC)] * 2


def test_mic_capture_discards_a_stalled_read_and_reopens():
    ticks = itertools.count(start=0, step=10)  # every read appears to take 10 s
    handler, mic, _ = _run_mic_until_reopen(
        lambda rec, numframes: np.zeros((numframes, 1), dtype=np.float32),
        clock=lambda: float(next(ticks)),
    )

    assert mic.opens == 2
    assert handler.mic_queue.empty()


def test_mic_capture_reopens_after_memory_error():
    def out_of_memory(rec, numframes):
        raise MemoryError()

    handler, mic, warnings_seen = _run_mic_until_reopen(out_of_memory)

    assert mic.opens == 2
    assert warnings_seen == []  # took the reopen path, not the error/backoff path


def test_capture_queues_are_bounded_and_keep_the_newest_blocks(caplog):
    handler = AudioStreamHandler(config_dict={"SAVE_AUDIO_RECORDINGS": False})
    assert handler.mic_queue.maxsize == round(QUEUE_MAX_SEC / MIC_BLOCK_SEC)
    maxsize = handler.speaker_queue.maxsize
    assert maxsize == round(QUEUE_MAX_SEC / SPEAKER_BLOCK_SEC)

    with caplog.at_level(logging.WARNING, logger="buddy.audio"):
        for i in range(maxsize + 5):
            handler._put_latest(handler.speaker_queue, np.full(4, i, dtype=np.float32))

    assert handler.speaker_queue.qsize() == maxsize
    kept = [handler.speaker_queue.get_nowait()[0] for _ in range(maxsize)]
    assert kept == list(range(5, maxsize + 5))
    # Five drops, but at most one log line per minute
    assert sum("queue full" in r.getMessage() for r in caplog.records) == 1


def test_orchestrator_step_keeps_only_the_most_recent_seconds():
    handler = AudioStreamHandler(config_dict={"SAVE_AUDIO_RECORDINGS": False})
    for i in range(20):  # 20 s of 1-second speaker blocks, e.g. after a stall
        handler.speaker_queue.put(np.full(SPEAKER_SAMPLE_RATE, i, dtype=np.float32))

    data = handler._drain_step_audio(handler.speaker_queue, SPEAKER_SAMPLE_RATE, "Speaker")

    assert len(data) == int(SPEAKER_SAMPLE_RATE * MAX_STEP_SEC)
    assert data[0] == 15 and data[-1] == 19
    assert handler.speaker_queue.empty()

    # A normal step is passed through whole
    for _ in range(10):
        handler.mic_queue.put(np.zeros(int(MIC_SAMPLE_RATE * MIC_BLOCK_SEC), dtype=np.float32))
    assert len(handler._drain_step_audio(handler.mic_queue, MIC_SAMPLE_RATE, "Microphone")) == MIC_SAMPLE_RATE


def test_mixed_buffer_stays_bounded_after_large_input():
    handler = AudioStreamHandler(window_duration_sec=2, overlap_duration_sec=1, config_dict={"SAVE_AUDIO_RECORDINGS": False})
    emitted = []
    handler.chunk_ready.connect(emitted.append)
    handler.mixed_buffer = [np.full((16000 * 20, 2), 0.2, dtype=np.float32)]  # ten windows' worth

    with patch.object(handler.vad, "is_speech_present", return_value=True):
        handler._emit_ready_windows()

    assert sum(len(c) for c in handler.mixed_buffer) < handler.total_target_samples
    assert all(c.base is None for c in handler.mixed_buffer)
    # 32000-sample windows advancing 16000 samples each through 320000 samples
    assert len(emitted) == 19

