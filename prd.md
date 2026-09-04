# Product Requirements Document (PRD)
## Project Name: Buddy
**Version:** 1.5.0  
**Status:** Implemented & Released  
**Target Platform:** Windows 10/11 (x64)

---

## 1. Executive Summary & Product Vision

For professionals juggling back-to-back virtual meetings, spontaneous brainstorms, and ongoing work conversations, manual note-taking is a constant friction point.

**Buddy** is a passive, always-on background audio transcriber for Windows 10 and 11. Operating silently in the system tray, it continuously listens to both the user's microphone ("Me") and system speaker loopback audio ("Others"), separating and attributing speaker voices automatically.

Buddy records sliding audio buffers (30–60s), filters out silent buffers using high-performance Voice Activity Detection (VAD), transcribes active speech via Gemini 2.5 Flash (or GCP Speech-to-Text v2 / Chirp 3), and instantly appends timestamped entries to a local, human-readable **Markdown (`.md`)** raw transcript log.

---

## 2. Core Features & Capabilities

### F01: Dual-Channel Audio Capture & Speaker Attribution
*   **Description:** Buddy continuously records sound simultaneously from physical microphone input ("Me") and Windows WASAPI loopback speaker audio ("Others") without requiring virtual audio cables.
*   **Channel Mapping:**
    *   **Left Channel:** Hardware Microphone ("Me").
    *   **Right Channel:** WASAPI System Loopback ("Others" / meeting attendees / remote speakers).
*   **Requirements:**
    *   Unified, synchronized background recording stream.
    *   Stereo standardization (16 kHz, 16-bit PCM WAV).
    *   Gemini multi-modal prompt instructs the model to tag speaker dialogue distinctly (e.g., `[Me]` vs `[Others]`).

### F02: Smart Voice Activity Detection (VAD) & Silence Filtering
*   **Description:** Buddy checks both audio channels for genuine voice activity before dispatching network requests.
*   **Requirements:**
    *   Frame-based RMS energy and Zero Crossing Rate (ZCR) analysis across 30ms sub-frames.
    *   Short acoustic click and continuous background noise rejection.
    *   Pure silence chunks skip API calls entirely, conserving network bandwidth and API quota.

### F03: Continuous Direct-to-Markdown Transcript Logging
*   **Description:** Rather than storing large audio recordings on disk, Buddy transcribes sliding audio windows and writes text directly to a local Markdown log.
*   **Requirements:**
    *   **Log Storage Path:** Saved in the user's home directory:  
        `%USERPROFILE%\.buddy\transcripts\YYYY-MM-DD_raw.md`
    *   **Format:**
        ```markdown
        ### [14:22:15]
        **[Me]:** Hey team, let's review the deployment pipeline architecture.
        **[Others]:** Sounds good, we just merged the latest pull request.
        ```
    *   **Crash Resilience:** Appending directly to disk ensures that even during unexpected power loss, all transcripts up to the last chunk are preserved.

### F04: Smart Pause & Auto-Resume
*   **Description:** Provides manual pause and scheduled auto-resume for evening/night workflow convenience.
*   **Requirements:**
    *   **Pause Listening:** Immediately toggles recording suspension and resumes on demand.
    *   **Pause Until 8:00 AM Tomorrow:** Calculates duration until 8:00:00 AM the next day, suspends audio capture, and sets a high-precision timer to automatically resume listening the next morning.
    *   Manual resume cancels any scheduled timer and resumes listening immediately.

### F05: In-App & Background Auto-Updater
*   **Description:** Automatic background checking, downloading, and atomic process restart for seamless updates from GitHub Releases.
*   **Requirements:**
    *   Hourly periodic background update checks via GitHub Releases API.
    *   Manual **Check for Updates...** tray action.
    *   Real-time download progress tracking with byte counts and percentage in the tray tooltip (`Buddy - Downloading update... 45% (37.4/83.0 MB)`).
    *   Detached PowerShell restart worker for atomic replacement of `Buddy.exe` on Windows.

---

## 3. User Interface & User Experience (UI/UX)

Buddy is designed to be 100% passive with **no main window interface**:

### 3.1. Dynamic System Tray Status Indicators
*   ⚪ **Sleeping**: Standby mode, monitoring for speech activity.
*   🔵 **Active**: Real-time voice activity detected, recording and transcribing.
*   🟡 **Paused**: Audio capture suspended (manual or scheduled until 8am).

### 3.2. Context Menu Actions
*   `Resume / Pause Listening`
*   `Pause Until 8:00 AM Tomorrow`
*   `Open Transcripts Folder` (Opens `%USERPROFILE%\.buddy\transcripts\`)
*   `Check for Updates...` (Manually triggers GitHub release check & background download)
*   `Exit`

### 3.3. Native Windows Notifications
*   Startup notification: *"Buddy is running silently in the background and listening."*
*   Scheduled pause: *"Listening paused. Auto-resume scheduled for tomorrow at 08:00:00."*
*   Update notifications for available releases, download start, and restart readiness.

---

## 4. Sequence & Data Flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Mic as Hardware Mic (Me)
    participant Loop as WASAPI Loopback (Others)
    participant App as Buddy Background Engine
    participant VAD as Voice Activity Detector
    participant API as Gemini 2.5 Flash / GCP Chirp 3
    participant Log as YYYY-MM-DD_raw.md

    User->>App: Start App (System Tray)
    activate App
    App->>Mic: Start mic capture thread
    App->>Loop: Start loopback capture thread
    
    loop Sliding Window Capture (e.g. 60 seconds)
        Mic-->>App: Mic PCM samples
        Loop-->>App: Loopback PCM samples
        App->>App: Mix down to stereo (L=Me, R=Others)
        App->>VAD: Analyze RMS & ZCR speech activity
        alt Pure Silence / Noise
            VAD-->>App: Silence detected
            App->>App: Discard chunk, skip API call
        else Speech Present
            VAD-->>App: Speech confirmed
            App->>API: Send stereo WAV bytes with speaker attribution prompt
            API-->>App: Return formatted transcript with [Me] / [Others] tags
            App->>Log: Append Timestamp & text block to daily Markdown file
        end
    end
    deactivate App
```

---

## 5. Security & Privacy

1.  **Zero Audio Retention:** Audio chunks exist only in-memory in short-lived sliding buffers. No audio files are written to disk.
2.  **Plain-Text Transparency:** Transcripts are saved locally in plaintext Markdown (`%USERPROFILE%\.buddy\transcripts\`), allowing easy inspection, editing, or deletion.
3.  **Encrypted Credential Storage:** API keys are protected in the Windows Credential Manager or local configuration file (`%USERPROFILE%\.buddy\config.json`).
