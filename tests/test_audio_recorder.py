import os
from datetime import datetime
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from src.audio.recorder import AudioRecorder

@pytest.fixture
def temp_recordings_dir(tmp_path):
    rec_dir = tmp_path / "recordings"
    rec_dir.mkdir(parents=True, exist_ok=True)
    return rec_dir

def test_feed_and_flush_creates_daily_subfolder_and_mp3(temp_recordings_dir):
    sr = 16000
    recorder = AudioRecorder(
        output_dir=temp_recordings_dir,
        chunk_duration_sec=600,
        sample_rate=sr,
        audio_format="mp3",
        save_silent_chunks=False,
        min_flush_sec=1.0
    )

    # Generate 2 seconds of stereo audio
    samples = np.random.randn(sr * 2, 2).astype(np.float32) * 0.1
    saved_file = recorder.feed_chunk(samples, speech_present=True)
    assert saved_file is None  # Not yet reached 600s

    # Flush on stop/pause
    saved_path = recorder.flush()
    assert saved_path is not None
    assert Path(saved_path).exists()

    # Verify directory structure: recordings/YYYY-MM-DD/recording_YYYY-MM-DD_HH-MM-SS.mp3
    date_str = datetime.now().strftime("%Y-%m-%d")
    assert date_str in saved_path
    assert saved_path.endswith(".mp3")
    assert "recording_" in saved_path

    # Verify audio file properties
    info = sf.info(saved_path)
    assert info.samplerate == sr
    assert info.channels == 2
    assert info.format == "MP3"
    assert info.duration >= 1.9

def test_smart_filtering_discards_silent_chunk_by_default(temp_recordings_dir):
    sr = 16000
    recorder = AudioRecorder(
        output_dir=temp_recordings_dir,
        chunk_duration_sec=600,
        sample_rate=sr,
        audio_format="mp3",
        save_silent_chunks=False,
        min_flush_sec=1.0
    )

    # 2 seconds of audio without speech activity
    samples = np.zeros((sr * 2, 2), dtype=np.float32)
    recorder.feed_chunk(samples, speech_present=False)
    saved_path = recorder.flush()

    assert saved_path is None
    # No files should have been created in output_dir
    files = list(temp_recordings_dir.rglob("*.mp3"))
    assert len(files) == 0

def test_save_silent_chunks_enabled(temp_recordings_dir):
    sr = 16000
    recorder = AudioRecorder(
        output_dir=temp_recordings_dir,
        chunk_duration_sec=600,
        sample_rate=sr,
        audio_format="mp3",
        save_silent_chunks=True,
        min_flush_sec=1.0
    )

    # 2 seconds of silent audio with save_silent_chunks=True
    samples = np.zeros((sr * 2, 2), dtype=np.float32)
    recorder.feed_chunk(samples, speech_present=False)
    saved_path = recorder.flush()

    assert saved_path is not None
    assert Path(saved_path).exists()
    assert sf.info(saved_path).channels == 2

def test_chunk_rotation_at_target_duration(temp_recordings_dir):
    sr = 16000
    # 2-second target duration
    recorder = AudioRecorder(
        output_dir=temp_recordings_dir,
        chunk_duration_sec=2,
        sample_rate=sr,
        audio_format="mp3",
        save_silent_chunks=True,
        min_flush_sec=0.5
    )

    # Feed 1 second (16000 samples)
    s1 = np.random.randn(sr * 1, 2).astype(np.float32) * 0.05
    res1 = recorder.feed_chunk(s1, speech_present=True)
    assert res1 is None

    # Feed 1.5 seconds (24000 samples) -> triggers rotation (total 40000 >= 32000)
    s2 = np.random.randn(int(sr * 1.5), 2).astype(np.float32) * 0.05
    res2 = recorder.feed_chunk(s2, speech_present=True)
    assert res2 is not None
    assert Path(res2).exists()

    # The first chunk should be exactly 2.0 seconds
    info = sf.info(res2)
    assert abs(info.duration - 2.0) < 0.1

    # Remaining 0.5 seconds (8000 samples) should remain in buffer for next chunk
    assert recorder._total_samples == int(sr * 0.5)

    # Flushing should now save the leftover chunk
    res3 = recorder.flush()
    assert res3 is not None
    assert Path(res3).exists()
    info3 = sf.info(res3)
    assert abs(info3.duration - 0.5) < 0.1

def test_min_flush_sec_discards_tiny_fragments(temp_recordings_dir):
    sr = 16000
    recorder = AudioRecorder(
        output_dir=temp_recordings_dir,
        chunk_duration_sec=600,
        sample_rate=sr,
        min_flush_sec=2.0
    )

    # 0.5 seconds (< 2.0s min_flush_sec)
    samples = np.random.randn(int(sr * 0.5), 2).astype(np.float32) * 0.1
    recorder.feed_chunk(samples, speech_present=True)
    saved_path = recorder.flush()

    assert saved_path is None
    assert len(list(temp_recordings_dir.rglob("*.mp3"))) == 0

def test_get_current_recording_filename(temp_recordings_dir):
    recorder = AudioRecorder(
        output_dir=temp_recordings_dir,
        chunk_duration_sec=600,
        audio_format="mp3"
    )

    assert recorder.get_current_recording_filename() is None

    samples = np.random.randn(16000, 2).astype(np.float32) * 0.1
    recorder.feed_chunk(samples, speech_present=True)

    filename = recorder.get_current_recording_filename()
    assert filename is not None
    assert filename.startswith("recording_")
    assert filename.endswith(".mp3")

    recorder.flush()
    assert recorder.get_current_recording_filename() is None

def test_wav_format_support(temp_recordings_dir):
    sr = 16000
    recorder = AudioRecorder(
        output_dir=temp_recordings_dir,
        chunk_duration_sec=600,
        sample_rate=sr,
        audio_format="wav",
        min_flush_sec=1.0
    )

    samples = np.random.randn(sr * 2, 2).astype(np.float32) * 0.1
    recorder.feed_chunk(samples, speech_present=True)
    saved_path = recorder.flush()

    assert saved_path is not None
    assert saved_path.endswith(".wav")
    info = sf.info(saved_path)
    assert info.format == "WAV"
    assert info.subtype == "PCM_16"
    assert info.channels == 2

def test_disabled_recorder(temp_recordings_dir):
    recorder = AudioRecorder(
        output_dir=temp_recordings_dir,
        enabled=False
    )

    samples = np.random.randn(16000 * 2, 2).astype(np.float32) * 0.1
    assert recorder.feed_chunk(samples, speech_present=True) is None
    assert recorder.flush() is None
    assert recorder.get_current_recording_filename() is None
