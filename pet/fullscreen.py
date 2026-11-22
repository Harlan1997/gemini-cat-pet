"""Windows fullscreen application detector using native Win32 APIs (zero extra deps)."""

import ctypes
from ctypes import wintypes
import os
import sys

# Desktop / shell window classes that cover the full screen but are NOT fullscreen apps
_SHELL_CLASSES = {
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow",
    "ApplicationFrameWindow",  # handled carefully only if not actually covering monitor
}

_DESKTOP_ONLY_CLASSES = {
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
}

if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _shell32 = ctypes.windll.shell32

    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", _RECT),
            ("rcWork", _RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetClassNameW.restype = ctypes.c_int
    _user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.MonitorFromWindow.restype = wintypes.HMONITOR
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    _user32.GetMonitorInfoW.restype = wintypes.BOOL
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongW.restype = wintypes.LONG

    _MONITOR_DEFAULTTONEAREST = 2
    _QUNS_BUSY = 2
    _QUNS_RUNNING_D3D_FULL_SCREEN = 3
    _QUNS_PRESENTATION_MODE = 4
    _MY_PID = os.getpid()


def is_fullscreen_on_widget_monitor(widget_hwnd: int) -> bool:
    """Return True if another application is fullscreen on the same monitor as widget_hwnd."""
    if sys.platform != "win32":
        return False

    try:
        fg = _user32.GetForegroundWindow()
        if not fg or fg == widget_hwnd:
            return False

        # Never trigger on our own process windows (e.g. pet, bubble, settings dialog)
        pid = wintypes.DWORD(0)
        _user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
        if pid.value == _MY_PID:
            return False

        # Ignore Windows desktop & taskbar shell surfaces
        cls_buf = ctypes.create_unicode_buffer(128)
        _user32.GetClassNameW(fg, cls_buf, 128)
        cls_name = cls_buf.value
        if cls_name in _DESKTOP_ONLY_CLASSES:
            return False

        # Check monitor match: only hide if the fullscreen app is on the pet's monitor
        pet_mon = _user32.MonitorFromWindow(wintypes.HWND(widget_hwnd), _MONITOR_DEFAULTTONEAREST)
        fg_mon = _user32.MonitorFromWindow(wintypes.HWND(fg), _MONITOR_DEFAULTTONEAREST)
        if pet_mon and fg_mon and pet_mon != fg_mon:
            return False

        # 1. Check Direct3D exclusive fullscreen / presentation mode via Shell API
        quns = ctypes.c_int(0)
        if _shell32.SHQueryUserNotificationState(ctypes.byref(quns)) == 0:
            if quns.value in (_QUNS_RUNNING_D3D_FULL_SCREEN, _QUNS_PRESENTATION_MODE):
                return True

        # 2. Check if the foreground window covers the entire monitor bounds (borderless / browser video / F11)
        win_rect = _RECT()
        if not _user32.GetWindowRect(fg, ctypes.byref(win_rect)):
            return False

        mon_info = _MONITORINFO()
        mon_info.cbSize = ctypes.sizeof(_MONITORINFO)
        if not _user32.GetMonitorInfoW(fg_mon, ctypes.byref(mon_info)):
            return False

        mr = mon_info.rcMonitor
        wr = mon_info.rcWork
        mon_w = mr.right - mr.left
        mon_h = mr.bottom - mr.top
        if mon_w <= 0 or mon_h <= 0:
            return False

        tol = 2
        covers_monitor = (
            win_rect.left <= mr.left + tol
            and win_rect.top <= mr.top + tol
            and win_rect.right >= mr.right - tol
            and win_rect.bottom >= mr.bottom - tol
        )
        if not covers_monitor:
            return False

        # Distinguish maximized normal window (stops at taskbar) vs true fullscreen (covers taskbar)
        # If taskbar is visible (work area smaller than monitor), a normal maximized window won't cover mr;
        # if taskbar is auto-hidden (rcWork == rcMonitor), also check WS_CAPTION absence (borderless/F11).
        if (
            wr.left == mr.left
            and wr.top == mr.top
            and wr.right == mr.right
            and wr.bottom == mr.bottom
        ):
            style = _user32.GetWindowLongW(fg, -16)  # GWL_STYLE
            ws_caption = 0x00C00000
            if (style & ws_caption) == ws_caption:
                return False

        return True
    except Exception:
        return False
