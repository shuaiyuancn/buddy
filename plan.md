# Buddy Development Tracker (plan.md)

This file tracks the real-time development progress of **Buddy** - your passive, stream-first Windows AI assistant.

---

## 📋 Implementation Checklist

- [x] **Task 1: Directory Setup & Configuration Initialization**
    - [x] Create core project directory structures (`src/audio/`, `src/ui/`, `src/ai/`).
    - [x] Implement `src/config.py` for API key checks (with native Windows toast error on failure).
- [x] **Task 2: Asynchronous Audio Capture & Mixing Engine**
    - [x] Implement `src/audio/mixer.py` for normalizations.
    - [x] Implement `src/audio/stream_handler.py` for WASAPI speaker loopback and mic capture.
- [x] **Task 3: Live Transcriber Service & Markdown Logging**
    - [x] Implement `src/ai/transcriber.py` to route 60s audio buffers directly to Gemini 1.5 Flash.
    - [x] Build file appender routines writing directly to `%USERPROFILE%\.buddy\transcripts\YYYY-MM-DD_raw.md`.
- [x] **Task 4: System Tray GUI & Notification Controller**
    - [x] Implement `src/ui/tray_icon.py` using PySide6.
    - [x] Add menu controls: Resume/Pause, Generate Summary, Open Logs, Settings, Exit.
- [x] **Task 5: Main Orchestrator Integration**
    - [x] Implement `src/main.py` to coordinate configuration, audio capturing loops, and GUI controls.
- [x] **Task 6: Verification & End-to-End Validation**
    - [x] Run a test suite validating thread safety, API upload stability, and markdown log formatting.
    - [x] Run a local test execute verifying background running loop.
- [x] **Task 7: Directory Relocation (~/.buddy/) & config.json Fallback**
    - [x] Relocate transcripts and summaries to `~/.buddy/transcripts/` and `~/.buddy/summaries/`.
    - [x] Implement local file `~/.buddy/config.json` configuration fallback and auto-generation with warning exit toast.
    - [x] Verify complete TDD automated test coverage and execution.

