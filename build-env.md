# Development & Runtime Environment Specification
## Project Name: Buddy
**Target Platform:** Windows 10 / 11 (x86_64)  
**Development Stack:** Python 3.11+ / PySide6 (Qt System Tray) / WASAPI Core Audio

---

## 1. System Prerequisites

Ensure your Windows system meets these foundational prerequisites:
1.  **Python 3.11.x (or 3.12.x):** Standard installation added to your user/system `PATH`.
2.  **Windows C++ Build Tools (PortAudio Prerequisite):**
    *   Install the Visual Studio Build Tools via the [Visual Studio Installer](https://visualstudio.microsoft.com/visual-build-tools/).
    *   Select the **Desktop development with C++** workload (required to compile certain low-level audio bindings like `pyaudio` if precompiled binary wheels are not used).
3.  **Active Audio Hardware:** Audio playback device (Speakers/Headphones) and an active input capture device (Microphone).

---

## 2. Dependency Matrix & Libraries

| Library / Package | Version | Purpose |
| :--- | :--- | :--- |
| **`PySide6`** | `>= 6.6.0` | Native Windows system tray icon, context menus, and Qt event loop / timer management. |
| **`soundcard`** | `>= 0.4.3` | Direct Windows WASAPI loopback speaker recording. |
| **`sounddevice`** | `>= 0.4.6` | Hardware microphone input capture. |
| **`soundfile`** | `>= 0.12.1` | Formats sliding stereo audio chunks into in-memory WAV formats for the transcription API. |
| **`scipy`** / **`numpy`** | `>= 1.11.0` | Digital signal processing: anti-aliasing Chebyshev filters and frame-based VAD analysis. |
| **`google-genai`** | `>= 0.1.1` | Official modern Google GenAI SDK for Gemini 3.5 Transcribe & Gemini 2.5 Flash transcription. |
| **`google-cloud-speech`**| `>= 2.25.0` | (Optional) Dynamic client bindings for GCP Speech-to-Text v2 API and Chirp 3 model. |
| **`keyring`** | `>= 24.3.0` | Securely queries and writes credentials to the Windows Credential Manager. |
| **`requests`** | `>= 2.31.0` | Hourly GitHub Releases checking and chunked binary update downloading. |
| **`packaging`** | `>= 23.0` | Semantic version parsing and release comparison for the auto-updater. |
| **`pyinstaller`** | `>= 6.3.0` | Standalone bundle compiler to compile Buddy into a single, console-less `.exe`. |

---

## 3. Step-by-Step Environment Setup

Follow these commands in PowerShell to initialize your local development environment inside the workspace.

### Step 3.1: Create & Activate Virtual Environment
```powershell
# Navigate to the project directory
cd c:\workspace\buddy

# Initialize Python virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\Activate.ps1
```

### Step 3.2: Install Dependencies
```powershell
# Upgrade pip to latest version
python -m pip install --upgrade pip

# Install required packages
pip install -r requirements.txt
```

---

## 4. Simplified Directory Layout

```
c:\workspace\buddy\
│
├── .venv/                      # Active Python Virtual Environment
├── assets/                     # Tray icons and media
│   └── app_icon.ico            # Main application icon
│
├── src/                        # Source Directory
│   ├── __init__.py
│   ├── main.py                 # Application Entry Point & Orchestrator
│   ├── config.py               # Key storage and config.json manager
│   ├── version.py              # Single source of truth for version (__version__)
│   ├── updater.py              # Auto-updater with GitHub Releases API & process restart
│   │
│   ├── audio/                  # Stream Capturing Core
│   │   ├── __init__.py
│   │   ├── stream_handler.py   # Continuous dual WASAPI recording threads
│   │   ├── mixer.py            # Anti-aliased resampling & stereo channel mapping
│   │   └── vad.py              # Frame-based Voice Activity Detection (RMS & ZCR)
│   │
│   ├── ui/                     # System Tray Components
│   │   ├── __init__.py
│   │   └── tray_icon.py        # Dynamic status icons, smart pause & updater hooks
│   │
│   └── ai/                     # Speech-to-Text Integrations
│       ├── __init__.py
│       └── transcriber.py      # Dual-channel Gemini 3.5 Transcribe & GCP Chirp 3 transcriber
│
├── tests/                      # Full Automated Pytest Suite (46 tests)
├── Buddy.spec                  # PyInstaller build specification
├── install.ps1                 # One-liner PowerShell installer script
├── requirements.txt            # Python requirements manifest
└── README.md                   # User documentation
```

---

## 5. Storage Directory Structure (~/.buddy)

Buddy saves all logs and configuration files to the user's hidden home directory:

```
C:\Users\<Username>\.buddy\
│
├── config.json                 # Local configuration file
│
└── transcripts\                # Continuous Daily Markdown Logs
    ├── 2026-05-29_raw.md       # Raw, chronological Markdown transcript
    └── 2026-05-30_raw.md
```

### Full config.json Options
```json
{
    "GEMINI_API_KEY": "YOUR_GEMINI_API_KEY",
    "GEMINI_MODEL": "gemini-3.5-transcribe",
    "STT_PROVIDER": "gemini",
    "GCP_PROJECT_ID": "",
    "GCP_REGION": "us",
    "GCP_SERVICE_ACCOUNT_KEY_PATH": "",
    "GCP_LANGUAGES": ["zh-CN", "en-US"],
    "GITHUB_REPO": "shuaiyuancn/buddy",
    "AUTO_UPDATE": true,
    "UPDATE_CHECK_INTERVAL_HOURS": 1
}
```
*   `"GEMINI_API_KEY"`: API key for Google Gemini transcription.
*   `"GEMINI_MODEL"`: Model used for Gemini transcription (default `"gemini-3.5-transcribe"`, with support for `"gemini-2.5-flash"`, `"gemini-3.7-flash"`, etc.).
*   `"STT_PROVIDER"`: Set to `"gemini"` (default) or `"gcp"` for GCP Speech-to-Text v2.
*   `"GCP_PROJECT_ID"`: Google Cloud Project ID (if using GCP STT).
*   `"GCP_REGION"`: Regional endpoint (e.g. `"us"`).
*   `"GCP_SERVICE_ACCOUNT_KEY_PATH"`: Absolute path to GCP service account JSON key file.
*   `"GCP_LANGUAGES"`: Language codes for multi-lingual speech recognition (e.g., `["zh-CN", "en-US"]`).
*   `"GITHUB_REPO"`: GitHub repository (`"owner/repo"`) for checking releases and downloading updates.
*   `"AUTO_UPDATE"`: Set to `true` to enable automatic background checks and downloads.
*   `"UPDATE_CHECK_INTERVAL_HOURS"`: Interval in hours between background update checks (default `1`).

---

## 6. Local Development Execution & Testing

```powershell
# Run automated test suite
pytest -v

# Run application from source
python run.py
```

---

## 7. Packaging & Releases

```powershell
# Package single-file standalone executable
pyinstaller Buddy.spec --noconfirm
```
Output executable is generated at `dist/Buddy.exe`.

Pushing a git tag (`git tag v0.1.6 ; git push origin master --tags`) automatically triggers the GitHub Actions CI/CD workflow to build and release `Buddy.exe`.
