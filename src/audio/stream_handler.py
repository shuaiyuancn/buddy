import time
import queue
import logging
import threading
import numpy as np
import soundcard as sc
from PySide6.QtCore import QThread, Signal
from src.audio.mixer import AudioMixer
from src.audio.vad import VoiceActivityDetector

logger = logging.getLogger("buddy.audio")

MIC_SAMPLE_RATE = 16000          # Microphone is captured natively at 16 kHz mono
SPEAKER_SAMPLE_RATE = 48000      # Speaker loopback capture rate
MIC_BLOCK_SEC = 0.1              # Length of one microphone read/queue block
SPEAKER_BLOCK_SEC = 1.0          # Length of one speaker loopback read/queue block
CAPTURE_BUFFER_SEC = 0.5         # WASAPI capture buffer (recorder blocksize) so a late read does not drop audio
ZERO_FILL_CAP_SEC = 2.0          # Most audio one soundcard _record_chunk() call may return before it counts as a standby backlog
CAPTURE_STALL_SEC = 5.0          # A record() call slower than this means the thread was frozen (standby): discard and reopen
QUEUE_MAX_SEC = 30.0             # Capture queues hold at most this much audio; the oldest block is dropped beyond it
QUEUE_DROP_LOG_INTERVAL_SEC = 60.0  # At most one log line per this many seconds about dropped queue blocks
MAX_STEP_SEC = 5.0               # Most audio per stream the orchestrator mixes in one step; older excess is dropped
DICTATION_MAX_SEC = 300          # Longest dictation kept (5 minutes); later audio is ignored until the hotkey is pressed
DICTATION_LIMIT_MESSAGE = "Dictation reached the 5 minute limit. Press the hotkey to finish."


class _BacklogGuard:
    """Remembers how much audio the _record_chunk guard cut off (see _install_backlog_guard)."""
    def __init__(self, cap_samples: int, samples_per_sec: int):
        self.cap_samples = cap_samples
        self.samples_per_sec = samples_per_sec
        self.dropped_samples = 0

    def take_dropped_sec(self) -> float:
        """Returns the seconds of audio dropped since the last call, and resets the count."""
        dropped, self.dropped_samples = self.dropped_samples, 0
        return dropped / self.samples_per_sec


def _install_backlog_guard(recorder, samplerate: int, channels: int, label: str):
    """
    Caps how much audio a single soundcard `_record_chunk()` call can return on this recorder instance.

    This reaches into a private method because soundcard offers no public hook for it. On Windows
    (soundcard/mediafoundation.py, _Recorder), `_record_chunk()` polls while no capture frames are
    available and, once it has been idle for a few device periods, returns a zero array covering the
    whole idle time with no upper bound. If the thread is frozen inside that wait during Modern Standby,
    the first call after wake returns one array spanning the entire standby (hours, gigabytes), and
    `record()` keeps serving the excess from `_pending_chunk`. The guard keeps only the first
    `samplerate x channels x ZERO_FILL_CAP_SEC` samples as a fresh copy, so the giant array is released
    without its lazily zeroed pages ever being touched, and records the drop so the capture loop can
    discard the block and reopen the device.

    Returns the guard, or None if the recorder could not be wrapped (capture then runs unguarded).
    """
    try:
        original = recorder._record_chunk
        guard = _BacklogGuard(int(samplerate * channels * ZERO_FILL_CAP_SEC), samplerate * channels)

        def guarded_record_chunk():
            chunk = original()
            if chunk is not None and len(chunk) > guard.cap_samples:
                guard.dropped_samples += len(chunk) - guard.cap_samples
                chunk = chunk[:guard.cap_samples].copy()
            return chunk

        recorder._record_chunk = guarded_record_chunk
        return guard
    except Exception as e:
        logger.info(f"{label} capture: standby backlog guard not installed ({type(e).__name__}: {e}); continuing without it")
        return None


