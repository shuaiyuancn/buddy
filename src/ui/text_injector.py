import sys
import time
import logging
import ctypes
from ctypes import wintypes
from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import QCoreApplication
from src.ui.hotkey import send_menu_mask

def foreground_app_name() -> str:
    """
    Executable name of the window that currently has focus (e.g. 'chrome.exe'), for the log.
    Only the process name is recorded, never the window title, which can contain private text.
    """
    if sys.platform != "win32":
        return "unknown"
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "none"
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return f"pid {pid.value}"
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = wintypes.DWORD(len(buf))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return buf.value.rsplit("\\", 1)[-1]
            return f"pid {pid.value}"
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return "unknown"


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
            logging.getLogger("buddy.dictation").exception(f"Failed to inject text at cursor: {e}")
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
        VK_LMENU = 0xA4
        VK_RMENU = 0xA5
        KEYEVENTF_KEYUP = 0x0002

        # If an Alt key (e.g. the Right Alt hotkey) is still physically held, release it so Windows
        # does not interpret Ctrl+V as Ctrl+Alt+V. Only release keys that are actually down: a stray
        # Alt key-up can itself activate the target app's menu bar and swallow the paste.
        held_alt = [vk for vk in (VK_RMENU, VK_LMENU) if user32.GetAsyncKeyState(vk) & 0x8000]
        if held_alt:
            send_menu_mask()
            for mod_vk in held_alt:
                user32.keybd_event(mod_vk, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)

        # Press Ctrl + V, then release
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 0, 0)
        time.sleep(0.01)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
