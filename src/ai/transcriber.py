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


MODEL_NAME = "gemini-3.5-transcribe"


class TranscriberService:
    """
    Coordinates speech-to-text transcribing via Gemini 3.5 Transcribe with native speaker diarization.
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
        self.gemini_model = MODEL_NAME
        self.vad = VoiceActivityDetector()
        self.appender = FileAppender()

    def is_wav_silent(self, wav_bytes: bytes) -> bool:
        """
        Evaluates whether a WAV audio buffer contains meaningful human speech.
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
        Transcribes an audio chunk using Gemini 3.5 Transcribe.
        """
        if not wav_bytes:
            return ""

        if self.is_wav_silent(wav_bytes):
            return ""

        return self._transcribe_gemini(wav_bytes)

    def _attribute_segments(self, parts: list, wav_bytes: bytes) -> str:
        """
        Attributes diarized segments to speakers ('Me' vs 'Others') by inspecting
        audio energy across stereo channels (Channel 0 = Mic, Channel 1 = Loopback):
        - When loopback audio is present (online call):
          - Speech segments on Channel 0 -> 'Me'
          - Speech segments on Channel 1 -> 'Others' (or 'Others (spk:N)' if multiple remote speakers)
        - When loopback audio is silent (in-person or phone in room):
          - Distinct speakers are labeled 'Speaker 1', 'Speaker 2', etc.
        """
        pcm_data = None
        n_channels = 1
        sample_rate = 16000
        try:
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                n_channels = wf.getnchannels()
                sample_rate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
                pcm_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                if n_channels > 1:
                    pcm_data = pcm_data.reshape(-1, n_channels)
        except Exception:
            pcm_data = None

        # Extract structured segments from candidate parts
        segments = []
        for part in parts:
            p_text = getattr(part, "text", None)
            at = getattr(part, "audio_transcription", None)
            at_text = getattr(at, "text", None) if at else None
            text = (p_text or at_text or "").strip()
            if not text:
                continue

            spk_label = getattr(at, "speaker_label", None) if at else None
            words = getattr(at, "words", None) if at else None
            start_sec = None
            end_sec = None
            if words and len(words) > 0:
                try:
                    s_off = getattr(words[0], "start_offset", "")
                    e_off = getattr(words[-1], "end_offset", "")
                    if s_off:
                        start_sec = float(str(s_off).rstrip("s"))
                    if e_off:
                        end_sec = float(str(e_off).rstrip("s"))
                except Exception:
                    pass

            segments.append({
                "text": text,
                "spk_label": spk_label or "spk:0",
                "start_sec": start_sec,
                "end_sec": end_sec
            })

        if not segments:
            return ""

        if pcm_data is None or n_channels < 2:
            return "\n".join(s["text"] for s in segments)

        total_loop_rms = float(np.sqrt(np.mean(pcm_data[:, 1] ** 2)))
        total_mic_rms = float(np.sqrt(np.mean(pcm_data[:, 0] ** 2)))
        has_loopback = total_loop_rms >= 0.003

        # Classify each segment's origin
        annotated = []
        remote_labels = set()
        for seg in segments:
            text = seg["text"]
            start_sec = seg["start_sec"]
            end_sec = seg["end_sec"]
            spk_label = seg["spk_label"]

            if not has_loopback:
                is_remote = False
            else:
                if start_sec is not None and end_sec is not None:
                    s_idx = max(0, int(start_sec * sample_rate))
                    e_idx = min(len(pcm_data), int(end_sec * sample_rate))
                    slice_pcm = pcm_data[s_idx:e_idx] if e_idx > s_idx else pcm_data
                else:
                    slice_pcm = pcm_data

                mic_rms = float(np.sqrt(np.mean(slice_pcm[:, 0] ** 2)))
                loop_rms = float(np.sqrt(np.mean(slice_pcm[:, 1] ** 2)))
                if loop_rms > mic_rms * 1.1:
                    is_remote = True
                elif mic_rms > loop_rms * 1.1:
                    is_remote = False
                else:
                    is_remote = total_loop_rms > total_mic_rms

            if is_remote:
                remote_labels.add(spk_label)
            annotated.append((is_remote, spk_label, text))

        multiple_remote = len(remote_labels) > 1
        all_spk_labels = {a[1] for a in annotated}
        multiple_room = len(all_spk_labels) > 1 and not has_loopback

        lines = []
        current_speaker = None
        current_texts = []

        for is_remote, spk_label, text in annotated:
            if not has_loopback:
                if multiple_room:
                    spk_idx = sorted(list(all_spk_labels)).index(spk_label) + 1
                    speaker = f"Speaker {spk_idx}"
                else:
                    speaker = "Me"
            else:
                if is_remote:
                    speaker = f"Others ({spk_label})" if multiple_remote else "Others"
                else:
                    speaker = "Me"

            if speaker != current_speaker:
                if current_speaker and current_texts:
                    lines.append(f"{current_speaker}: " + " ".join(current_texts))
                current_speaker = speaker
                current_texts = [text]
            else:
                current_texts.append(text)

        if current_speaker and current_texts:
            lines.append(f"{current_speaker}: " + " ".join(current_texts))

        return "\n".join(lines)

    def _transcribe_gemini(self, wav_bytes: bytes) -> str:
        """
        Sends WAV audio bytes to Gemini 3.5 Transcribe with native speaker diarization.
        """
        if not self.api_key:
            return "[Error: GEMINI_API_KEY environment variable is missing]"

        if not self.client:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                return f"[Error: Failed to initialize Gemini Client: {str(e)}]"

        try:
            config = types.GenerateContentConfig(
                audio_transcription_config=types.AudioTranscriptionConfig(
                    diarization=True
                )
            )

            response = self.client.models.generate_content(
                model=self.gemini_model,
                contents=[
                    types.Part.from_bytes(
                        data=wav_bytes,
                        mime_type="audio/wav"
                    )
                ],
                config=config
            )

            # Extract parts from response
            all_parts = []
            if getattr(response, "candidates", None):
                for candidate in response.candidates:
                    content = getattr(candidate, "content", None)
                    parts = getattr(content, "parts", None) if content else None
                    if parts:
                        all_parts.extend(parts)

            transcribed_text = ""
            if all_parts:
                transcribed_text = self._attribute_segments(all_parts, wav_bytes)

            # Fallback to response.text if candidate parts did not produce text
            if not transcribed_text:
                try:
                    response_text = response.text.strip() if response.text else ""
                except Exception:
                    response_text = ""

                if response_text:
                    if not (response_text.startswith("Me:") or response_text.startswith("Others:") or response_text.startswith("Speaker")):
                        try:
                            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                                if wf.getnchannels() >= 2:
                                    frames = wf.readframes(wf.getnframes())
                                    pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                                    pcm = pcm.reshape(-1, wf.getnchannels())
                                    mic_rms = float(np.sqrt(np.mean(pcm[:, 0] ** 2)))
                                    loop_rms = float(np.sqrt(np.mean(pcm[:, 1] ** 2)))
                                    if loop_rms > mic_rms * 1.2:
                                        response_text = f"Others: {response_text}"
                                    elif mic_rms > loop_rms * 1.2:
                                        response_text = f"Me: {response_text}"
                        except Exception:
                            pass
                    transcribed_text = response_text

            # Log to markdown file
            if transcribed_text:
                self.appender.append_transcription(transcribed_text)
                
            return transcribed_text
        except Exception as e:
            error_msg = f"[Transcription Error: {str(e)}]"
            self.appender.append_transcription(error_msg)
            return error_msg

    def transcribe_dictation(self, wav_bytes: bytes) -> str:
        """
        Transcribes voice dictation audio via Gemini without multi-speaker diarization prefixes.
        Returns the raw transcribed speech text.
        """
        if not wav_bytes:
            return ""

        if self.is_wav_silent(wav_bytes):
            return ""

        if not self.api_key:
            return ""

        if not self.client:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[Warning] Failed to initialize Gemini Client: {e}")
                return ""

        try:
            response = self.client.models.generate_content(
                model=self.gemini_model,
                contents=[
                    types.Part.from_bytes(
                        data=wav_bytes,
                        mime_type="audio/wav"
                    )
                ]
            )

            raw_text = ""
            if getattr(response, "text", None):
                raw_text = response.text.strip()
            elif getattr(response, "candidates", None):
                for candidate in response.candidates:
                    content = getattr(candidate, "content", None)
                    parts = getattr(content, "parts", None) if content else None
                    if parts:
                        for part in parts:
                            p_text = getattr(part, "text", None)
                            if p_text:
                                raw_text += p_text + " "
                raw_text = raw_text.strip()

            # Clean speaker labels if model included any like "Me: ", "Speaker 1: ", "Others: "
            cleaned_lines = []
            for line in raw_text.splitlines():
                line = line.strip()
                if line.startswith("Me:"):
                    line = line[3:].strip()
                elif line.startswith("Others:"):
                    line = line[7:].strip()
                elif line.startswith("Speaker ") and ":" in line[:15]:
                    line = line.split(":", 1)[1].strip()
                if line:
                    cleaned_lines.append(line)

            final_text = "\n".join(cleaned_lines)
            return final_text
        except Exception as e:
            print(f"[Warning] Dictation transcription error: {e}")
            return ""

    def optimize_dictation(self, raw_text: str) -> str:
        """
        Optimizes dictation text for proper formatting, punctuation, capitalization, and fluency.
        Removes speech disfluencies and verbal fillers (um, uh, like) while strictly preserving meaning.
        Falls back to raw_text if an error occurs.
        """
        cleaned = raw_text.strip() if raw_text else ""
        if not cleaned:
            return ""

        if not self.api_key:
            return cleaned

        if not self.client:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception:
                return cleaned

        prompt = (
            "You are an expert voice dictation assistant. "
            "The following text was transcribed from spoken voice dictation. "
            "Optimize it for formatting, grammar, punctuation, and fluency:\n"
            "- Fix spelling, capitalization, and punctuation.\n"
            "- Smooth out awkward speech patterns and remove verbal filler words (e.g., 'um', 'uh', 'you know', 'like').\n"
            "- Format lists, numbers, or paragraph breaks if appropriate.\n"
            "- Strictly preserve the speaker's original meaning, tone, and language (do not translate unless asked).\n"
            "- Return ONLY the final polished text with no surrounding quotes, markdown code fences, conversational preamble, or explanation.\n\n"
            f"Raw dictation:\n{cleaned}"
        )

        try:
            optimizer_model = self.config.get("DICTATION_OPTIMIZER_MODEL", "gemini-2.5-flash")
            response = self.client.models.generate_content(
                model=optimizer_model,
                contents=prompt
            )

            result_text = ""
            if getattr(response, "text", None):
                result_text = response.text.strip()
            elif getattr(response, "candidates", None):
                for candidate in response.candidates:
                    content = getattr(candidate, "content", None)
                    parts = getattr(content, "parts", None) if content else None
                    if parts:
                        for part in parts:
                            p_text = getattr(part, "text", None)
                            if p_text:
                                result_text += p_text
                result_text = result_text.strip()

            # Strip any accidental wrapping markdown code fences ```
            if result_text.startswith("```") and result_text.endswith("```"):
                lines = result_text.splitlines()
                if len(lines) >= 2:
                    result_text = "\n".join(lines[1:-1]).strip()

            return result_text if result_text else cleaned
        except Exception as e:
            print(f"[Warning] Dictation optimization failed, falling back to raw: {e}")
            return cleaned

