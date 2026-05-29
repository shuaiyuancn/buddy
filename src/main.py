import sys
import signal
from PySide6.QtWidgets import QApplication
from src.config import check_api_key_or_toast_and_exit
from src.audio.stream_handler import AudioStreamHandler
from src.ai.transcriber import TranscriberService
from src.ui.tray_icon import TrayIconController

def main():
    # 1. Enforce windowless API Key check. Aborts and fires Windows toast notification if missing.
    api_key = check_api_key_or_toast_and_exit()

    # 2. Initialize main Qt Application loop
    app = QApplication(sys.argv)
    
    # CRITICAL: Prevent the background app from closing when sub-dialogs or browser pages are closed
    app.setQuitOnLastWindowClosed(False)

    # 3. Instantiate underlying services
    print("[Buddy] Initializing Gemini Transcriber Service...")
    transcriber = TranscriberService(api_key=api_key)

    print("[Buddy] Initializing Threaded Audio Capture Engine...")
    audio_handler = AudioStreamHandler(target_sr=16000, window_duration_sec=60)

    print("[Buddy] Constructing System Tray Interface...")
    tray_controller = TrayIconController(
        audio_handler=audio_handler,
        transcriber_service=transcriber
    )

    # 4. Bind signal interrupt handlers to exit cleanly from CLI commands (Ctrl+C)
    def signal_handler(sig, frame):
        print("\n[Buddy] Termination signal received. Shutting down background loops...")
        audio_handler.stop()
        app.quit()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 5. Start background recording threads
    print("[Buddy] Launching active audio streams...")
    audio_handler.start()

    # 6. Reveal the tray icon and trigger active startup toast
    tray_controller.show()

    # Run execution loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
