"""Bring the browser window back when it is minimized.

A minimized window makes CDP screenshot and click calls hang or return empty
frames, and the page keeps reporting itself as visible, so the real window
state has to be asked for.
"""

import ctypes
from ctypes import wintypes

_user32 = ctypes.windll.user32

SW_RESTORE = 9
SW_SHOW = 5

_EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

_user32.IsWindow.argtypes = [wintypes.HWND]
_user32.IsWindow.restype = wintypes.BOOL
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.IsIconic.restype = wintypes.BOOL
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextLengthW.restype = ctypes.c_int
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.restype = ctypes.c_int
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowRect.restype = wintypes.BOOL
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD


def _top_windows():
    found = []

    def callback(hwnd, _lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rect = wintypes.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
        found.append((hwnd, pid.value, buf.value, area))
        return True

    _user32.EnumWindows(_EnumProc(callback), 0)
    return found


class Restorer:
    def __init__(self, pid=None, titles=('yuketang', '雨课堂', 'Chrome', 'Edge')):
        self.pid = pid
        self.titles = titles
        self.hwnd = None

    def _find(self):
        if self.hwnd and _user32.IsWindow(self.hwnd):
            return self.hwnd
        windows = _top_windows()
        if self.pid:
            mine = [w for w in windows if w[1] == self.pid]
            if mine:
                mine.sort(key=lambda w: -w[3])
                self.hwnd = mine[0][0]
                return self.hwnd
        for hwnd, _pid, title, _area in sorted(windows, key=lambda w: -w[3]):
            low = (title or '').lower()
            if any(t.lower() in low for t in self.titles):
                self.hwnd = hwnd
                return hwnd
        return None

    def restore(self):
        hwnd = self._find()
        if not hwnd:
            return False
        try:
            if not _user32.IsIconic(hwnd):
                return True
            _user32.ShowWindow(hwnd, SW_RESTORE)
            _user32.ShowWindow(hwnd, SW_SHOW)
            _user32.SetForegroundWindow(hwnd)
            return True
        except Exception:
            return False
