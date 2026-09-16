import sys
import time
import ctypes
from ctypes import wintypes
from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import QCoreApplication

class TextInjector:
    """
    Injects text at the current cursor position by setting the system clipboard
    and synthesizing a Ctrl+V paste key sequence.
    """
    @staticmethod
    def _set_clipboard_win32(text: str) -> bool:
        """
        Synchronously and atomically sets text in the Windows OS clipboard via Win32 API.
        Ensures external applications immediately see the updated text upon Ctrl+V.
        """
        if sys.platform != "win32":
            return False

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE

        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalFree.restype = wintypes.HGLOBAL

        # Retry opening clipboard up to 10 times in case another process is briefly holding it
        for _ in range(10):
            if user32.OpenClipboard(None):
                break
            time.sleep(0.005)
        else:
            return False

        try:
            user32.EmptyClipboard()
            encoded = (text + "\0").encode("utf-16le")
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
            if not h_mem:
                return False
            p_mem = kernel32.GlobalLock(h_mem)
            if not p_mem:
                kernel32.GlobalFree(h_mem)
                return False
            ctypes.memmove(p_mem, encoded, len(encoded))
            kernel32.GlobalUnlock(h_mem)
            if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
                kernel32.GlobalFree(h_mem)
                return False
            return True
        finally:
            user32.CloseClipboard()

    @classmethod
    def paste_text(cls, text: str) -> bool:
        if not text:
            return False

        try:
            # 1. Update Windows OS native clipboard synchronously
            win32_ok = cls._set_clipboard_win32(text)

            # 2. Synchronize Qt clipboard cache and pump Qt events
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(text)
            QCoreApplication.processEvents()

            if not win32_ok and clipboard is None:
                return False

            # Allow brief moment for target app message queue to settle
            time.sleep(0.03)

            # 3. Simulate Ctrl+V paste
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
        VK_MENU = 0x12
        VK_LMENU = 0xA4
        VK_RMENU = 0xA5
        KEYEVENTF_KEYUP = 0x0002

        # Ensure any Alt modifier keys (e.g. Right Alt / AltGr) are released
        # so Windows does not interpret Ctrl+V as Ctrl+Alt+V
        for mod_vk in (VK_RMENU, VK_LMENU, VK_MENU):
            user32.keybd_event(mod_vk, 0, KEYEVENTF_KEYUP, 0)

        time.sleep(0.02)

        # Press Ctrl + V, then release
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 0, 0)
        time.sleep(0.01)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
