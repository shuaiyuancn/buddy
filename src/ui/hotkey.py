import sys
import time
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
    "altgr": 0xA5,
    "alt_gr": 0xA5,
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

STANDALONE_MODIFIERS = {0xA5, 0xA4, 0xA3, 0xA2, 0xA1, 0xA0, 0x12, 0x11, 0x10}

def parse_hotkey(hotkey_str: str) -> tuple[int, int]:
    """
    Parses a hotkey string (e.g. 'right_alt', 'altgr', 'f9', 'ctrl+shift+d') into
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
    Background worker thread listening for a global hotkey, emitting the Qt hotkey_triggered signal.
    Uses Win32 RegisterHotKey with an automatic GetAsyncKeyState edge-detection fallback
    for standalone modifiers (e.g. Right Alt / AltGr) or when RegisterHotKey returns error 1409.
    """
    hotkey_triggered = Signal()

    def __init__(self, hotkey: str = "right_alt", parent=None):
        super().__init__(parent)
        self.hotkey_str = hotkey
        self.modifiers, self.vk = parse_hotkey(hotkey)
        self._thread_id = None
        self._hotkey_id = 1001
        self._is_registered = False
        self._is_running = True

    def run(self):
        if sys.platform != "win32":
            return

        self._is_running = True

        # Standalone modifier keys (like Right Alt / AltGr) cannot be reliably registered
        # via RegisterHotKey in Windows, so we directly use the low-overhead GetAsyncKeyState loop.
        if self.vk in STANDALONE_MODIFIERS:
            self._run_async_key_loop()
            return

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        self._thread_id = kernel32.GetCurrentThreadId()

        # Try registering global hotkey
        success = user32.RegisterHotKey(
            None,
            self._hotkey_id,
            self.modifiers,
            self.vk
        )
        if not success:
            err = kernel32.GetLastError()
            print(f"[Info] RegisterHotKey unavailable for '{self.hotkey_str}' (code {err}). Falling back to GetAsyncKeyState.")
            self._run_async_key_loop()
            return

        self._is_registered = True

        msg = wintypes.MSG()
        try:
            # Win32 Message Loop
            while self._is_running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                    self.hotkey_triggered.emit()
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if self._is_registered:
                user32.UnregisterHotKey(None, self._hotkey_id)
                self._is_registered = False

    def _run_async_key_loop(self):
        """
        Polls the hardware key state every 20ms using GetAsyncKeyState.
        Triggers on leading edge (key transition from up to down) with zero perceptible CPU overhead.
        """
        user32 = ctypes.windll.user32
        was_pressed = False

        check_ctrl = bool(self.modifiers & MOD_CONTROL)
        check_shift = bool(self.modifiers & MOD_SHIFT)
        check_alt = bool(self.modifiers & MOD_ALT)
        check_win = bool(self.modifiers & MOD_WIN)

        while self._is_running:
            key_down = bool(user32.GetAsyncKeyState(self.vk) & 0x8000)

            if key_down:
                mod_ok = True
                if check_ctrl and not (user32.GetAsyncKeyState(0x11) & 0x8000):
                    mod_ok = False
                if check_shift and not (user32.GetAsyncKeyState(0x10) & 0x8000):
                    mod_ok = False
                if check_alt and not (user32.GetAsyncKeyState(0x12) & 0x8000):
                    mod_ok = False
                if check_win and not ((user32.GetAsyncKeyState(0x5B) | user32.GetAsyncKeyState(0x5C)) & 0x8000):
                    mod_ok = False

                if mod_ok:
                    if not was_pressed:
                        was_pressed = True
                        self.hotkey_triggered.emit()
                else:
                    was_pressed = False
            else:
                was_pressed = False

            time.sleep(0.02)

    def stop(self):
        """
        Signals the thread to terminate and waits for exit.
        """
        self._is_running = False
        if self._thread_id and sys.platform == "win32":
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self.wait(2000)
