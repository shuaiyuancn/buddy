import sys
import ctypes
from ctypes import wintypes
from PySide6.QtCore import QThread, Signal

# Win32 Hotkey Modifiers
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

# Common Virtual Key Codes
VK_MAP = {
    "right_alt": 0xA5,
    "ralt": 0xA5,
    "alt_r": 0xA5,
    "left_alt": 0xA4,
    "lalt": 0xA4,
    "alt_l": 0xA4,
    "alt": 0x12,
    "ctrl": 0x11,
    "shift": 0x10,
    "space": 0x20,
    "esc": 0x1B,
    "escape": 0x1B,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "backspace": 0x08,
}
# Add F1-F24
for i in range(1, 25):
    VK_MAP[f"f{i}"] = 0x70 + (i - 1)

def parse_hotkey(hotkey_str: str) -> tuple[int, int]:
    """
    Parses a hotkey string (e.g. 'right_alt', 'f9', 'ctrl+shift+d') into
    (modifiers, virtual_key_code). Always sets MOD_NOREPEAT.
    """
    cleaned = hotkey_str.strip().lower()
    modifiers = MOD_NOREPEAT
    vk_code = 0

    if cleaned in VK_MAP:
        return modifiers, VK_MAP[cleaned]

    parts = [p.strip() for p in cleaned.split("+") if p.strip()]
    for part in parts:
        if part in ("ctrl", "control"):
            modifiers |= MOD_CONTROL
        elif part in ("shift",):
            modifiers |= MOD_SHIFT
        elif part in ("alt", "menu"):
            modifiers |= MOD_ALT
        elif part in ("win", "windows", "super", "cmd"):
            modifiers |= MOD_WIN
        elif part in VK_MAP:
            vk_code = VK_MAP[part]
        elif len(part) == 1:
            vk_code = ord(part.upper())

    if vk_code == 0:
        # Default fallback to right alt
        vk_code = 0xA5

    return modifiers, vk_code

class GlobalHotkeyListener(QThread):
    """
    Background worker thread running a Win32 message loop listening for a registered
    global hotkey, emitting the Qt hotkey_triggered signal.
    """
    hotkey_triggered = Signal()

    def __init__(self, hotkey: str = "right_alt", parent=None):
        super().__init__(parent)
        self.hotkey_str = hotkey
        self.modifiers, self.vk = parse_hotkey(hotkey)
        self._thread_id = None
        self._hotkey_id = 1001
        self._is_registered = False

    def run(self):
        if sys.platform != "win32":
            return

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        self._thread_id = kernel32.GetCurrentThreadId()

        # Register global hotkey
        success = user32.RegisterHotKey(
            None,
            self._hotkey_id,
            self.modifiers,
            self.vk
        )
        if not success:
            err = kernel32.GetLastError()
            print(f"[Warning] Failed to register global hotkey '{self.hotkey_str}': error code {err}")
            return

        self._is_registered = True

        msg = wintypes.MSG()
        try:
            # Win32 Message Loop
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                    self.hotkey_triggered.emit()
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if self._is_registered:
                user32.UnregisterHotKey(None, self._hotkey_id)
                self._is_registered = False

    def stop(self):
        """
        Signals the thread to terminate its message loop and waits for exit.
        """
        if self._thread_id and sys.platform == "win32":
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self.wait(2000)
