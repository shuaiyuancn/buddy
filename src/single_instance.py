import os
import sys

# Session-local named mutex: one Buddy per logged-in user session.
MUTEX_NAME = "Local\\Buddy-SingleInstance-Mutex"
ERROR_ALREADY_EXISTS = 183

# Keep the handle referenced for the lifetime of the process. Windows releases
# the mutex automatically when the process exits (including os._exit and kills),
# so the auto-updater's relaunch after the old PID dies is never blocked.
_mutex_handle = None


def acquire_single_instance_lock(name: str = MUTEX_NAME) -> bool:
    """
    Attempts to claim the process-wide single-instance lock.
    Returns True if this is the only running instance, False if another Buddy already holds it.
    Fails open (returns True) on non-Windows platforms or if the mutex cannot be created.
    """
    global _mutex_handle
    if os.name != "nt":
        return True
    if _mutex_handle is not None:
        return True

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateMutexW(None, False, name)
        last_error = ctypes.get_last_error()
    except Exception as e:
        print(f"[Warning] Single-instance check unavailable: {e}", file=sys.stderr)
        return True

    if not handle:
        print(f"[Warning] CreateMutexW failed (error {last_error}); skipping single-instance check.", file=sys.stderr)
        return True

    if last_error == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False

    _mutex_handle = handle
    return True


def release_single_instance_lock():
    """
    Releases the single-instance lock held by this process, if any.
    """
    global _mutex_handle
    if _mutex_handle is None or os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(_mutex_handle)
    _mutex_handle = None
