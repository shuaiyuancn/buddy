# Buddy 🎙️

> **Always-on, passive, windowless background audio transcriber with dual-channel speaker attribution for Windows 10/11.**

Buddy runs silently in the system tray, capturing microphone input ("Me") and speaker loopback audio ("Others"), detecting speech via Voice Activity Detection (VAD), and transcribing speech in near real-time via Gemini 3.5 Transcribe / Google Cloud Speech-to-Text v2 (Chirp 3) into timestamped daily Markdown logs.

---

## ⚡ Quick Start (One-Liner Installation)

Install the latest version of Buddy directly from GitHub Releases via Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/shuaiyuancn/buddy/master/install.ps1 | iex
```

The installer will:
1. Fetch the latest `Buddy.exe` release from GitHub.
2. Install the binary to `%LOCALAPPDATA%\Buddy\`.
3. Create a Start Menu shortcut (`Buddy`).
4. Add `%LOCALAPPDATA%\Buddy\` to your user `PATH`.
5. Launch Buddy in the background.

---

## 🎙️ System Tray & Controls

* **Dynamic Status Indicators**:
  * ⚪ **Sleeping**: Standby mode, monitoring for speech.
  * 🔵 **Active**: Real-time audio recording & transcription.
  * 🟡 **Paused**: Listening suspended.
* **Smart Pause**:
  * **Pause Listening**: Instantly suspend or resume audio capture.
  * **Pause Until 8:00 AM Tomorrow**: Convenient scheduled pause for evening/night work, automatically resuming at 8:00 AM the next morning.
* **Transcripts Access**: Click **Open Transcripts Folder** to view daily markdown logs saved in `%USERPROFILE%\.buddy\transcripts\`.
* **Automatic Background Updates**: Buddy checks GitHub Releases hourly and updates seamlessly. You can also manually check via **Check for Updates...**.

---

## ⚙️ Configuration

Configuration is stored in `%USERPROFILE%\.buddy\config.json`:

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

* **STT Models & Configuration**:
  * `GEMINI_MODEL`: Model used for Gemini STT (defaults to `"gemini-3.5-transcribe"`, with support for `"gemini-2.5-flash"`, `"gemini-3.7-flash"`, etc.).
  * `STT_PROVIDER`: Set to `"gemini"` (default) or `"gcp"` (for GCP Speech-to-Text Chirp 3).
* **API Key Options**:
  * Put `GEMINI_API_KEY` in `%USERPROFILE%\.buddy\config.json`
  * Set `GEMINI_API_KEY` environment variable
  * Store securely in Windows Credential Manager under service `Buddy` and username `GEMINI_API_KEY`

---

## 🛠️ Development & Building

### Running from source
```powershell
# Create & activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run test suite
python -m pytest -v

# Run application
python run.py
```

### Packaging Single-File Executable
```powershell
pyinstaller Buddy.spec --noconfirm
```
Output executable is generated at `dist/Buddy.exe`.

---

## 🚀 GitHub Actions CI/CD

Pushing a git tag (e.g. `v0.1.0`) automatically builds `Buddy.exe` on Windows and creates a published GitHub Release:

```powershell
git tag v0.1.0
git push origin v0.1.0
```
