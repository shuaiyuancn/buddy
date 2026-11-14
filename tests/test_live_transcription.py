import os
import pytest
import numpy as np

from src.ai.transcriber import TranscriberService
from src.audio.mixer import AudioMixer

def load_live_api_key() -> str:
    # Like Buddy itself, read the key only from the environment variable
    key = os.environ.get("GEMINI_API_KEY")
    if key and key.strip():
        return key.strip()
        
    return ""

def test_live_gemini_transcription():
    api_key = load_live_api_key()
    if not api_key:
        pytest.skip("GEMINI_API_KEY environment variable is not set. Skipping live API integration test.")

    print(f"\n[Live Test] Authenticated. Initializing TranscriberService...")
    service = TranscriberService(api_key=api_key)
    
    # Generate 1 second of silent float32 audio at 16000Hz standard
    sample_rate = 16000
    silent_samples = np.zeros(sample_rate, dtype=np.float32)
    
    # Package into standard WAV bytes using the system's AudioMixer
    mixer = AudioMixer()
    wav_bytes = mixer.convert_to_wav_bytes(silent_samples)
    
    assert isinstance(wav_bytes, bytes)
    assert len(wav_bytes) > 0
    
    print("[Live Test] Dispatching 1-second silent WAV chunk to Gemini API (gemini-3.5-transcribe)...")
    result = service.transcribe_chunk(wav_bytes)
    
    print(f"[Live Test] API returned: '{result}'")
    
    # Assert that it did not return any error formatting
    assert "[Error" not in result
    assert "[Transcription Error" not in result
    assert "404" not in result
