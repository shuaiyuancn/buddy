import io
import wave
import numpy as np
import soundfile as sf

class AudioMixer:
    @staticmethod
    def resample(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """
        Resamples a numpy float32 array using fast linear interpolation.
        Args:
            samples (np.ndarray): Input audio array (float32).
            orig_sr (int): Original sample rate (e.g. 48000).
            target_sr (int): Target sample rate (e.g. 16000).
        Returns:
            np.ndarray: Resampled float32 array.
        """
        if orig_sr == target_sr or len(samples) == 0:
            return samples
        
        # Calculate target sample length based on physical duration
        duration = len(samples) / orig_sr
        num_target_samples = int(duration * target_sr)
        
        orig_indices = np.arange(len(samples))
        target_indices = np.linspace(0, len(samples) - 1, num_target_samples)
        
        return np.interp(target_indices, orig_indices, samples).astype(np.float32)

    @staticmethod
    def mix_and_standardize(mic_samples: np.ndarray, mic_sr: int, 
                            speaker_samples: np.ndarray, speaker_sr: int, 
                            target_sr: int = 16000) -> np.ndarray:
        """
        Standardizes both streams to target_sr and mixes them at normalized amplitude.
        Args:
            mic_samples (np.ndarray): Microphone float32 samples.
            mic_sr (int): Mic hardware sample rate.
            speaker_samples (np.ndarray): Speaker loopback float32 samples.
            speaker_sr (int): Speaker hardware sample rate.
            target_sr (int): Standard output rate.
        Returns:
            np.ndarray: Mixed single-channel float32 array.
        """
        # 1. Ensure inputs are flat 1D arrays (convert stereo/multichannel to mono if needed)
        if mic_samples.ndim > 1:
            mic_samples = mic_samples.mean(axis=1)
        if speaker_samples.ndim > 1:
            speaker_samples = speaker_samples.mean(axis=1)

        # 2. Resample both sources to 16kHz
        resampled_mic = AudioMixer.resample(mic_samples, mic_sr, target_sr)
        resampled_spk = AudioMixer.resample(speaker_samples, speaker_sr, target_sr)

        # 3. Align buffer lengths
        max_len = max(len(resampled_mic), len(resampled_spk))
        if max_len == 0:
            return np.array([], dtype=np.float32)

        padded_mic = np.pad(resampled_mic, (0, max_len - len(resampled_mic)))
        padded_spk = np.pad(resampled_spk, (0, max_len - len(resampled_spk)))

        # 4. Mix and normalize (scale by 0.5 to prevent overflow/clipping)
        mixed = (padded_mic * 0.5) + (padded_spk * 0.5)
        return mixed

    @staticmethod
    def convert_to_wav_bytes(samples: np.ndarray, sample_rate: int = 16000) -> bytes:
        """
        Converts a normalized float32 numpy array into standard 16-bit PCM WAV bytes.
        """
        if len(samples) == 0:
            return b""
        
        # Convert float32 range [-1.0, 1.0] to signed 16-bit PCM range [-32768, 32767]
        quantized = np.clip(samples, -1.0, 1.0) * 32767.0
        pcm16_samples = quantized.astype(np.int16)

        # Write to in-memory bytes buffer formatted as a standard RIFF WAV file
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)      # Mono
            wav_file.setsampwidth(2)      # 2 bytes per sample (16-bit)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm16_samples.tobytes())
        
        return wav_buffer.getvalue()
