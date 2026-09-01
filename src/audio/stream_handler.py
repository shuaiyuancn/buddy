import time
import queue
import threading
import numpy as np
import soundcard as sc
import sounddevice as sd
from PySide6.QtCore import QThread, Signal
from src.audio.mixer import AudioMixer
from src.audio.vad import VoiceActivityDetector

class AudioStreamHandler(QThread):
    # Qt Signal emitted when a mixed 60-second WAV chunk is completed
    chunk_ready = Signal(bytes)
    # Signal emitted for logging system warnings to the UI
    warning_logged = Signal(str)

    def __init__(self, target_sr: int = 16000, window_duration_sec: int = 60, energy_threshold_db: float = -45.0):
        super().__init__()
        self.target_sr = target_sr
        self.window_duration_sec = window_duration_sec
        self.total_target_samples = target_sr * window_duration_sec
        self.vad = VoiceActivityDetector(energy_threshold_db=energy_threshold_db)

        self._is_running = False
        self._is_paused = False
        
        # Thread-safe queues for communication between worker threads and orchestrator
        self.mic_queue = queue.Queue()
        self.speaker_queue = queue.Queue()

        # Shared buffer for mixed 16kHz float32 audio samples
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
        self.mixed_buffer = []

        # Start child recorders
        self.mic_thread = threading.Thread(target=self._record_microphone, daemon=True)
        self.speaker_thread = threading.Thread(target=self._record_speaker_loopback, daemon=True)
        
        self.mic_thread.start()
        self.speaker_thread.start()

        # Orchestration Loop
        while self._is_running:
            if self._is_paused:
                time.sleep(0.5)
                continue

            # Every 1.0 second, fetch data from both queues
            time.sleep(1.0)

            mic_chunks = []
            while not self.mic_queue.empty():
                mic_chunks.append(self.mic_queue.get_nowait())

            spk_chunks = []
            while not self.speaker_queue.empty():
                spk_chunks.append(self.speaker_queue.get_nowait())

            # Compile samples for this 1-second step
            mic_data = np.concatenate(mic_chunks) if mic_chunks else np.array([], dtype=np.float32)
            spk_data = np.concatenate(spk_chunks) if spk_chunks else np.array([], dtype=np.float32)

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

            # Append mixed chunk to our rolling window buffer
            self.mixed_buffer.extend(mixed_chunk.tolist())

            # Once the buffer reaches our 60-second window, slice it and emit it
            if len(self.mixed_buffer) >= self.total_target_samples:
                # Slice exactly 60 seconds of samples
                target_samples = np.array(self.mixed_buffer[:self.total_target_samples], dtype=np.float32)
                self.mixed_buffer = self.mixed_buffer[self.total_target_samples:]

                # Check for human speech activity before packaging and emitting
                if self.vad.is_speech_present(target_samples, self.target_sr):
                    wav_bytes = AudioMixer.convert_to_wav_bytes(target_samples, self.target_sr)
                    if wav_bytes:
                        self.chunk_ready.emit(wav_bytes)

    def stop(self):
        """
        Shuts down background capturing loops cleanly and joins worker threads.
        """
        self._is_running = False
        self.wait()  # Wait for QThread event loop to end
        if self.mic_thread and self.mic_thread.is_alive():
            self.mic_thread.join(timeout=1.0)
        if self.speaker_thread and self.speaker_thread.is_alive():
            self.speaker_thread.join(timeout=1.0)

    def pause(self):
        """
        Pauses recording aggregation.
        """
        self._is_paused = True

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

    def _record_microphone(self):
        """
        Blocking loop for microphone recording with automatic reconnection on device disconnects.
        """
        samplerate = 16000  # Record natively at target 16kHz mono
        block_duration = 1.0  # Fetch 1-second chunks
        block_size = int(samplerate * block_duration)
        retry_delay = 2.0

        while self._is_running:
            try:
                with sd.InputStream(samplerate=samplerate, channels=1, dtype='float32') as stream:
                    while self._is_running:
                        if self._is_paused:
                            time.sleep(0.2)
                            continue
                        
                        data, overflow = stream.read(block_size)
                        self.mic_queue.put(data.flatten())
            except Exception as e:
                self.warning_logged.emit(f"Microphone Capture Error: {str(e)}")
                # Provide silence fallback while backing off before reconnection attempt
                elapsed = 0.0
                while self._is_running and elapsed < retry_delay:
                    if not self._is_paused:
                        self.mic_queue.put(np.zeros(block_size, dtype=np.float32))
                    time.sleep(1.0)
                    elapsed += 1.0

    def _record_speaker_loopback(self):
        """
        Blocking loop for speaker loopback (WASAPI) with automatic reconnection.
        """
        samplerate = 48000  # Default loopback rate
        block_size = int(samplerate * 1.0)  # 1-second blocks
        retry_delay = 2.0

        while self._is_running:
            try:
                speaker = sc.default_speaker()
                loopback = sc.get_microphone(id=str(speaker.name), include_loopback=True)
                with loopback.recorder(samplerate=samplerate) as recorder:
                    while self._is_running:
                        if self._is_paused:
                            time.sleep(0.2)
                            continue
                        
                        data = recorder.record(numframes=block_size)
                        if data.ndim > 1:
                            data = data.mean(axis=1)
                        self.speaker_queue.put(data.astype(np.float32))
            except Exception as e:
                self.warning_logged.emit(f"WASAPI Speaker Capture Error: {str(e)}")
                # Provide silence fallback while backing off before reconnection attempt
                elapsed = 0.0
                while self._is_running and elapsed < retry_delay:
                    if not self._is_paused:
                        self.speaker_queue.put(np.zeros(block_size, dtype=np.float32))
                    time.sleep(1.0)
                    elapsed += 1.0
