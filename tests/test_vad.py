import pytest
import numpy as np
from src.audio.vad import VoiceActivityDetector

def test_vad_silence_detection():
    vad = VoiceActivityDetector(energy_threshold_db=-45.0, min_speech_duration_sec=0.5)
    
    # 1. Complete zero silence
    zeros = np.zeros(16000 * 5, dtype=np.float32)  # 5 seconds of silence
    assert vad.calculate_rms_db(zeros) == -100.0
    assert not vad.is_speech_present(zeros, sample_rate=16000)

    # 2. Very low level static noise (-60 dBFS)
    quiet_noise = np.random.uniform(-0.001, 0.001, 16000 * 5).astype(np.float32)
    assert vad.calculate_rms_db(quiet_noise) < -50.0
    assert not vad.is_speech_present(quiet_noise, sample_rate=16000)

def test_vad_speech_detection():
    vad = VoiceActivityDetector(energy_threshold_db=-45.0, min_speech_duration_sec=0.5)
    
    # Generate 5 seconds of audio containing a 1.5 second active speech-like burst (400Hz tone with harmonics at -20 dBFS)
    sr = 16000
    total_samples = sr * 5
    audio = np.zeros(total_samples, dtype=np.float32)
    
    # Insert 1.5s tone between 1.0s and 2.5s
    t = np.linspace(0, 1.5, int(1.5 * sr), endpoint=False)
    speech_signal = (0.2 * np.sin(2 * np.pi * 400 * t) + 0.1 * np.sin(2 * np.pi * 800 * t)).astype(np.float32)
    audio[sr:sr + len(speech_signal)] = speech_signal

    assert vad.is_speech_present(audio, sample_rate=16000) is True

def test_vad_brief_click_rejection():
    vad = VoiceActivityDetector(energy_threshold_db=-45.0, min_speech_duration_sec=0.5)
    
    # A single 50ms click should be rejected because min_speech_duration_sec is 0.5s
    sr = 16000
    audio = np.zeros(sr * 3, dtype=np.float32)
    click = np.random.uniform(-0.3, 0.3, int(0.05 * sr)).astype(np.float32)
    audio[sr:sr + len(click)] = click

    assert vad.is_speech_present(audio, sample_rate=16000) is False

def test_vad_empty_array():
    vad = VoiceActivityDetector()
    assert vad.calculate_rms_db(np.array([], dtype=np.float32)) == -100.0
    assert not vad.is_speech_present(np.array([], dtype=np.float32))
