import math
import numpy as np

class VoiceActivityDetector:
    """
    Lightweight, high-performance Voice Activity Detector (VAD).
    Uses frame-level RMS energy (dBFS) and Zero-Crossing Rate (ZCR) to detect human speech
    and discard silent or non-speech background audio without making external API calls.
    """
    def __init__(self, 
                 energy_threshold_db: float = -45.0, 
                 min_speech_duration_sec: float = 0.5,
                 frame_duration_ms: int = 30):
        """
        Args:
            energy_threshold_db (float): Silence cutoff in dBFS. Samples below this are considered silence.
            min_speech_duration_sec (float): Minimum cumulative speech duration needed in a chunk to trigger STT.
            frame_duration_ms (int): Sub-frame size in milliseconds for temporal energy analysis.
        """
        self.energy_threshold_db = energy_threshold_db
        self.min_speech_duration_sec = min_speech_duration_sec
        self.frame_duration_ms = frame_duration_ms

    @staticmethod
    def calculate_rms_db(samples: np.ndarray) -> float:
        """
        Calculates Root Mean Square (RMS) energy in decibels relative to full scale (dBFS).
        """
        if len(samples) == 0:
            return -100.0
        
        # Ensure flat float32 array
        if samples.ndim > 1:
            samples = samples.flatten()
            
        mean_square = np.mean(np.square(samples.astype(np.float64)))
        if mean_square <= 1e-12:
            return -100.0
            
        rms = math.sqrt(mean_square)
        db = 20.0 * math.log10(max(rms, 1e-5))
        return float(db)

    @staticmethod
    def calculate_zcr(samples: np.ndarray) -> float:
        """
        Calculates the Zero-Crossing Rate (ZCR) of an audio frame.
        Speech typically exhibits moderate ZCR compared to high-frequency noise or DC offsets.
        """
        if len(samples) < 2:
            return 0.0
        
        zero_crossings = np.sum(np.abs(np.diff(np.sign(samples)))) / 2
        return float(zero_crossings / len(samples))

    def is_speech_present(self, samples: np.ndarray, sample_rate: int = 16000) -> bool:
        """
        Analyzes audio buffer using sliding temporal sub-frames.
        Returns True if total detected speech duration exceeds min_speech_duration_sec.
        """
        if len(samples) == 0:
            return False

        if samples.ndim > 1:
            samples = samples.mean(axis=1)

        frame_size = int(sample_rate * (self.frame_duration_ms / 1000.0))
        if frame_size <= 0 or len(samples) < frame_size:
            # Fallback to single chunk check
            return self.calculate_rms_db(samples) > self.energy_threshold_db

        num_frames = len(samples) // frame_size
        speech_frames = 0

        for i in range(num_frames):
            frame = samples[i * frame_size:(i + 1) * frame_size]
            rms_db = self.calculate_rms_db(frame)
            
            # Check if frame energy exceeds threshold
            if rms_db > self.energy_threshold_db:
                zcr = self.calculate_zcr(frame)
                # Filter out pure DC offset (zcr near 0) or extreme ultrasonic noise (zcr > 0.85)
                if 0.01 <= zcr <= 0.85:
                    speech_frames += 1

        detected_speech_duration = speech_frames * (self.frame_duration_ms / 1000.0)
        return detected_speech_duration >= self.min_speech_duration_sec
