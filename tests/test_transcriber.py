import os
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np
import pytest
from src.ai.transcriber import FileAppender, TranscriberService

@pytest.fixture
def temp_transcript_dir():
    # Setup temporary directory for testing isolated File I/O
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)

def test_file_appender_creates_headers(temp_transcript_dir):
    appender = FileAppender(temp_transcript_dir)
    date_str = datetime.now().strftime("%Y-%m-%d")
    expected_file = temp_transcript_dir / f"{date_str}_raw.md"

    # Append first block
    appender.append_transcription("First transcription line.")

    assert expected_file.exists()
    content = expected_file.read_text(encoding="utf-8")
    
    # Header should be auto-created
    assert f"# Buddy Raw Transcript Log - {date_str}" in content
    # Text block should contain timestamp header and cleaned text
    assert "First transcription line." in content

def test_file_appender_thread_safety(temp_transcript_dir):
    appender = FileAppender(temp_transcript_dir)
    date_str = datetime.now().strftime("%Y-%m-%d")
    expected_file = temp_transcript_dir / f"{date_str}_raw.md"

    num_threads = 10
    loops_per_thread = 10

    def worker(thread_idx):
        for i in range(loops_per_thread):
            appender.append_transcription(f"Thread-{thread_idx} loop-{i}")

    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Read the file and assert count of appends matches expected count
    content = expected_file.read_text(encoding="utf-8")
    for i in range(num_threads):
        for j in range(loops_per_thread):
            assert f"Thread-{i} loop-{j}" in content

def test_transcribe_chunk_gemini_interaction(temp_transcript_dir):
    service = TranscriberService(api_key="mock-api-key")
    service.appender = FileAppender(temp_transcript_dir)

    # Mock google.genai Client
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Hello, this is a simulated transcription."
    mock_response.candidates = []
    mock_client.models.generate_content.return_value = mock_response
    service.client = mock_client

    # Audio with energy/speech so VAD lets it pass
    t = np.linspace(0, 1.0, 16000, endpoint=False)
    tone = (np.sin(2 * np.pi * 440.0 * t) * 0.5).astype(np.float32)
    from src.audio.mixer import AudioMixer
    dummy_wav = AudioMixer.convert_to_wav_bytes(tone, sample_rate=16000)

    result = service.transcribe_chunk(dummy_wav)

    # Verify Gemini is called with the expected model and diarization config
    mock_client.models.generate_content.assert_called_once()
    call_kwargs = mock_client.models.generate_content.call_args[1]
    assert call_kwargs["model"] == "gemini-3.5-transcribe"
    assert call_kwargs["config"].audio_transcription_config.diarization is True

    # Verify results are correctly logged to our appender
    assert "Hello, this is a simulated transcription." in result
    raw_log = service.appender.read_raw_log()
    assert "Hello, this is a simulated transcription." in raw_log

def test_transcribe_chunk_gemini_turn_by_turn_diarization(temp_transcript_dir):
    service = TranscriberService(api_key="mock-api-key")
    service.appender = FileAppender(temp_transcript_dir)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = None

    # Part 1: Me (0.0s - 1.8s)
    mock_part1 = MagicMock()
    mock_part1.text = None
    mock_part1.audio_transcription.speaker_label = "spk:0"
    mock_part1.audio_transcription.text = "Hello, can you hear me?"
    mock_w1 = MagicMock(word="Hello,", start_offset="0.0s", end_offset="0.8s")
    mock_w2 = MagicMock(word="hear", start_offset="0.9s", end_offset="1.8s")
    mock_part1.audio_transcription.words = [mock_w1, mock_w2]

    # Part 2: Others (2.0s - 3.8s)
    mock_part2 = MagicMock()
    mock_part2.text = None
    mock_part2.audio_transcription.speaker_label = "spk:1"
    mock_part2.audio_transcription.text = "Yes, loud and clear."
    mock_w3 = MagicMock(word="Yes,", start_offset="2.0s", end_offset="2.8s")
    mock_w4 = MagicMock(word="clear.", start_offset="2.9s", end_offset="3.8s")
    mock_part2.audio_transcription.words = [mock_w3, mock_w4]

    mock_candidate = MagicMock()
    mock_candidate.content.parts = [mock_part1, mock_part2]
    mock_response.candidates = [mock_candidate]
    mock_client.models.generate_content.return_value = mock_response
    service.client = mock_client

    # Stereo audio: Left channel active at 0-2s, Right channel active at 2-4s
    sr = 16000
    pcm = np.zeros((4 * sr, 2), dtype=np.float32)
    t = np.linspace(0, 2.0, 2 * sr, endpoint=False)
    pcm[0:2 * sr, 0] = (np.sin(2 * np.pi * 440.0 * t) * 0.5).astype(np.float32)
    pcm[2 * sr:4 * sr, 1] = (np.sin(2 * np.pi * 440.0 * t) * 0.5).astype(np.float32)
    
    from src.audio.mixer import AudioMixer
    dummy_wav = AudioMixer.convert_to_wav_bytes(pcm, sample_rate=16000)

    result = service.transcribe_chunk(dummy_wav)
    assert "Me: Hello, can you hear me?" in result
    assert "Others: Yes, loud and clear." in result
    
    raw_log = service.appender.read_raw_log()
    assert "Me: Hello, can you hear me?" in raw_log
    assert "Others: Yes, loud and clear." in raw_log

