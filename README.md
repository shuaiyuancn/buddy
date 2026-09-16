# Buddy 🎙️

> **Always-on, passive, windowless background audio transcriber with dual-channel speaker attribution for Windows 10/11.**

Buddy runs silently in the system tray, capturing microphone input ("Me") and speaker loopback audio ("Others"), detecting speech via Voice Activity Detection (VAD), and transcribing speech with native speaker diarization via Gemini 3.5 Transcribe into timestamped daily Markdown logs.

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
4. Create a Windows Startup shortcut (`Buddy.lnk` in Startup folder) for auto-start on login.
5. Add `%LOCALAPPDATA%\Buddy\` to your user `PATH`.
6. Launch Buddy in the background.

---

## 🎙️ System Tray & Controls

* **Dynamic Status Indicators**:
  * <img src="assets/icons/icon_sleeping.png" width="16" height="16" alt="Sleeping" /> **Sleeping**: Standby mode, monitoring for speech.
  * <img src="assets/icons/icon_active.png" width="16" height="16" alt="Active" /> **Active**: Real-time audio recording & transcription.
  * <img src="assets/icons/icon_dictating.png" width="16" height="16" alt="Dictating" /> **Dictating**: Dictation mode active, capturing your voice.
  * <img src="assets/icons/icon_paused.png" width="16" height="16" alt="Paused" /> **Paused**: Listening suspended.
* **Smart Dictation Mode**:
  * **Global Hotkey**: Press **Right Alt** (configurable via `DICTATION_HOTKEY`) to start dictation mode. Normal background recording is paused.
  * **Auto-Type at Cursor**: Press the hotkey again when done speaking. Buddy transcribes your speech with Gemini, optimizes the text for fluency, punctuation, and clarity (stripping verbal fillers like "um" and "uh"), and automatically types/pastes it directly into your active window at the cursor position.
  * **Recent Dictations History**: The 5 most recent dictation transcripts are accessible via the tray icon submenu. Clicking any transcript copies it immediately to your clipboard.
* **Smart Pause**:
  * **Pause Listening**: Instantly suspend or resume audio capture.
  * **Pause Until 8:00 AM Tomorrow**: Convenient scheduled pause for evening/night work, automatically resuming at 8:00 AM the next morning.
* **Transcripts Access**: Click **Open Transcripts Folder** to view daily markdown logs saved in `%USERPROFILE%\.buddy\transcripts\`.
* **Auto-Start on Login**: Toggle **Start on Windows Login** directly from the tray menu to automatically launch Buddy when you log in.
* **Automatic Background Updates**: Buddy checks GitHub Releases hourly and updates seamlessly. You can also manually check via **Check for Updates...**.

---

## ⚙️ Configuration

Configuration is stored in `%USERPROFILE%\.buddy\config.json`:

```json
{
    "GEMINI_API_KEY": "YOUR_GEMINI_API_KEY",
    "GEMINI_MODEL": "gemini-3.5-transcribe",
    "GITHUB_REPO": "shuaiyuancn/buddy",
    "AUTO_UPDATE": true,
    "UPDATE_CHECK_INTERVAL_HOURS": 1,
    "AUTO_START": true,
    "DICTATION_HOTKEY": "right_alt"
}
```

* **STT Engine**: Powered exclusively by Google's native audio-language transcription model `gemini-3.5-transcribe` with hardware-level dual-channel diarization.
* `DICTATION_HOTKEY`: Global hotkey to toggle dictation mode (default `"right_alt"`, supports combinations like `"ctrl+shift+d"` or function keys like `"f9"`).
* `AUTO_START`: Whether Buddy launches automatically when Windows starts (default `true`).
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
