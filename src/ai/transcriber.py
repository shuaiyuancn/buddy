import os
import threading
from datetime import datetime
from pathlib import Path
import google.generativeai as genai
from src.config import TRANSCRIPTS_DIR, SUMMARIES_DIR

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
        if self.api_key:
            genai.configure(api_key=self.api_key)
            
        self.config = config_dict or {}
        self.stt_provider = self.config.get("STT_PROVIDER", "gemini").lower()
        self.gcp_client = None
        
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

    def transcribe_chunk(self, wav_bytes: bytes) -> str:
        """
        Routes the transcription task to the configured speech-to-text provider.
        """
        if not wav_bytes:
            return ""

        if self.stt_provider == "gcp":
            return self._transcribe_gcp(wav_bytes)
        else:
            return self._transcribe_gemini(wav_bytes)

    def _transcribe_gemini(self, wav_bytes: bytes) -> str:
        """
        Sends raw WAV audio bytes to Gemini 2.5 Flash for verbatim speech-to-text.
        """
        if not self.api_key:
            return "[Error: GEMINI_API_KEY environment variable is missing]"

        try:
            audio_part = {
                "mime_type": "audio/wav",
                "data": wav_bytes
            }

            model = genai.GenerativeModel("gemini-2.5-flash")
            
            prompt = (
                "Transcribe the following audio stream. Output ONLY the verbatim speech content. "
                "Do not include any conversational introductions, meta-commentary, or structural headings."
            )
            
            response = model.generate_content([prompt, audio_part])
            
            try:
                transcribed_text = response.text.strip()
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

    def compile_daily_summary(self, date_str: str = None) -> str:
        """
        Compiles the raw daily log into a structured executive report.
        """
        if not self.api_key:
            return "[Error: GEMINI_API_KEY environment variable is missing]"

        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")

        raw_log_content = self.appender.read_raw_log(date_str)
        if not raw_log_content or len(raw_log_content.strip()) < 10:
            return "No transcript logs available to synthesize for this day."

        try:
            model = genai.GenerativeModel("gemini-2.5-pro")
            
            summary_prompt = (
                "You are Buddy, a world-class executive chief of staff and personal assistant.\n"
                f"Analyze the following raw timeline transcript representing a user's day ({date_str}).\n\n"
                "YOUR INSTRUCTIONS:\n"
                "1. Read the transcript from start to finish.\n"
                "2. Detect transitions, verbal meeting demarcations (e.g. \"Buddy, starting the meeting on X\"), and subject changes to divide the day into logical, chronological meeting segments.\n"
                "3. Compile a professional executive overview.\n"
                "4. Extract an 'Action Items & Task Matrix' table detailing tasks, priority, and any mentioned owners.\n"
                "5. Compile an 'Ideas Vault' isolating spontaneous thoughts, brainstorms, or feedback stated in the stream.\n"
                "6. Format the output in a stunning, readable Markdown document.\n\n"
                f"--- RAW DAILY TRANSCRIPT LOGS ---\n{raw_log_content}"
            )

            response = model.generate_content(summary_prompt)
            summary_md = response.text.strip()

            # Save the synthesized report
            summary_path = SUMMARIES_DIR / f"{date_str}_summary.md"
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary_md)

            return summary_md
        except Exception as e:
            return f"[Summarization Error: {str(e)}]"