def test_transcribe_chunk_gemini_multiple_remote_speakers(temp_transcript_dir):
    service = TranscriberService(api_key="mock-api-key")
    service.appender = FileAppender(temp_transcript_dir)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = None

    mock_part1 = MagicMock()
    mock_part1.text = None
    mock_part1.audio_transcription.speaker_label = "spk:0"
    mock_part1.audio_transcription.text = "My proposal is ready."
    mock_part1.audio_transcription.words = [
        MagicMock(word="My", start_offset="0.0s", end_offset="0.5s"),
        MagicMock(word="ready.", start_offset="0.6s", end_offset="1.8s")
    ]

    mock_part2 = MagicMock()
    mock_part2.text = None
    mock_part2.audio_transcription.speaker_label = "spk:1"
    mock_part2.audio_transcription.text = "I like it."
    mock_part2.audio_transcription.words = [
        MagicMock(word="I", start_offset="2.0s", end_offset="2.5s"),
        MagicMock(word="it.", start_offset="2.6s", end_offset="3.5s")
    ]

    mock_part3 = MagicMock()
    mock_part3.text = None
    mock_part3.audio_transcription.speaker_label = "spk:2"
    mock_part3.audio_transcription.text = "I have a question."
    mock_part3.audio_transcription.words = [
        MagicMock(word="I", start_offset="4.0s", end_offset="4.5s"),
        MagicMock(word="question.", start_offset="4.6s", end_offset="5.5s")
    ]

    mock_candidate = MagicMock()
    mock_candidate.content.parts = [mock_part1, mock_part2, mock_part3]
    mock_response.candidates = [mock_candidate]
    mock_client.models.generate_content.return_value = mock_response
    service.client = mock_client

    # Stereo audio: Left channel at 0-2s, Right channel at 2-6s
    sr = 16000
    pcm = np.zeros((6 * sr, 2), dtype=np.float32)
    t = np.linspace(0, 2.0, 2 * sr, endpoint=False)
    pcm[0:2 * sr, 0] = (np.sin(2 * np.pi * 440.0 * t) * 0.5).astype(np.float32)
    pcm[2 * sr:6 * sr, 1] = (np.sin(2 * np.pi * 440.0 * np.linspace(0, 4.0, 4 * sr, endpoint=False)) * 0.5).astype(np.float32)

    from src.audio.mixer import AudioMixer
    dummy_wav = AudioMixer.convert_to_wav_bytes(pcm, sample_rate=16000)

    result = service.transcribe_chunk(dummy_wav)
    assert "Me: My proposal is ready." in result
    assert "Others (spk:1): I like it." in result
    assert "Others (spk:2): I have a question." in result

def test_transcribe_chunk_room_phone_call(temp_transcript_dir):
    service = TranscriberService(api_key="mock-api-key")
    service.appender = FileAppender(temp_transcript_dir)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = None

    mock_part1 = MagicMock()
    mock_part1.text = None
    mock_part1.audio_transcription.speaker_label = "spk:0"
    mock_part1.audio_transcription.text = "Hello, car rental service."
    mock_part1.audio_transcription.words = [
        MagicMock(word="Hello,", start_offset="0.0s", end_offset="1.5s")
    ]

    mock_part2 = MagicMock()
    mock_part2.text = None
    mock_part2.audio_transcription.speaker_label = "spk:1"
    mock_part2.audio_transcription.text = "Hi, I have a reservation."
    mock_part2.audio_transcription.words = [
        MagicMock(word="Hi,", start_offset="2.0s", end_offset="3.5s")
    ]

    mock_candidate = MagicMock()
    mock_candidate.content.parts = [mock_part1, mock_part2]
    mock_response.candidates = [mock_candidate]
    mock_client.models.generate_content.return_value = mock_response
    service.client = mock_client

    # Stereo audio: Left channel has all speech, Right channel (loopback) has 0 sound
    sr = 16000
    pcm = np.zeros((4 * sr, 2), dtype=np.float32)
    pcm[0:4 * sr, 0] = (np.sin(2 * np.pi * 440.0 * np.linspace(0, 4.0, 4 * sr, endpoint=False)) * 0.5).astype(np.float32)

    from src.audio.mixer import AudioMixer
    dummy_wav = AudioMixer.convert_to_wav_bytes(pcm, sample_rate=16000)

    result = service.transcribe_chunk(dummy_wav)
    assert "Speaker 1: Hello, car rental service." in result
    assert "Speaker 2: Hi, I have a reservation." in result

def test_transcribe_chunk_silence_skipped(temp_transcript_dir):
    from src.audio.mixer import AudioMixer
    import numpy as np

    service = TranscriberService(api_key="mock-api-key")
    service.appender = FileAppender(temp_transcript_dir)

    # 5 seconds of pure zero silence packed as genuine WAV
    silent_samples = np.zeros(16000 * 5, dtype=np.float32)
    silent_wav = AudioMixer.convert_to_wav_bytes(silent_samples, sample_rate=16000)

    # Should detect silence and return empty string without calling APIs
    result = service.transcribe_chunk(silent_wav)
    assert result == ""
    # Raw log should remain empty
    assert service.appender.read_raw_log() == ""


