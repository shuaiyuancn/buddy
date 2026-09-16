import sys
import time
import ctypes
from PySide6.QtGui import QGuiApplication

class TextInjector:
    """
    Injects text at the current cursor position by setting the system clipboard
    and synthesizing a Ctrl+V paste key sequence.
    """
    @classmethod
    def paste_text(cls, text: str) -> bool:
        if not text:
            return False

        try:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(text)
            else:
                return False

            # Allow brief moment for clipboard to settle
            time.sleep(0.05)

            cls._simulate_paste()
            return True
        except Exception as e:
            print(f"[Warning] Failed to inject text at cursor: {e}")
            return False

    @classmethod
    def _simulate_paste(cls):
        """
        Synthesizes Ctrl+V key combination to paste text from clipboard.
        """
        if sys.platform != "win32":
            return

        user32 = ctypes.windll.user32
        VK_CONTROL = 0x11
        VK_V = 0x56
        KEYEVENTF_KEYUP = 0x0002

        # Press Ctrl + V, then release
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 0, 0)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
