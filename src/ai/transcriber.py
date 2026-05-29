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
    Coordinates speech-to-text transcribing and end-of-day summary compilation via Gemini.
    """
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            
        self.appender = FileAppender()

    def transcribe_chunk(self, wav_bytes: bytes) -> str:
        """
        Sends raw WAV audio bytes to Gemini 1.5 Flash for verbatim speech-to-text.
        """
        if not self.api_key:
            return "[Error: GEMINI_API_KEY environment variable is missing]"
        if not wav_bytes:
            return ""

        try:
            # Inline audio part dictionary (under 20 MB, which our 60s wav files certainly are)
            audio_part = {
                "mime_type": "audio/wav",
                "data": wav_bytes
            }

            model = genai.GenerativeModel("gemini-1.5-flash")
            
            prompt = (
                "Transcribe the following audio stream. Output ONLY the verbatim speech content. "
                "Do not include any conversational introductions, meta-commentary, or structural headings."
            )
            
            response = model.generate_content([prompt, audio_part])
            transcribed_text = response.text.strip()
            
            # Log to markdown file
            if transcribed_text:
                self.appender.append_transcription(transcribed_text)
                
            return transcribed_text
        except Exception as e:
            error_msg = f"[Transcription Error: {str(e)}]"
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
            model = genai.GenerativeModel("gemini-1.5-pro")
            
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
