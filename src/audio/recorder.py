import os
import sys
import threading
from datetime import datetime
from pathlib import Path
import numpy as np
import soundfile as sf
from src.config import RECORDINGS_DIR

class AudioRecorder:
    """
    Manages continuous background audio recording into timestamped 10-minute chunks.
    Organizes files into daily subdirectories and supports smart silence filtering.
    """
    def __init__(
        self,
        output_dir: Path = RECORDINGS_DIR,
        chunk_duration_sec: int = 600,
        sample_rate: int = 16000,
        audio_format: str = "mp3",
        save_silent_chunks: bool = False,
        enabled: bool = True,
        min_flush_sec: float = 2.0
    ):
        self.output_dir = Path(output_dir)
        self.chunk_duration_sec = int(chunk_duration_sec)
        self.sample_rate = int(sample_rate)
        self.audio_format = audio_format.lower().lstrip(".")
        self.save_silent_chunks = bool(save_silent_chunks)
        self.enabled = bool(enabled)
        self.min_flush_sec = float(min_flush_sec)

        self._lock = threading.Lock()
        self._buffer = []
        self._total_samples = 0
        self._target_samples = self.chunk_duration_sec * self.sample_rate
        self._chunk_start_time = None
        self._has_speech = False

    def get_current_recording_filename(self) -> str | None:
        """
        Returns the filename of the active recording chunk for transcript cross-referencing.
        Returns None if no recording chunk is currently active.
        """
        with self._lock:
            if self._chunk_start_time is None or self._total_samples == 0:
                return None
            date_str = self._chunk_start_time.strftime("%Y-%m-%d")
            time_str = self._chunk_start_time.strftime("%H-%M-%S")
            return f"recording_{date_str}_{time_str}.{self.audio_format}"

    def feed_chunk(self, samples: np.ndarray, speech_present: bool = False) -> str | None:
        """
        Appends standardized audio samples to the current chunk buffer.
        If accumulated audio reaches chunk_duration_sec, flushes the chunk to disk.
        Args:
            samples (np.ndarray): Audio samples (1D or 2D float32).
            speech_present (bool): Whether speech activity was detected in this chunk.
        Returns:
            str | None: The saved file path if a chunk was finalized to disk, otherwise None.
        """
        if not self.enabled or len(samples) == 0:
            return None

        with self._lock:
            if self._chunk_start_time is None:
                self._chunk_start_time = datetime.now()

            self._buffer.append(samples)
            self._total_samples += len(samples)
            if speech_present:
                self._has_speech = True

            if self._total_samples >= self._target_samples:
                return self._flush_locked(is_rotation=True)

            return None

    def flush(self) -> str | None:
        """
        Flushes and writes any pending audio in the buffer to disk (e.g. on pause or app exit).
        Returns:
            str | None: The saved file path if written, otherwise None.
        """
        with self._lock:
            return self._flush_locked(is_rotation=False)

    def _flush_locked(self, is_rotation: bool = False) -> str | None:
        """
        Internal flush method. Must be called while holding self._lock.
        """
        if not self._buffer or self._chunk_start_time is None:
            self._reset_state_locked()
            return None

        total_samples = sum(len(b) for b in self._buffer)
        if is_rotation and total_samples >= self._target_samples:
            chunk_length = self._target_samples
        else:
            chunk_length = total_samples
        leftover_length = total_samples - chunk_length

        duration_sec = chunk_length / self.sample_rate
        chunk_start = self._chunk_start_time
        has_speech = self._has_speech

        # Discard if chunk is shorter than minimum flush threshold, or (Smart Filtering) if no speech
        # occurred and silent chunk saving is disabled. Decided up front so a discarded chunk is never concatenated.
        will_save = duration_sec >= self.min_flush_sec and (has_speech or self.save_silent_chunks)

        if will_save:
            all_samples = np.concatenate(self._buffer)
            chunk_samples = all_samples[:chunk_length]
            # A copy, so the carried-over tail does not pin the whole previous chunk in memory
            leftover_samples = all_samples[chunk_length:].copy()
        else:
            leftover_samples = self._tail_copy_locked(leftover_length)

        # Setup state for the next chunk if rotating
        if is_rotation and leftover_length > 0:
            self._buffer = [leftover_samples]
            self._total_samples = leftover_length
            self._chunk_start_time = datetime.now()
            self._has_speech = False
        else:
            self._reset_state_locked()

        if not will_save:
            return None

        # Build directory and file paths
        date_str = chunk_start.strftime("%Y-%m-%d")
        time_str = chunk_start.strftime("%H-%M-%S")
        filename = f"recording_{date_str}_{time_str}.{self.audio_format}"
        day_dir = self.output_dir / date_str

        try:
            day_dir.mkdir(parents=True, exist_ok=True)
            target_path = day_dir / filename
            tmp_path = day_dir / f"{filename}.tmp"

            # Prevent digital clipping distortion
            clipped = np.clip(chunk_samples, -1.0, 1.0)

            # Determine format and write
            if self.audio_format == "mp3":
                sf.write(str(tmp_path), clipped, self.sample_rate, format="MP3")
            elif self.audio_format == "wav":
                sf.write(str(tmp_path), clipped, self.sample_rate, format="WAV", subtype="PCM_16")
            elif self.audio_format == "flac":
                sf.write(str(tmp_path), clipped, self.sample_rate, format="FLAC")
            elif self.audio_format == "ogg":
                sf.write(str(tmp_path), clipped, self.sample_rate, format="OGG")
            else:
                # Fallback to WAV
                sf.write(str(tmp_path), clipped, self.sample_rate, format="WAV", subtype="PCM_16")

            # Atomic replace
            tmp_path.replace(target_path)
            return str(target_path)
        except Exception as e:
            print(f"[Warning] Failed to save audio chunk to {filename}: {e}", file=sys.stderr)
            if 'tmp_path' in locals() and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            return None

    def _tail_copy_locked(self, num_samples: int):
        """
        Returns a new array holding the last num_samples buffered samples (None if num_samples is 0),
        concatenating only the trailing buffer pieces. Must be called while holding self._lock.
        """
        if num_samples <= 0:
            return None
        pieces = []
        needed = num_samples
        for piece in reversed(self._buffer):
            if needed <= 0:
                break
            if len(piece) > needed:
                piece = piece[len(piece) - needed:]
            pieces.append(piece)
            needed -= len(piece)
        pieces.reverse()
        return np.concatenate(pieces)

    def _reset_state_locked(self):
        """
        Resets active accumulator state. Must be called while holding self._lock.
        """
        self._buffer = []
        self._total_samples = 0
        self._chunk_start_time = None
        self._has_speech = False