def _channel_count(device, default: int) -> int:
    """Channel count soundcard will record from device when none is requested; default if unknown."""
    try:
        count = int(device.channels)
    except Exception:
        return default
    return count if count > 0 else default


class AudioStreamHandler(QThread):
    # Qt Signal emitted when a mixed 60-second WAV chunk is completed
    chunk_ready = Signal(bytes)
    # Signal emitted when real-time speech activity changes (True=speaking/active, False=sleeping/silent)
    speech_activity_changed = Signal(bool)
    # Signal emitted for logging system warnings to the UI
    warning_logged = Signal(str)

    def __init__(self, target_sr: int = 16000, window_duration_sec: int = 60, overlap_duration_sec: int = 3, energy_threshold_db: float = -45.0, config_dict: dict = None):
        super().__init__()
        self.target_sr = target_sr
        self.window_duration_sec = window_duration_sec
        self.overlap_duration_sec = overlap_duration_sec
        self.total_target_samples = target_sr * window_duration_sec
        self.overlap_samples = target_sr * overlap_duration_sec
        self.vad = VoiceActivityDetector(energy_threshold_db=energy_threshold_db)
        self.config = config_dict or {}

        # Audio Recorder initialization for 10-minute chunk persistence
        from src.audio.recorder import AudioRecorder
        from src.config import RECORDINGS_DIR

        chunk_minutes = self.config.get("RECORDING_CHUNK_MINUTES", 10)
        audio_format = self.config.get("RECORDING_FORMAT", "mp3")
        save_silent = self.config.get("RECORDING_SAVE_SILENT_CHUNKS", False)
        save_enabled = self.config.get("SAVE_AUDIO_RECORDINGS", True)

        self.recorder = AudioRecorder(
            output_dir=RECORDINGS_DIR,
            chunk_duration_sec=chunk_minutes * 60,
            sample_rate=target_sr,
            audio_format=audio_format,
            save_silent_chunks=save_silent,
            enabled=save_enabled
        )

        self._is_running = False
        self._is_paused = False
        self._is_dictating = False
        self._dictation_buffer = []
        self._dictation_samples = 0
        self.dictation_max_samples = int(MIC_SAMPLE_RATE * DICTATION_MAX_SEC)
        self._dictation_lock = threading.Lock()
        self._is_speech_active = False
        self._silence_hangover_sec = 3
        self._recent_speech_countdown = 0
        self.current_mic_name = "unknown"
        self.current_speaker_name = "unknown"
        # Endpoint ids chosen in the tray menu; empty means follow the Windows default device
        self.preferred_mic_id = self.config.get("MICROPHONE_DEVICE_ID", "") or ""
        self.preferred_speaker_id = self.config.get("SPEAKER_DEVICE_ID", "") or ""
        # How often capture threads check whether the Windows default device has changed
        self.device_check_interval_sec = 2.0
        
        # Thread-safe queues for communication between worker threads and orchestrator
        # Bounded: when full, the oldest block is dropped (see _put_latest) so capture never blocks
        self.mic_queue = queue.Queue(maxsize=round(QUEUE_MAX_SEC / MIC_BLOCK_SEC))
        self.speaker_queue = queue.Queue(maxsize=round(QUEUE_MAX_SEC / SPEAKER_BLOCK_SEC))
        self._queue_drop_lock = threading.Lock()
        self._queue_drops = 0
        self._queue_drop_logged_at = float("-inf")

        # Shared buffer for mixed 16kHz float32 audio samples (list of numpy arrays)
        self.mixed_buffer = []

        # Worker threads references
        self.mic_thread = None
        self.speaker_thread = None

    def run(self):
        """
        Main QThread Event Loop. Orchestrates child recording threads and mixes buffers.
        """
        self._is_running = True
        self._is_paused = False
        self._is_speech_active = False
        self._recent_speech_countdown = 0
        self.mixed_buffer = []

        # Start child recorders
        self.mic_thread = threading.Thread(target=self._record_microphone, daemon=True)
        self.speaker_thread = threading.Thread(target=self._record_speaker_loopback, daemon=True)
        
        self.mic_thread.start()
        self.speaker_thread.start()

        # Orchestration Loop
        while self._is_running:
            # Dictation keeps working while background listening is paused
            if self._is_paused and not self._is_dictating:
                time.sleep(0.5)
                continue

            # Every 1.0 second, fetch data from both queues
            time.sleep(1.0)

            is_dictating = self._collect_dictation_audio()

            if is_dictating:
                # Speaker audio is not part of dictation and is not recorded meanwhile
                while not self.speaker_queue.empty():
                    self.speaker_queue.get_nowait()
                continue

            if self._is_paused:
                continue

            # Compile samples for this 1-second step
            mic_data = self._drain_step_audio(self.mic_queue, MIC_SAMPLE_RATE, "Microphone")
            spk_data = self._drain_step_audio(self.speaker_queue, SPEAKER_SAMPLE_RATE, "Speaker")

            # If we received no samples from either device, write silence to keep stream ticking
            if len(mic_data) == 0 and len(spk_data) == 0:
                mic_data = np.zeros(self.target_sr, dtype=np.float32)
                spk_data = np.zeros(48000, dtype=np.float32)  # assuming 48k default for speaker

            # Mix down and resample to 16kHz mono
            mixed_chunk = AudioMixer.mix_and_standardize(
                mic_samples=mic_data, mic_sr=16000,
                speaker_samples=spk_data, speaker_sr=48000,
                target_sr=self.target_sr
            )

            if len(mixed_chunk) > 0:
                self.mixed_buffer.append(mixed_chunk)

                # Real-time speech activity detection for System Tray visual state
                is_current_speech = self.vad.is_speech_present(mixed_chunk, self.target_sr)
                if is_current_speech:
                    self._recent_speech_countdown = self._silence_hangover_sec
                    if not self._is_speech_active:
                        self._is_speech_active = True
                        self.speech_activity_changed.emit(True)
                else:
                    if self._recent_speech_countdown > 0:
                        self._recent_speech_countdown -= 1
                    else:
                        if self._is_speech_active:
                            self._is_speech_active = False
                            self.speech_activity_changed.emit(False)

                # Feed to audio recorder for continuous 10-minute chunk persistence
                if hasattr(self, "recorder") and self.recorder is not None:
                    self.recorder.feed_chunk(mixed_chunk, speech_present=is_current_speech)

            self._emit_ready_windows()

    def _collect_dictation_audio(self) -> bool:
        """
        In dictation mode, moves microphone audio into the dictation buffer under the lock and returns True.
        Checking the flag and draining in one step means audio drained here can never be
        lost to a stop_dictation() call landing between the drain and the check.
        Warns the user once when the dictation reaches its maximum length.
        """
        limit_reached = False
        with self._dictation_lock:
            is_dictating = self._is_dictating
            if is_dictating:
                while not self.mic_queue.empty():
                    limit_reached |= self._append_dictation_locked(self.mic_queue.get_nowait())
        if limit_reached:
            self.warning_logged.emit(DICTATION_LIMIT_MESSAGE)
        return is_dictating

    def _append_dictation_locked(self, chunk: np.ndarray) -> bool:
        """
        Adds microphone audio to the dictation buffer up to dictation_max_samples; audio past it is dropped.
        Returns True only on the call that reaches the limit. Must be called while holding _dictation_lock.
        """
        room = self.dictation_max_samples - self._dictation_samples
        if room <= 0:
            return False
        if len(chunk) > room:
            chunk = chunk[:room]
        self._dictation_buffer.append(chunk)
        self._dictation_samples += len(chunk)
        if self._dictation_samples >= self.dictation_max_samples:
            logger.warning(f"Dictation reached the {DICTATION_MAX_SEC / 60:.0f} minute limit; "
                           "further audio is ignored until the hotkey is pressed")
            return True
        return False

    def _drain_step_audio(self, q: queue.Queue, sample_rate: int, label: str) -> np.ndarray:
        """
        Takes everything queued for one orchestrator step. More than MAX_STEP_SEC (a capture loop that
        caught up after a stall) is cut to the most recent MAX_STEP_SEC so one step never mixes a backlog.
        """
        chunks = []
        while not q.empty():
            chunks.append(q.get_nowait())
        data = np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)
        max_samples = int(sample_rate * MAX_STEP_SEC)
        if len(data) > max_samples:
            logger.warning(f"{label} capture delivered {len(data) / sample_rate:.1f} s in one step; "
                           f"keeping only the most recent {MAX_STEP_SEC:.0f} s")
            data = data[-max_samples:].copy()
        return data

    def _emit_ready_windows(self):
        """
        Slices every complete window out of mixed_buffer and emits the ones with speech, so several
        windows' worth can never accumulate. The tail kept for the next window is a copy, not a view
        that would pin the larger concatenated array.
        """
        current_buffer_samples = sum(len(c) for c in self.mixed_buffer)

        # Once the buffer reaches our 60-second window, slice it and emit it
        while current_buffer_samples >= self.total_target_samples:
            all_samples = np.concatenate(self.mixed_buffer)
            target_samples = all_samples[:self.total_target_samples]

            # Advance buffer retaining overlap samples to avoid clipping words at boundaries
            advance_samples = max(1, self.total_target_samples - self.overlap_samples)
            remaining_samples = all_samples[advance_samples:].copy()
            self.mixed_buffer = [remaining_samples] if len(remaining_samples) > 0 else []
            current_buffer_samples = len(remaining_samples)

            # Check for human speech activity before packaging and emitting
            if self.vad.is_speech_present(target_samples, self.target_sr):
                wav_bytes = AudioMixer.convert_to_wav_bytes(target_samples, self.target_sr)
                if wav_bytes:
                    self.chunk_ready.emit(wav_bytes)

    def _put_latest(self, q: queue.Queue, block: np.ndarray):
        """Queues a capture block without ever blocking: when the queue is full the oldest block is dropped."""
        while True:
            try:
                q.put_nowait(block)
                return
            except queue.Full:
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass
                self._note_queue_drop()

    def _note_queue_drop(self):
        """Counts a dropped queue block and logs the count at most once per QUEUE_DROP_LOG_INTERVAL_SEC."""
        with self._queue_drop_lock:
            self._queue_drops += 1
            now = time.monotonic()
            if now - self._queue_drop_logged_at < QUEUE_DROP_LOG_INTERVAL_SEC:
                return
            count, self._queue_drops = self._queue_drops, 0
            self._queue_drop_logged_at = now
        logger.warning(f"Audio capture queue full: dropped {count} oldest block(s) since the last report")

    def _capture_stalled(self, label: str, started: float, guard) -> bool:
        """
        True when the record() call that began at `started` (time.monotonic) took longer than
        CAPTURE_STALL_SEC or returned a standby backlog cut by the guard. The caller discards the block
        and reopens the recorder, which also drops whatever soundcard kept in _pending_chunk.
        """
        stalled_sec = time.monotonic() - started
        dropped_sec = guard.take_dropped_sec() if guard is not None else 0.0
        if stalled_sec <= CAPTURE_STALL_SEC and dropped_sec <= 0:
            return False
        logger.warning(f"{label} capture: discarded ~{max(stalled_sec, dropped_sec):.0f} s of audio after a stalled read "
                       "(likely resume from standby); reopening")
        return True

    def stop(self):
        """
        Shuts down background capturing loops cleanly and joins worker threads.
        """
        self._is_running = False
        if hasattr(self, "recorder") and self.recorder is not None:
            self.recorder.flush()
        self.wait()  # Wait for QThread event loop to end
        if self.mic_thread and self.mic_thread.is_alive():
            self.mic_thread.join(timeout=1.0)
        if self.speaker_thread and self.speaker_thread.is_alive():
            self.speaker_thread.join(timeout=1.0)

    def pause(self):
        """
        Pauses recording aggregation and flushes active audio chunk.
        """
        self._is_paused = True
        if hasattr(self, "recorder") and self.recorder is not None:
            self.recorder.flush()

    def get_current_recording_filename(self) -> str | None:
        """
        Returns the filename of the active 10-minute recording chunk if recording.
        """
        if hasattr(self, "recorder") and self.recorder is not None:
            return self.recorder.get_current_recording_filename()
        return None

    def resume(self):
        """
        Resumes recording aggregation.
        """
        # Clear out stagnant old queue elements to prevent sudden catch-up noise
        while not self.mic_queue.empty():
            self.mic_queue.get_nowait()
        while not self.speaker_queue.empty():
            self.speaker_queue.get_nowait()
            
        self._is_paused = False

    def start_dictation(self):
        """
        Enters dictation mode, turning off normal sliding-window recording and routing
        active microphone audio to a dedicated dictation buffer.
        """
        with self._dictation_lock:
            self._is_dictating = True
            self._dictation_buffer = []
            self._dictation_samples = 0

    def stop_dictation(self) -> bytes:
        """
        Exits dictation mode, drains remaining microphone samples, converts the accumulated
        audio into standardized 16kHz mono WAV bytes, and resumes normal recording.
        """
        with self._dictation_lock:
            self._is_dictating = False
            # Drain any pending microphone chunks immediately
            while not self.mic_queue.empty():
                try:
                    chunk = self.mic_queue.get_nowait()
                    if len(chunk) > 0:
                        self._append_dictation_locked(chunk)
                except queue.Empty:
                    break

            if not self._dictation_buffer:
                return b""

            recorded_samples = np.concatenate(self._dictation_buffer)
            self._dictation_buffer = []
            self._dictation_samples = 0

        return AudioMixer.convert_to_wav_bytes(recorded_samples, sample_rate=self.target_sr)

    def _default_device_changed(self, get_default, device_id: str) -> bool:
        """
        Returns True once the Windows default device no longer matches device_id
        (headset plugged in, Bluetooth connected, default switched in Sound settings).
        A failed lookup also counts as a change so the caller reopens on whatever is default now.
        """
        try:
            return get_default().id != device_id
        except Exception:
            return True

    @staticmethod
    def _pick_device(preferred_id: str, list_devices, get_default):
        """
        Returns the device the user selected (by endpoint id) if it is connected, else the Windows default.
        An unplugged selection therefore falls back to the default and is picked up again when it returns.
        """
        if preferred_id:
            try:
                for device in list_devices():
                    if device.id == preferred_id:
                        return device
            except Exception:
                pass
        return get_default()

    def _selected_microphone(self):
        return self._pick_device(self.preferred_mic_id, sc.all_microphones, sc.default_microphone)

    def _selected_speaker(self):
        return self._pick_device(self.preferred_speaker_id, sc.all_speakers, sc.default_speaker)

    def _record_microphone(self):
        """
        Blocking loop for microphone recording with automatic reconnection on device disconnects.
        Records the microphone selected in the tray menu, or follows the Windows default microphone:
        whenever the device to use changes, the stream is reopened on the new device.
        """
        samplerate = MIC_SAMPLE_RATE  # Record natively at target 16kHz mono
        block_duration = MIC_BLOCK_SEC  # Fetch 100ms chunks for low-latency draining
        block_size = int(samplerate * block_duration)
        retry_delay = 2.0

        while self._is_running:
            try:
                # soundcard (WASAPI) queries the live default each time; sounddevice/PortAudio
                # snapshots the device list at import and never sees newly connected headsets.
                mic = self._selected_microphone()
                with mic.recorder(samplerate=samplerate, channels=1, blocksize=int(samplerate * CAPTURE_BUFFER_SEC)) as recorder:
                    guard = _install_backlog_guard(recorder, samplerate, 1, "Microphone")
                    self.current_mic_name = mic.name
                    print(f"[Buddy] Microphone capture opened on: {mic.name}")
                    next_device_check = time.monotonic() + self.device_check_interval_sec
                    while self._is_running:
                        if time.monotonic() >= next_device_check:
                            next_device_check = time.monotonic() + self.device_check_interval_sec
                            if self._default_device_changed(self._selected_microphone, mic.id):
                                print("[Buddy] Microphone to use changed. Reopening capture...")
                                break

                        if self._is_paused and not self._is_dictating:
                            time.sleep(0.2)
                            continue

                        started = time.monotonic()
                        try:
                            data = recorder.record(numframes=block_size)
                        except MemoryError:
                            logger.error("Microphone capture: out of memory reading audio; discarding it and reopening")
                            break
                        if self._capture_stalled("Microphone", started, guard):
                            break
                        self._put_latest(self.mic_queue, data.flatten().astype(np.float32))
            except Exception as e:
                logger.error(f"Microphone capture error: {type(e).__name__}: {e}")
                self.warning_logged.emit(f"Microphone Capture Error: {str(e)}")
                # Provide silence fallback while backing off before reconnection attempt
                elapsed = 0.0
                while self._is_running and elapsed < retry_delay:
                    if not self._is_paused:
                        self._put_latest(self.mic_queue, np.zeros(block_size, dtype=np.float32))
                    time.sleep(1.0)
                    elapsed += 1.0

    def _record_speaker_loopback(self):
        """
        Blocking loop for speaker loopback (WASAPI) with automatic reconnection.
        Records the speaker selected in the tray menu, or follows the Windows default output:
        whenever the device to use changes, loopback is reopened on the new device.
        """
        samplerate = SPEAKER_SAMPLE_RATE  # Default loopback rate
        block_size = int(samplerate * SPEAKER_BLOCK_SEC)  # 1-second blocks
        retry_delay = 2.0

        while self._is_running:
            try:
                speaker = self._selected_speaker()
                # Match by endpoint id: name matching is fuzzy and can pick a sibling output
                # on the same sound card (e.g. "Speakers" vs "2nd output" on Realtek).
                loopback = sc.get_microphone(id=speaker.id, include_loopback=True)
                with loopback.recorder(samplerate=samplerate, blocksize=int(samplerate * CAPTURE_BUFFER_SEC)) as recorder:
                    guard = _install_backlog_guard(recorder, samplerate, _channel_count(loopback, 2), "Speaker")
                    self.current_speaker_name = speaker.name
                    print(f"[Buddy] Speaker loopback opened on: {speaker.name}")
                    next_device_check = time.monotonic() + self.device_check_interval_sec
                    while self._is_running:
                        if time.monotonic() >= next_device_check:
                            next_device_check = time.monotonic() + self.device_check_interval_sec
                            if self._default_device_changed(self._selected_speaker, speaker.id):
                                print("[Buddy] Speaker to use changed. Reopening loopback...")
                                break

                        if self._is_paused:
                            time.sleep(0.2)
                            continue
                        
                        started = time.monotonic()
                        try:
                            data = recorder.record(numframes=block_size)
                        except MemoryError:
                            logger.error("Speaker capture: out of memory reading audio; discarding it and reopening")
                            break
                        if self._capture_stalled("Speaker", started, guard):
                            break
                        if data.ndim > 1:
                            data = data.mean(axis=1)
                        self._put_latest(self.speaker_queue, data.astype(np.float32))
            except Exception as e:
                logger.error(f"Speaker capture error: {type(e).__name__}: {e}")
                self.warning_logged.emit(f"WASAPI Speaker Capture Error: {str(e)}")
                # Provide silence fallback while backing off before reconnection attempt
                elapsed = 0.0
                while self._is_running and elapsed < retry_delay:
                    if not self._is_paused:
                        self._put_latest(self.speaker_queue, np.zeros(block_size, dtype=np.float32))
                    time.sleep(1.0)
                    elapsed += 1.0
