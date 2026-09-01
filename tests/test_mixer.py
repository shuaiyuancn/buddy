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
    
    # Default: Dual-Channel Stereo
    stereo_mixed = AudioMixer.mix_and_standardize(
        mic_samples=mic_samples, mic_sr=mic_sr,
        speaker_samples=spk_samples, speaker_sr=spk_sr,
        target_sr=16000, stereo=True
    )
    
    # Assert: Output shape should be (16000, 2)
    assert stereo_mixed.shape == (16000, 2)
    assert stereo_mixed.dtype == np.float32
    assert np.allclose(stereo_mixed[:, 0], 0.8, atol=1e-5)  # Channel 0: Mic (Me)
    assert np.allclose(stereo_mixed[:, 1], 0.4, atol=1e-5)  # Channel 1: Speaker (Others)

    # Blended Mono
    mono_mixed = AudioMixer.mix_and_standardize(
        mic_samples=mic_samples, mic_sr=mic_sr,
        speaker_samples=spk_samples, speaker_sr=spk_sr,
        target_sr=16000, stereo=False
    )
    assert len(mono_mixed) == 16000
    assert mono_mixed.dtype == np.float32
    assert np.allclose(mono_mixed, 0.6, atol=1e-5)

def test_convert_to_wav_bytes():
    # 1 second of constant amplitude at 16kHz (Mono)
    sample_rate = 16000
    mono_samples = np.full(sample_rate, 0.5, dtype=np.float32)
    
    mono_wav = AudioMixer.convert_to_wav_bytes(mono_samples, sample_rate)
    assert isinstance(mono_wav, bytes)
    assert len(mono_wav) > 0
    
    with wave.open(io.BytesIO(mono_wav), "rb") as wav_file:
        assert wav_file.getnchannels() == 1  # Mono
        assert wav_file.getsampwidth() == 2  # 16-bit PCM (2 bytes)
        assert wav_file.getframerate() == sample_rate
        assert wav_file.getnframes() == sample_rate

    # 1 second of Stereo
    stereo_samples = np.column_stack((np.full(sample_rate, 0.5), np.full(sample_rate, -0.5))).astype(np.float32)
    stereo_wav = AudioMixer.convert_to_wav_bytes(stereo_samples, sample_rate)
    assert isinstance(stereo_wav, bytes)

    with wave.open(io.BytesIO(stereo_wav), "rb") as wav_file:
        assert wav_file.getnchannels() == 2  # Stereo
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == sample_rate
        assert wav_file.getnframes() == sample_rate

def test_anti_aliased_downsampling():
    orig_sr = 48000
    target_sr = 16000
    duration = 1.0
    t = np.linspace(0, duration, int(orig_sr * duration), endpoint=False)

    # 1. Audible speech frequency (1000 Hz) should be preserved
    speech_signal = np.sin(2 * np.pi * 1000.0 * t).astype(np.float32)
    resampled_speech = AudioMixer.resample(speech_signal, orig_sr, target_sr)
    speech_power = np.mean(resampled_speech ** 2)
    assert speech_power > 0.35  # Preserved near 0.5 power of sine wave

    # 2. Ultrasonic / out-of-band frequency (14000 Hz) should be heavily attenuated
    high_freq_signal = np.sin(2 * np.pi * 14000.0 * t).astype(np.float32)
    resampled_high_freq = AudioMixer.resample(high_freq_signal, orig_sr, target_sr)
    high_freq_power = np.mean(resampled_high_freq ** 2)
    assert high_freq_power < 0.05  # Strongly suppressed by anti-aliasing lowpass filter
