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

Because we removed complex keyboard hotkeys and floating UI panels, our dependencies are significantly simplified:

| Library / Package | Version | Purpose |
| :--- | :--- | :--- |
| **`PySide6`** | `>= 6.6.0` | Provides the native Windows system tray icon, context menus, settings panels, and standard Windows toast notification hooks. |
| **`soundcard`** | `>= 0.4.3` | Binds directly to Windows WASAPI for loopback speaker recording. |
| **`PyAudio`** / **`sounddevice`** | `>= 0.2.14` | Handles physical hardware microphone input capture. |
| **`soundfile`** | `>= 0.12.1` | Formats and handles writing mixed sliding audio chunks into in-memory bytes or temporary WAV formats for the transcription API. |
| **`google-generativeai`** | `>= 0.4.0` | Official Google GenAI Python SDK for connecting to Gemini API (or other transcription interfaces). |
| **`google-cloud-speech`**| `>= 2.25.0` | (Optional) Dynamic client bindings for GCP Speech-to-Text v2 API and the premium Chirp 3 model. |
| **`keyring`** | `>= 24.3.0` | Securely queries and writes credentials to the native Windows Credential Manager (to store the user's Gemini API Key). |
| **`pyinstaller`** | `>= 6.3.0` | Standalone bundle compiler to compile our background Python scripts into a single, console-less `.exe` file. |

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

### Step 3.2: Install Streamlined Dependencies
```powershell
# Upgrade pip to latest version
python -m pip install --upgrade pip

# Install required packages (standard)
pip install PySide6 soundcard soundfile sounddevice google-generativeai keyring pyinstaller

# (Optional) Install GCP Speech-to-Text v2 dependencies if using gcp provider
pip install google-cloud-speech
```

---

## 4. Simplified Directory Layout

Our modular project directory structure is clean and easy to maintain:

```
c:\workspace\buddy\
│
├── .venv/                      # Active Python Virtual Environment
├── assets/                     # Tray icons and media
│   └── app_icon.ico            # Main system tray icon
│
├── src/                        # Source Directory
│   ├── __init__.py
│   ├── main.py                 # Application Entry Point & Tray Loop
│   ├── config.py               # Key storage and keyring manager
│   │
│   ├── audio/                  # Stream Capturing Core
│   │   ├── __init__.py
│   │   ├── stream_handler.py   # Continuous WASAPI recording thread
│   │   └── mixer.py            # Mixing/resampling mic & speaker buffers
│   │
│   ├── ui/                     # System Tray Components
│   │   ├── __init__.py
│   │   ├── tray_icon.py        # System tray menu and Windows toast hooks
│   │   └── settings_dialog.py  # Small, native Qt panel to set API Key
│   │
│   └── ai/                     # Gemini Integrations
│       ├── __init__.py
│       └── transcriber.py      # Micro-buffer transcription & prompt summaries
│
├── build-env.md                # Updated Environment and compilation instructions
├── prd.md                      # Updated Product Requirements Document
├── requirements.txt            # Python requirements manifest
└── .gitignore                  # Git Ignore configuration
```

---

## 5. Storage Directory Structure (~/.buddy)

Rather than storing files internally inside the project sandbox, Buddy saves all logs and configuration files to the user's hidden home directory, ensuring they are clean, centralized, and persistent:

```
C:\Users\<Username>\.buddy\
│
├── config.json                 # Local configuration file
│
├── transcripts\                # Continuous Raw Markdown Logs
│   ├── 2026-05-29_raw.md       # Raw, chronological Markdown transcript
│   └── 2026-05-30_raw.md
│
└── summaries\                  # Synthesized Daily Markdown Reports
    ├── 2026-05-29_summary.md   # Segmented daily digest & action items
    └── 2026-05-30_summary.md
```

### Expanded config.json Options
To support high-accuracy multilingual Speech-to-Text via the **Chirp 3** model, your `~/.buddy/config.json` can be configured with the following options:
```json
{
    "GEMINI_API_KEY": "AIzaSy...",
    "STT_PROVIDER": "gcp",
    "GCP_PROJECT_ID": "your-gcp-project-id",
    "GCP_REGION": "us",
    "GCP_SERVICE_ACCOUNT_KEY_PATH": "C:\\path\\to\\your\\service-account-key.json",
    "GCP_LANGUAGES": ["zh-CN", "en-US"]
}
```
*   `"STT_PROVIDER"`: Set to `"gcp"` to enable GCP Speech-to-Text, or `"gemini"` (default) to use Gemini 2.5 Flash for transcription.
*   `"GCP_PROJECT_ID"`: Your active Google Cloud Platform Project ID.
*   `"GCP_REGION"`: The regional endpoint to run Speech V2 recognition. (Defaults to `"us"`; `"us"` and `"eu"` support Chirp 3).
*   `"GCP_SERVICE_ACCOUNT_KEY_PATH"`: Absolute path to your GCP service account JSON key file containing transcription credentials. If empty, the SDK falls back to the `GOOGLE_APPLICATION_CREDENTIALS` environment variable.
*   `"GCP_LANGUAGES"`: List of languages for multi-lingual automatic detection (e.g., Chinese mixed with English).

---

## 6. Local Development Execution

To run Buddy with debugging console printouts enabled:
```powershell
# Activate venv
.venv\Scripts\Activate.ps1

# Execute core entry file
python src/main.py
```

---

## 7. Packaging for Production

When packaging the finalized version of Buddy as a lightweight, background Windows taskbar application, compile using PyInstaller with the console window disabled (`--noconsole` / `--windowed`):

```powershell
.venv\Scripts\pyinstaller --clean Buddy.spec
```
This compiles the streamlined standalone binary `Buddy.exe` inside the `dist/` directory utilizing the configured `Buddy.spec` profile.

---

## 8. Google Cloud Speech-to-Text v2 Integration & Chirp 3 Setup

To use the state-of-the-art **Chirp 3** multilingual model for your transcription engine:

### Step 8.1: Enable the API in GCP Console
1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Select your project or create a new one.
3. Search for the **Cloud Speech-to-Text API** in the API library and enable it.

### Step 8.2: Create a Service Account & Download Key
1. Go to **IAM & Admin > Service Accounts**.
2. Click **Create Service Account**, name it (e.g., `buddy-stt`), and assign it the **Speech-to-Text Administrator** role (or standard client roles).
3. Select the created Service Account, click the **Keys** tab, click **Add Key > Create new key** (JSON format).
4. Download the generated `.json` key file and store it safely in your user folder (e.g., `C:\Users\<Username>\.buddy\gcp-credentials.json`).

### Step 8.3: Configure Buddy
Edit your local configuration file `~/.buddy/config.json` with your project information:
```json
{
    "GEMINI_API_KEY": "AIzaSy...",
    "STT_PROVIDER": "gcp",
    "GCP_PROJECT_ID": "your-gcp-project-id",
    "GCP_REGION": "us",
    "GCP_SERVICE_ACCOUNT_KEY_PATH": "C:\\Users\\<Username>\\.buddy\\gcp-credentials.json",
    "GCP_LANGUAGES": ["zh-CN", "en-US"]
}
```
*Buddy is now fully prepared to transcribe mixed speech with industry-leading precision!*
