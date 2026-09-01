import os
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
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

@patch("google.generativeai.GenerativeModel")
def test_transcribe_chunk_gemini_interaction(mock_model_class, temp_transcript_dir):
    # Setup mock Gemini Client response
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Hello, this is a simulated transcription."
    mock_model.generate_content.return_value = mock_response
    mock_model_class.return_value = mock_model

    # Configure Service with local temp directories
    service = TranscriberService(api_key="mock-api-key")
    service.appender = FileAppender(temp_transcript_dir)

    dummy_wav = b"RIFFmockaudiobytes..."
    result = service.transcribe_chunk(dummy_wav)

    # Verify Gemini is called with the expected prompt and inline audio-structure
    mock_model_class.assert_called_with("gemini-2.5-flash")
    args, kwargs = mock_model.generate_content.call_args
    prompt_list = args[0]
    
    assert "Transcribe the following" in prompt_list[0]
    assert prompt_list[1]["mime_type"] == "audio/wav"
    assert prompt_list[1]["data"] == dummy_wav

    # Verify results are correctly logged to our appender
    assert result == "Hello, this is a simulated transcription."
    raw_log = service.appender.read_raw_log()
    assert "Hello, this is a simulated transcription." in raw_log

@patch("google.generativeai.GenerativeModel")
def test_compile_daily_summary(mock_model_class, temp_transcript_dir):
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "# Daily Summary Report\n\n- Tasks done\n- Ideas saved"
    mock_model.generate_content.return_value = mock_response
    mock_model_class.return_value = mock_model

    service = TranscriberService(api_key="mock-api-key")
    service.appender = FileAppender(temp_transcript_dir)

    # Mock an existing log
    service.appender.append_transcription("User: Next meeting is daily standup.")

    # Patch the global summaries folder directory in config module to prevent cluttering real folders
    with patch("src.ai.transcriber.SUMMARIES_DIR", temp_transcript_dir):
        summary_result = service.compile_daily_summary()

        assert "# Daily Summary Report" in summary_result
        expected_summary_file = temp_transcript_dir / f"{datetime.now().strftime('%Y-%m-%d')}_summary.md"
        assert expected_summary_file.exists()
        assert "# Daily Summary Report" in expected_summary_file.read_text(encoding="utf-8")

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

