import io
import wave
import numpy as np
from src.audio.mixer import AudioMixer

def test_linear_resample():
    # Create a simple 2-second constant frequency signal at 48000Hz
    orig_sr = 48000
    target_sr = 16000
    duration = 2.0
    num_samples = int(orig_sr * duration)
    
    # 440 Hz wave
    t = np.linspace(0, duration, num_samples, endpoint=False)
    samples = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)
    
    # Resample
    resampled = AudioMixer.resample(samples, orig_sr, target_sr)
    
    # Assert resampled size matches duration * target_sr exactly
    assert len(resampled) == int(target_sr * duration)
    assert resampled.dtype == np.float32

def test_mix_and_standardize():
    # Create dummy samples
    mic_sr = 16000
    spk_sr = 48000
    
    # 1 second of mic audio (all 0.8 values)
    mic_samples = np.full(mic_sr, 0.8, dtype=np.float32)
    # 1 second of speaker audio (all 0.4 values)
    spk_samples = np.full(spk_sr, 0.4, dtype=np.float32)
    
    mixed = AudioMixer.mix_and_standardize(
        mic_samples=mic_samples, mic_sr=mic_sr,
        speaker_samples=spk_samples, speaker_sr=spk_sr,
        target_sr=16000
    )
    
    # Assert: Output length should be exactly 16000 samples (1 second at 16kHz)
    assert len(mixed) == 16000
    assert mixed.dtype == np.float32
    
    # Assert: No clipping occurred (amplitude should be safely normalized by 0.5 factors)
    # mic (0.8 * 0.5) + speaker (0.4 * 0.5) = 0.4 + 0.2 = 0.6
    assert np.allclose(mixed, 0.6, atol=1e-5)

def test_convert_to_wav_bytes():
    # 1 second of constant amplitude at 16kHz
    sample_rate = 16000
    samples = np.full(sample_rate, 0.5, dtype=np.float32)
    
    wav_bytes = AudioMixer.convert_to_wav_bytes(samples, sample_rate)
    
    assert isinstance(wav_bytes, bytes)
    assert len(wav_bytes) > 0
    
    # Parse WAV bytes using standard wave module to verify structural formatting
    wav_io = io.BytesIO(wav_bytes)
    with wave.open(wav_io, "rb") as wav_file:
        assert wav_file.getnchannels() == 1  # Mono
        assert wav_file.getsampwidth() == 2  # 16-bit PCM (2 bytes)
        assert wav_file.getframerate() == sample_rate
        assert wav_file.getnframes() == sample_rate  # Exactly 16000 frames
