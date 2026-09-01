import os
import sys
import threading
import concurrent.futures
import webbrowser
from pathlib import Path
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QMessageBox
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
from PySide6.QtCore import QObject, Slot, Qt
from src.config import TRANSCRIPTS_DIR, SUMMARIES_DIR, APP_VERSION
from src.updater import AutoUpdater

class TrayIconController(QObject):
    """
    Coordinates System Tray GUI interactions, context menus, and toast notifications.
    """
    def __init__(self, audio_handler, transcriber_service, updater: AutoUpdater = None):
        super().__init__()
        self.audio_handler = audio_handler
        self.transcriber = transcriber_service
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="buddy_worker")
        self.updater = updater or AutoUpdater(parent=self)

        # Create main System Tray instance
        self.tray = QSystemTrayIcon(self)
        
        # Draw and apply initial active icon
        self.active_icon = self._draw_tray_icon(is_active=True)
        self.paused_icon = self._draw_tray_icon(is_active=False)
        self.tray.setIcon(self.active_icon)
        self.tray.setToolTip("Buddy - Listening...")

        # Setup context menu
        self.menu = QMenu()
        self._build_menu()
        self.tray.setContextMenu(self.menu)

        # Connect background warning logging signals to Windows Toast messaging
        self.audio_handler.warning_logged.connect(self.show_warning_notification)
        # Connect audio chunk ready signal to our transcription service
        self.audio_handler.chunk_ready.connect(self.on_audio_chunk_ready)

        # Connect Auto-Updater signals
        self.updater.update_available.connect(self._on_update_available)
        self.updater.update_started.connect(self._on_update_started)
        self.updater.update_completed.connect(self._on_update_completed)
        self.updater.update_error.connect(self.show_warning_notification)
        self.updater.check_finished.connect(self._on_check_finished)

    def show(self):
        """
        Launches the system tray, starts the auto-updater, and triggers the initial startup notification.
        """
        self.tray.show()
        self.updater.start()
        self.tray.showMessage(
            "Buddy Active",
            "Buddy is running silently in the background and listening.",
            QSystemTrayIcon.MessageIcon.Information,
            5000
        )

    def _draw_tray_icon(self, is_active: bool) -> QIcon:
        """
        Dynamically renders an elegant tray icon programmatically, avoiding static assets.
        """
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if is_active:
            # High-end cyan dot
            color = QColor("#00E5FF")
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(8, 8, 16, 16)
            
            # Subtle external ring representing the microphone/loopback sound capture
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#00E5FF"), 2, Qt.SolidLine))
            painter.drawEllipse(3, 3, 26, 26)
        else:
            # Sleek slate gray dot
            color = QColor("#78909C")
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(10, 10, 12, 12)
            
            # Muted external dashed ring
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#78909C"), 1, Qt.DashLine))
            painter.drawEllipse(5, 5, 22, 22)
            
        painter.end()
        return QIcon(pixmap)

    def _build_menu(self):
        """
        Assembles menu options.
        """
        self.toggle_action = self.menu.addAction("Pause Listening")
        self.toggle_action.triggered.connect(self.on_toggle_listening)

        self.menu.addSeparator()

        summarize_action = self.menu.addAction("Generate Daily Summary")
        summarize_action.triggered.connect(self.on_generate_summary)

        open_transcripts_action = self.menu.addAction("Open Transcripts Folder")
        open_transcripts_action.triggered.connect(self.on_open_transcripts_folder)

        open_summaries_action = self.menu.addAction("Open Summaries Folder")
        open_summaries_action.triggered.connect(self.on_open_summaries_folder)

        self.menu.addSeparator()

        check_update_action = self.menu.addAction(f"Check for Updates... (v{APP_VERSION})")
        check_update_action.triggered.connect(self.on_check_for_updates)

        self.menu.addSeparator()

        exit_action = self.menu.addAction("Exit")
        exit_action.triggered.connect(self.on_exit)

    @Slot()
    def on_toggle_listening(self):
        """
        Handles pausing and resuming the continuous audio queues.
        """
        if self.audio_handler._is_paused:
            self.audio_handler.resume()
            self.tray.setIcon(self.active_icon)
            self.tray.setToolTip("Buddy - Listening...")
            self.toggle_action.setText("Pause Listening")
            self.tray.showMessage("Buddy Active", "Listening resumed.", QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            self.audio_handler.pause()
            self.tray.setIcon(self.paused_icon)
            self.tray.setToolTip("Buddy - Paused")
            self.toggle_action.setText("Resume Listening")
            self.tray.showMessage("Buddy Paused", "Listening suspended.", QSystemTrayIcon.MessageIcon.Information, 2000)

    def _safe_transcribe(self, wav_bytes: bytes):
        """
        Executes transcription in worker pool and surfaces warnings if errors occur.
        """
        try:
            result = self.transcriber.transcribe_chunk(wav_bytes)
            if result and result.startswith("[Error:"):
                self.audio_handler.warning_logged.emit(result)
        except Exception as e:
            self.audio_handler.warning_logged.emit(f"Transcription Error: {str(e)}")

    @Slot()
    def on_audio_chunk_ready(self, wav_bytes: bytes):
        """
        Triggered asynchronously whenever a 60-second sliding buffer completes.
        Dispatches transcription work safely to the thread pool.
        """
        if hasattr(self, "executor") and self.executor is not None:
            self.executor.submit(self._safe_transcribe, wav_bytes)

    @Slot()
    def on_generate_summary(self):
        """
        Gathers raw logs and compiles the final summary using the worker thread pool.
        """
        self.tray.setToolTip("Buddy - Compiling Summary...")
        self.tray.showMessage("Buddy - Processing", "Compiling your daily summary. Please wait...", QSystemTrayIcon.MessageIcon.Information, 3000)
        
        def process():
            try:
                summary_text = self.transcriber.compile_daily_summary()
                self.tray.setToolTip("Buddy - Listening...")
                
                if "Error" in summary_text or "No transcript logs" in summary_text:
                    self.tray.showMessage("Buddy - Summary Failed", summary_text, QSystemTrayIcon.MessageIcon.Warning, 5000)
                else:
                    self.tray.showMessage(
                        "Buddy - Summary Completed",
                        "Your daily summary markdown has been saved successfully!",
                        QSystemTrayIcon.MessageIcon.Information,
                        5000
                    )
                    # Open summaries folder in Explorer
                    self.on_open_summaries_folder()
            except Exception as e:
                self.tray.setToolTip("Buddy - Listening...")
                self.tray.showMessage("Buddy - Summary Error", str(e), QSystemTrayIcon.MessageIcon.Warning, 5000)

        if hasattr(self, "executor") and self.executor is not None:
            self.executor.submit(process)

    @Slot()
    def on_open_transcripts_folder(self):
        """
        Opens transcripts directory in Windows explorer.
        """
        if TRANSCRIPTS_DIR.exists():
            os.startfile(str(TRANSCRIPTS_DIR))

    @Slot()
    def on_open_summaries_folder(self):
        """
        Opens summaries directory in Windows explorer.
        """
        if SUMMARIES_DIR.exists():
            os.startfile(str(SUMMARIES_DIR))

    @Slot(str)
    def show_warning_notification(self, text: str):
        """
        Pops a standard system tray bubble warning message.
        """
        self.tray.showMessage(
            "Buddy - Warning",
            text,
            QSystemTrayIcon.MessageIcon.Warning,
            4000
        )

    @Slot()
    def on_check_for_updates(self):
        """
        Manually triggers a check for new releases on GitHub.
        """
        self.tray.showMessage(
            "Buddy - Update Check",
            f"Checking GitHub ({self.updater.repo}) for newer releases...",
            QSystemTrayIcon.MessageIcon.Information,
            3000
        )
        self.updater.check_for_updates_async(manual=True)

    @Slot(bool, str)
    def _on_check_finished(self, update_found: bool, message: str):
        """
        Handles manual check result notification.
        """
        if not update_found:
            self.tray.showMessage(
                "Buddy - Updates",
                message,
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )

    @Slot(str, str)
    def _on_update_available(self, version_tag: str, download_url: str):
        """
        Notifies user of newly found version.
        """
        self.tray.showMessage(
            "Buddy - Update Available",
            f"A new version (v{version_tag}) is available. Downloading update in background...",
            QSystemTrayIcon.MessageIcon.Information,
            5000
        )

    @Slot(str)
    def _on_update_started(self, version_tag: str):
        """
        Updates tooltip during active binary download.
        """
        self.tray.setToolTip(f"Buddy - Downloading v{version_tag}...")

    @Slot(str)
    def _on_update_completed(self, version_tag: str):
        """
        Notifies user that update is ready and will restart.
        """
        self.tray.showMessage(
            "Buddy - Update Ready",
            f"v{version_tag} downloaded successfully. Restarting Buddy...",
            QSystemTrayIcon.MessageIcon.Information,
            4000
        )

    @Slot()
    def on_exit(self):
        """
        Cleanly stops background streams, flushes worker threads, and exits the application.
        """
        self.updater.stop()
        self.audio_handler.stop()
        self.tray.hide()
        if hasattr(self, "executor") and self.executor is not None:
            self.executor.shutdown(wait=True, cancel_futures=False)
        sys.exit(0)
