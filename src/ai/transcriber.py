import os
import io
import wave
import threading
from datetime import datetime
from pathlib import Path
import numpy as np
from google import genai
from google.genai import types
from src.config import TRANSCRIPTS_DIR
from src.audio.vad import VoiceActivityDetector

class FileAppender:
    """
    Thread-safe, append-only file writer for writing raw markdown transcripts.
    """
    def __init__(self, target_directory: Path = TRANSCRIPTS_DIR):
        self.directory = target_directory
        self._lock = threading.Lock()

    def append_transcription(self, text: str) -> Path:
        """
        Safely appends a timestamped text block to the current day's raw markdown file.
        Args:
            text (str): The transcribed text block.
        Returns:
            Path: The path to the active raw transcript log.
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        timestamp_str = datetime.now().strftime("%H:%M:%S")
        file_path = self.directory / f"{date_str}_raw.md"

        cleaned_text = text.strip()
        if not cleaned_text:
            return file_path

        # Write inside a mutual exclusion block (thread safety)
        with self._lock:
            # Check if file is empty or newly created, add a title if so
            is_new = not file_path.exists() or file_path.stat().st_size == 0
            
            with open(file_path, "a", encoding="utf-8") as f:
                if is_new:
                    f.write(f"# Buddy Raw Transcript Log - {date_str}\n")
                
                f.write(f"\n### [{timestamp_str}]\n{cleaned_text}\n")
        
        return file_path

    def read_raw_log(self, date_str: str = None) -> str:
        """
        Reads the contents of the raw transcript log for a specific date.
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        file_path = self.directory / f"{date_str}_raw.md"

        if not file_path.exists():
            return ""

        with self._lock:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()


class TranscriberService:
    """
    Coordinates speech-to-text transcribing and end-of-day summary compilation via Gemini/GCP STT.
    """
    def __init__(self, api_key: str = None, config_dict: dict = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[Warning] Failed to initialize Gemini Client: {e}")
            
        self.config = config_dict or {}
        self.stt_provider = self.config.get("STT_PROVIDER", "gemini").lower()
        self.gemini_model = self.config.get("GEMINI_MODEL", "gemini-3.5-transcribe")
        self.gcp_client = None
        self.vad = VoiceActivityDetector()
        
        if self.stt_provider == "gcp":
            self._init_gcp_client()

        self.appender = FileAppender()

    def _init_gcp_client(self):
        """
        Thread-safe dynamic import and initialization of Google Cloud Speech Client.
        """
        try:
            from google.cloud.speech_v2 import SpeechClient
            from google.api_core.client_options import ClientOptions
            
            # Programmatically register local service account key path if specified
            sa_path = self.config.get("GCP_SERVICE_ACCOUNT_KEY_PATH")
            if sa_path:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_path
                
            region = self.config.get("GCP_REGION", "us")
            self.gcp_client = SpeechClient(
                client_options=ClientOptions(
                    api_endpoint=f"{region}-speech.googleapis.com"
                )
            )
        except Exception as e:
            print(f"[Warning] Failed to initialize Google Cloud Speech Client: {e}")

    def is_wav_silent(self, wav_bytes: bytes) -> bool:
        """
        Evaluates whether a WAV audio buffer (Mono or Stereo) contains meaningful human speech.
        Returns True if the buffer is silent/empty, False if speech is detected.
        """
        if not wav_bytes or len(wav_bytes) <= 44:
            return False
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                n_channels = wf.getnchannels()
                frames = wf.readframes(wf.getnframes())
                pcm_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                if n_channels > 1:
                    pcm_data = pcm_data.reshape(-1, n_channels)
                if len(pcm_data) < 1600:  # less than 100ms
                    return False
                return not self.vad.is_speech_present(pcm_data, sample_rate=16000)
        except Exception:
            return False

    def transcribe_chunk(self, wav_bytes: bytes) -> str:
        """
        Routes the transcription task to the configured speech-to-text provider.
        """
        if not wav_bytes:
            return ""

        if self.is_wav_silent(wav_bytes):
            return ""

        if self.stt_provider == "gcp":
            return self._transcribe_gcp(wav_bytes)
        else:
            return self._transcribe_gemini(wav_bytes)

    def _transcribe_gemini(self, wav_bytes: bytes) -> str:
        """
        Sends dual-channel WAV audio bytes to Gemini for speaker-attributed verbatim speech-to-text.
        """
        if not self.api_key:
            return "[Error: GEMINI_API_KEY environment variable is missing]"

        if not self.client:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                return f"[Error: Failed to initialize Gemini Client: {str(e)}]"

        try:
            prompt = (
                "You are an expert speech-to-text transcriber for a dual-channel audio stream:\n"
                "- Channel 1 (Left Channel): 'Me' (the local user's microphone)\n"
                "- Channel 2 (Right Channel): 'Others' (remote meeting participants / system audio)\n\n"
                "INSTRUCTIONS:\n"
                "1. Transcribe the dialogue in strict chronological order.\n"
                "2. Attribute each spoken phrase with the appropriate speaker label based on the audio channel:\n"
                "   - 'Me: <spoken content>' for speech originating on Channel 1 (Left).\n"
                "   - 'Others: <spoken content>' for speech originating on Channel 2 (Right).\n"
                "3. If only one party is speaking, output only their attributed dialogue.\n"
                "4. Output ONLY the attributed verbatim dialogue. Do not include introductory notes, timestamps, structural headers, or conversational commentary."
            )
            
            response = self.client.models.generate_content(
                model=self.gemini_model,
                contents=[
                    prompt,
                    types.Part.from_bytes(
                        data=wav_bytes,
                        mime_type="audio/wav"
                    )
                ]
            )
            
            try:
                transcribed_text = response.text.strip() if response.text else ""
            except Exception:
                transcribed_text = ""
            
            # Log to markdown file
            if transcribed_text:
                self.appender.append_transcription(transcribed_text)
                
            return transcribed_text
        except Exception as e:
            error_msg = f"[Transcription Error: {str(e)}]"
            self.appender.append_transcription(error_msg)
            return error_msg

    def _transcribe_gcp(self, wav_bytes: bytes) -> str:
        """
        Sends raw WAV audio bytes to GCP Speech-to-Text V2 using the Chirp-3 model.
        """
        if not self.gcp_client:
            self._init_gcp_client()
            if not self.gcp_client:
                return "[Error: Google Cloud Speech Client is not initialized]"

        try:
            from google.cloud.speech_v2.types import cloud_speech
            
            project_id = self.config.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
            if not project_id:
                return "[Error: GCP_PROJECT_ID is missing from config]"
                
            region = self.config.get("GCP_REGION", "us")
            languages = self.config.get("GCP_LANGUAGES", ["zh-CN", "en-US"])
            
            config = cloud_speech.RecognitionConfig(
                auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                language_codes=languages,
                model="chirp_3",
            )
            
            request = cloud_speech.RecognizeRequest(
                recognizer=f"projects/{project_id}/locations/{region}/recognizers/_",
                config=config,
                content=wav_bytes,
            )
            
            response = self.gcp_client.recognize(request=request)
            
            transcripts = []
            for result in response.results:
                if result.alternatives:
                    transcripts.append(result.alternatives[0].transcript)
            transcribed_text = " ".join(transcripts).strip()
            
            # Log to markdown file
            if transcribed_text:
                self.appender.append_transcription(transcribed_text)
                
            return transcribed_text
        except Exception as e:
            error_msg = f"[Transcription Error (GCP): {str(e)}]"
            self.appender.append_transcription(error_msg)
            return error_msg
