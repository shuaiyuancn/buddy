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
  * **Auto-Type at Cursor**: Press the hotkey again when done speaking. Buddy rewrites what you said into concise, clear, professional text with Gemini (it is not a word-for-word transcript): fillers, repetitions and false starts go, self-corrections are applied, lists become `•` bullets on separate lines, and Chinese, English or mixed speech stays in the language you used. The result is pasted at the cursor in your active window.
  * **Muted Mic Warning**: If the microphone records only silence, Buddy tells you straight away instead of returning nothing.
  * **Recent Dictations History**: The 5 most recent dictation transcripts are accessible via the tray icon submenu. Clicking any transcript copies it immediately to your clipboard.
  * **Dictation History**: Every dictation is also saved to `%USERPROFILE%\.buddy\dictations\YYYY-MM-DD.md`, with the model used and how long it took.
  * **Works While Paused**: Dictation still works when background listening is paused.
* **Smart Pause**:
  * **Pause Listening**: Instantly suspend or resume audio capture.
  * **Pause Until 8:00 AM Tomorrow**: Convenient scheduled pause for evening/night work, automatically resuming at 8:00 AM the next morning.
* **Microphone & Speaker Selection**: The **Microphone** and **Speaker** submenus list connected devices. **System default** (the default) follows Windows, including a headset you plug in; picking a device pins it. If a pinned device is unplugged, Buddy uses the system default until it comes back.
* **Transcripts Access**: Click **Open Transcripts Folder** to view daily markdown logs saved in `%USERPROFILE%\.buddy\transcripts\`.
* **Logs**: Errors and activity (startup, audio devices, transcription, each dictation step) go to `%USERPROFILE%\.buddy\logs\buddy.log`, which rolls over at 1 MB and keeps 3 older files.
* **Auto-Start on Login**: Toggle **Start on Windows Login** directly from the tray menu to automatically launch Buddy when you log in.
* **Automatic Background Updates**: Buddy checks GitHub Releases hourly and updates seamlessly. You can also manually check via **Check for Updates...**.
* **Single Instance**: Only one Buddy runs per Windows session. Launching it again (Start Menu, login autostart, installer) shows an "already running" notification and exits.

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
    "DICTATION_HOTKEY": "right_alt",
    "DICTATION_MODEL": "gemini-3.1-flash-lite",
    "DICTATION_THINKING_LEVEL": ""
}
```

* **STT Engine**: Powered exclusively by Google's native audio-language transcription model `gemini-3.5-transcribe` with hardware-level dual-channel diarization.
* `DICTATION_HOTKEY`: Global hotkey to toggle dictation mode (default `"right_alt"`, supports combinations like `"ctrl+shift+d"` or function keys like `"f9"`).
* `DICTATION_MODEL`: Gemini model for dictation. The default `"gemini-3.1-flash-lite"` takes about 3.5s and keeps facts intact best among the fast models on an English, Chinese and mixed-language test set. For the highest accuracy use `"gemini-3.8-flash"`, which takes about twice as long. See [docs/dictation-model-evaluation.md](docs/dictation-model-evaluation.md) for how models were compared and how to re-run the comparison.
* `DICTATION_THINKING_LEVEL`: Optional thinking level for the dictation model, e.g. `"minimal"` with `"gemini-3.5-flash"`. Leave empty to use the model's default.
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
