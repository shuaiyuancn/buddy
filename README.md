# Buddy 🎙️

> **Always-on, passive, windowless background audio transcriber & daily executive summarizer for Windows 10/11.**

Buddy runs silently in the system tray, capturing system loopback audio and microphone input, detecting speech via Voice Activity Detection (VAD), transcribing speech in near real-time via Gemini / Google Cloud Speech-to-Text v2 (Chirp 3), and compiling structured daily Markdown summaries.

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

## 🔄 Automatic & In-App Updates

* **Automatic Background Check**: Buddy checks GitHub Releases every **1 hour** (and 15s after startup). When a new version is released, Buddy automatically downloads the update and performs a seamless atomic process restart.
* **Manual Check**: Right-click the Buddy system tray icon and select **Check for Updates...** at any time.

---

## ⚙️ Configuration

Configuration is stored in `%USERPROFILE%\.buddy\config.json`:

```json
{
    "GEMINI_API_KEY": "YOUR_GEMINI_API_KEY",
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
