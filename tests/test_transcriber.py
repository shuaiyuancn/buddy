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
    mock_client.models.generate_content.return_value = mock_response
    service.client = mock_client

    # Audio with energy/speech so VAD lets it pass
    t = np.linspace(0, 1.0, 16000, endpoint=False)
    tone = (np.sin(2 * np.pi * 440.0 * t) * 0.5).astype(np.float32)
    from src.audio.mixer import AudioMixer
    dummy_wav = AudioMixer.convert_to_wav_bytes(tone, sample_rate=16000)

    result = service.transcribe_chunk(dummy_wav)

    # Verify Gemini is called with the expected model and contents
    mock_client.models.generate_content.assert_called_once()
    call_kwargs = mock_client.models.generate_content.call_args[1]
    assert call_kwargs["model"] == "gemini-2.5-flash"
    assert "Channel 1" in call_kwargs["contents"][0]
    assert "Me:" in call_kwargs["contents"][0]
    assert "Others:" in call_kwargs["contents"][0]

    # Verify results are correctly logged to our appender
    assert result == "Hello, this is a simulated transcription."
    raw_log = service.appender.read_raw_log()
    assert "Hello, this is a simulated transcription." in raw_log

@patch("google.cloud.speech_v2.SpeechClient")
def test_transcribe_chunk_gcp_routing(mock_speech_client_class, temp_transcript_dir):
    # Setup mock SpeechClient and response
    mock_client = MagicMock()
    mock_response = MagicMock()
    
    # Mock result alternatives structure
    mock_alternative = MagicMock()
    mock_alternative.transcript = "This is a high-accuracy Chirp 3 transcription."
    mock_result = MagicMock()
    mock_result.alternatives = [mock_alternative]
    mock_response.results = [mock_result]
    
    mock_client.recognize.return_value = mock_response
    mock_speech_client_class.return_value = mock_client

    # Configure service with GCP provider
    config_dict = {
        "STT_PROVIDER": "gcp",
        "GCP_PROJECT_ID": "test-gcp-project-456",
        "GCP_REGION": "us",
        "GCP_LANGUAGES": ["zh-CN", "en-US"]
    }
    
    service = TranscriberService(api_key="mock-api-key", config_dict=config_dict)
    service.appender = FileAppender(temp_transcript_dir)
    
    # Force initialize mocked client
    service.gcp_client = mock_client

    dummy_wav = b"RIFFmockaudiobytes..."
    result = service.transcribe_chunk(dummy_wav)

    # Verify recognize was called
    assert mock_client.recognize.called
    args, kwargs = mock_client.recognize.call_args
    request = kwargs.get("request") or args[0]
    
    # Verify request details
    assert request.recognizer == "projects/test-gcp-project-456/locations/us/recognizers/_"
    assert request.config.model == "chirp_3"
    assert "zh-CN" in request.config.language_codes
    assert "en-US" in request.config.language_codes
    assert request.content == dummy_wav

    # Verify results are logged and returned
    assert result == "This is a high-accuracy Chirp 3 transcription."
    raw_log = service.appender.read_raw_log()
    assert "This is a high-accuracy Chirp 3 transcription." in raw_log

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

