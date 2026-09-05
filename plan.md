# Buddy Development Tracker (plan.md)

This file tracks the development progress and milestone achievements of **Buddy** - your passive, stream-first Windows AI assistant.

---

## 📋 Implementation Checklist

- [x] **Task 1: Directory Setup & Configuration Initialization**
    - [x] Create core project directory structures (`src/audio/`, `src/ui/`, `src/ai/`).
    - [x] Implement `src/config.py` for API key checks (with native Windows toast error on failure).
- [x] **Task 2: Asynchronous Audio Capture & Mixing Engine**
    - [x] Implement `src/audio/mixer.py` for anti-aliased resampling and normalizations.
    - [x] Implement `src/audio/stream_handler.py` for WASAPI speaker loopback and mic capture.
- [x] **Task 3: Live Transcriber Service & Markdown Logging**
    - [x] Implement `src/ai/transcriber.py` to route audio buffers to Gemini 2.5 Flash / GCP Speech-to-Text.
    - [x] Build thread-safe file appender routines writing directly to `%USERPROFILE%\.buddy\transcripts\YYYY-MM-DD_raw.md`.
- [x] **Task 4: System Tray GUI & Notification Controller**
    - [x] Implement `src/ui/tray_icon.py` using PySide6.
    - [x] Add menu controls: Resume/Pause, Open Transcripts Folder, Check for Updates, Exit.
- [x] **Task 5: Main Orchestrator Integration**
    - [x] Implement `src/main.py` to coordinate configuration, audio capturing loops, and GUI controls.
- [x] **Task 6: Verification & End-to-End Validation**
    - [x] Build comprehensive 44-test automated test suite validating thread safety, audio resampling, VAD, tray actions, and updater.
- [x] **Task 7: Directory Relocation (~/.buddy/) & config.json Fallback**
    - [x] Relocate transcripts to `~/.buddy/transcripts/`.
    - [x] Implement local file `~/.buddy/config.json` configuration fallback and auto-generation with warning exit toast.
- [x] **Task 8: Voice Activity Detection (VAD) & Pure Silence Optimization**
    - [x] Implement `src/audio/vad.py` with multi-channel RMS energy and Zero-Crossing Rate analysis.
    - [x] Skip routing/sending to the Gemini API if the chunk is pure silence or sub-threshold background noise.
- [x] **Task 9: Dual-Channel Speaker Attribution ("Me" vs "Others")**
    - [x] Map physical microphone to Left channel and WASAPI loopback to Right channel in stereo WAV output.
    - [x] Formulate Gemini multi-modal prompt to output attributed dialogues with `[Me]` and `[Others]` tags.
- [x] **Task 10: Dynamic System Tray Status Indicators**
    - [x] Procedural icon rendering for ⚪ Sleeping, 🔵 Active (speech detected), and 🟡 Paused states.
    - [x] Live speech activity signal binding between audio stream worker and tray controller.
- [x] **Task 11: Smart Pause (Auto-Resume at 8:00 AM Tomorrow)**
    - [x] Add "Pause Until 8:00 AM Tomorrow" tray action.
    - [x] Schedule single-shot Qt timer for next 8:00:00 AM and auto-resume audio capture.
    - [x] Cancel timer on manual toggle.
- [x] **Task 12: Streamlined Real-Time Transcription Focus**
    - [x] Remove legacy batch daily summary generation across transcriber, config, UI, and tests.
- [x] **Task 13: In-App & Background Auto-Updater**
    - [x] Implement `src/updater.py` with GitHub Releases API integration.
    - [x] Hourly background checking and manual "Check for Updates..." triggering.
    - [x] Real-time download progress feedback (`%` and `MB`) in tray tooltip.
    - [x] Atomic binary replacement via detached PowerShell restart worker.
- [x] **Task 14: Automated CI/CD & One-Liner Installer**
    - [x] GitHub Actions workflow building and releasing `Buddy.exe` on tag push.
    - [x] Windows PowerShell one-liner installer (`install.ps1`).
- [x] **Task 15: Gemini 3.5 Transcribe Integration & Model Config**
    - [x] Add configurable `"GEMINI_MODEL": "gemini-3.5-transcribe"` in `config.json` and `load_full_config()`.
    - [x] Update `TranscriberService` to use dynamic Gemini model.
    - [x] Add unit tests for default `gemini-3.5-transcribe` and custom override.
    - [x] Update all repository documentation.

