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
    Coordinates System Tray GUI interactions, context menus, toast notifications,
    and real-time visual status updates (Sleeping, Active, Summarizing, Paused).
    """
    def __init__(self, audio_handler, transcriber_service, updater: AutoUpdater = None):
        super().__init__()
        self.audio_handler = audio_handler
        self.transcriber = transcriber_service
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="buddy_worker")
        self.updater = updater or AutoUpdater(parent=self)

        # Create main System Tray instance
        self.tray = QSystemTrayIcon(self)
        
        # Pre-render state icons
        self.icons = {
            "sleeping": self._draw_tray_icon("sleeping"),
            "active": self._draw_tray_icon("active"),
            "summarizing": self._draw_tray_icon("summarizing"),
            "paused": self._draw_tray_icon("paused"),
        }
        # Backward compatibility properties for tests
        self.active_icon = self.icons["active"]
        self.paused_icon = self.icons["paused"]

        self._current_state = ""
        self.set_status("sleeping")

        # Setup context menu
        self.menu = QMenu()
        self._build_menu()
        self.tray.setContextMenu(self.menu)

        # Connect background warning logging signals to Windows Toast messaging
        self.audio_handler.warning_logged.connect(self.show_warning_notification)
        # Connect audio chunk ready signal to our transcription service
        self.audio_handler.chunk_ready.connect(self.on_audio_chunk_ready)
        # Connect real-time speech activity updates to tray icon states
        if hasattr(self.audio_handler, "speech_activity_changed"):
            self.audio_handler.speech_activity_changed.connect(self._on_speech_activity_changed)

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

    def set_status(self, state: str):
        """
        Updates the tray icon and tooltip based on operational status.
        Supported states: 'sleeping', 'active', 'summarizing', 'paused'.
        """
        if getattr(self.audio_handler, "_is_paused", False) and state != "paused":
            state = "paused"

        if self._current_state == state:
            return

        self._current_state = state
        icon = self.icons.get(state, self.icons["sleeping"])
        self.tray.setIcon(icon)

        tooltips = {
            "sleeping": "Buddy - Sleeping (Waiting for audio)",
            "active": "Buddy - Recording & Transcribing",
            "summarizing": "Buddy - Generating Daily Summary...",
            "paused": "Buddy - Paused",
        }
        self.tray.setToolTip(tooltips.get(state, "Buddy"))

    @Slot(bool)
    def _on_speech_activity_changed(self, is_active: bool):
        """
        Switches between sleeping and active recording states based on real-time audio detection.
        """
        if self._current_state == "summarizing" or getattr(self.audio_handler, "_is_paused", False):
            return
        self.set_status("active" if is_active else "sleeping")

    def _draw_tray_icon(self, state: str | bool) -> QIcon:
        """
        Dynamically renders high-DPI procedural status icons avoiding static image assets.
        States:
        - 'sleeping': Muted slate dot with subtle outer ring.
        - 'active' (or True): Radiant cyan dot with acoustic capture rings.
        - 'summarizing': Radiant violet dot with golden synthesis arcs.
        - 'paused' (or False): Muted slate gray dot with dashed boundary.
        """
        if isinstance(state, bool):
            state = "active" if state else "paused"

        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if state == "active":
            # Radiant cyan central dot with acoustic capture rings
            cyan_color = QColor("#00E5FF")
            painter.setBrush(cyan_color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(9, 9, 14, 14)
            
            # Concentric sound capture wave ring
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(cyan_color, 2, Qt.SolidLine))
            painter.drawEllipse(3, 3, 26, 26)
            
            # Subtle inner aura
            painter.setPen(QPen(QColor(0, 229, 255, 100), 1, Qt.SolidLine))
            painter.drawEllipse(6, 6, 20, 20)

        elif state == "summarizing":
            # Vibrant purple core with golden/amber synthesis arcs
            purple_color = QColor("#A855F7")
            amber_color = QColor("#F59E0B")
            
            painter.setBrush(purple_color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(9, 9, 14, 14)
            
            # Golden synthesis arcs
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(amber_color, 2, Qt.SolidLine))
            painter.drawArc(3, 3, 26, 26, 30 * 16, 120 * 16)
            painter.drawArc(3, 3, 26, 26, 210 * 16, 120 * 16)

        elif state == "paused":
            # Slate gray dot with muted dashed ring
            gray_color = QColor("#94A3B8")
            painter.setBrush(gray_color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(11, 11, 10, 10)
            
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(gray_color, 1.5, Qt.DashLine))
            painter.drawEllipse(4, 4, 24, 24)

        else:  # "sleeping" / default
            # Soft slate/indigo standby dot with muted sleep ring
            slate_color = QColor("#64748B")
            painter.setBrush(slate_color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(10, 10, 12, 12)
            
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#475569"), 1.5, Qt.DotLine))
            painter.drawEllipse(4, 4, 24, 24)
            
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
            self.set_status("active" if getattr(self.audio_handler, "_is_speech_active", False) else "sleeping")
            self.toggle_action.setText("Pause Listening")
            self.tray.showMessage("Buddy Active", "Listening resumed.", QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            self.audio_handler.pause()
            self.set_status("paused")
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
        self.set_status("summarizing")
        self.tray.showMessage("Buddy - Processing", "Compiling your daily summary. Please wait...", QSystemTrayIcon.MessageIcon.Information, 3000)
        
        def process():
            try:
                summary_text = self.transcriber.compile_daily_summary()
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
                self.tray.showMessage("Buddy - Summary Error", str(e), QSystemTrayIcon.MessageIcon.Warning, 5000)
            finally:
                if getattr(self.audio_handler, "_is_paused", False):
                    self.set_status("paused")
                else:
                    self.set_status("active" if getattr(self.audio_handler, "_is_speech_active", False) else "sleeping")

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
