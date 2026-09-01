import io
import wave
import numpy as np
import soundfile as sf

class AudioMixer:
    @staticmethod
    def _design_lowpass_fir(cutoff_ratio: float, num_taps: int = 31) -> np.ndarray:
        """
        Designs a windowed sinc low-pass FIR filter kernel for anti-aliasing.
        Args:
            cutoff_ratio (float): Normalized cutoff frequency relative to sample rate (0 < cutoff_ratio < 0.5).
            num_taps (int): Number of filter coefficients (must be odd).
        Returns:
            np.ndarray: Normalized float32 FIR filter kernel.
        """
        n = np.arange(num_taps) - (num_taps - 1) / 2.0
        h = np.sinc(2 * cutoff_ratio * n)
        w = np.hamming(num_taps)
        h = h * w
        sum_h = np.sum(h)
        if sum_h != 0:
            h = h / sum_h
        return h.astype(np.float32)

    @staticmethod
    def resample(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """
        Resamples a numpy float32 array using anti-aliased polyphase/FIR decimation and interpolation.
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
        if num_target_samples == 0:
            return np.array([], dtype=np.float32)

        # Anti-aliasing filtering when downsampling (target_sr < orig_sr)
        if target_sr < orig_sr:
            cutoff = (target_sr * 0.45) / orig_sr
            num_taps = 31
            h = AudioMixer._design_lowpass_fir(cutoff, num_taps=num_taps)
            pad_len = num_taps // 2
            padded = np.pad(samples, pad_len, mode='edge')
            filtered = np.convolve(padded, h, mode='valid')
        else:
            filtered = samples

        # Integer decimation optimization (e.g. 48000 -> 16000 is factor 3)
        if orig_sr % target_sr == 0 and len(filtered) >= (orig_sr // target_sr):
            ratio = orig_sr // target_sr
            resampled = filtered[::ratio][:num_target_samples]
            return resampled.astype(np.float32)
        
        orig_indices = np.arange(len(filtered))
        target_indices = np.linspace(0, len(filtered) - 1, num_target_samples)
        
        return np.interp(target_indices, orig_indices, filtered).astype(np.float32)

    @staticmethod
    def mix_and_standardize(mic_samples: np.ndarray, mic_sr: int, 
                            speaker_samples: np.ndarray, speaker_sr: int, 
                            target_sr: int = 16000,
                            stereo: bool = True) -> np.ndarray:
        """
        Standardizes both streams to target_sr and aligns them into a dual-channel stereo stream
        (Channel 1 = Mic / 'Me', Channel 2 = Speaker Loopback / 'Others') or blended mono stream.
        Args:
            mic_samples (np.ndarray): Microphone float32 samples.
            mic_sr (int): Mic hardware sample rate.
            speaker_samples (np.ndarray): Speaker loopback float32 samples.
            speaker_sr (int): Speaker hardware sample rate.
            target_sr (int): Standard output rate.
            stereo (bool): If True, returns 2D array of shape (N, 2); if False, blends into 1D mono.
        Returns:
            np.ndarray: Dual-channel (N, 2) or single-channel float32 array.
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
            return np.zeros((0, 2), dtype=np.float32) if stereo else np.array([], dtype=np.float32)

        padded_mic = np.pad(resampled_mic, (0, max_len - len(resampled_mic)))
        padded_spk = np.pad(resampled_spk, (0, max_len - len(resampled_spk)))

        if stereo:
            # Channel 0 (Left) = Mic ('Me'), Channel 1 (Right) = Speaker Loopback ('Others')
            return np.column_stack((padded_mic, padded_spk)).astype(np.float32)
        else:
            # Mix and normalize (scale by 0.5 to prevent overflow/clipping)
            mixed = (padded_mic * 0.5) + (padded_spk * 0.5)
            return mixed.astype(np.float32)

    @staticmethod
    def convert_to_wav_bytes(samples: np.ndarray, sample_rate: int = 16000) -> bytes:
        """
        Converts a normalized float32 numpy array (1D Mono or 2D Stereo) into standard 16-bit PCM WAV bytes.
        """
        if len(samples) == 0:
            return b""
        
        # Determine channel count
        num_channels = 2 if (samples.ndim == 2 and samples.shape[1] == 2) else 1

        # Convert float32 range [-1.0, 1.0] to signed 16-bit PCM range [-32768, 32767]
        quantized = np.clip(samples, -1.0, 1.0) * 32767.0
        pcm16_samples = np.ascontiguousarray(quantized).astype(np.int16)

        # Write to in-memory bytes buffer formatted as a standard RIFF WAV file
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(num_channels)
            wav_file.setsampwidth(2)      # 2 bytes per sample (16-bit)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm16_samples.tobytes())
        
        return wav_buffer.getvalue()
