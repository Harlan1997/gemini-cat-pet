"""Lightweight Windows foreground-app, background-music, and battery watcher via Win32 APIs."""

import ctypes
from ctypes import wintypes
import os
import sys
import time
from dataclasses import dataclass

if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _TH32CS_SNAPPROCESS = 0x00000002

    class _PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    class _SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_byte),
            ("BatteryFlag", ctypes.c_byte),
            ("BatteryLifePercent", ctypes.c_byte),
            ("SystemStatusFlag", ctypes.c_byte),
            ("BatteryLifeTime", wintypes.DWORD),
            ("BatteryFullLifeTime", wintypes.DWORD),
        ]

    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int

    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    _kernel32.Process32FirstW.restype = wintypes.BOOL
    _kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    _kernel32.Process32NextW.restype = wintypes.BOOL
    _kernel32.GetSystemPowerStatus.argtypes = [ctypes.POINTER(_SYSTEM_POWER_STATUS)]
    _kernel32.GetSystemPowerStatus.restype = wintypes.BOOL

    _MY_PID = os.getpid()


# Executable name (lowercase) -> activity category
_FOREGROUND_APPS: dict[str, str] = {
    # Coding & dev tools
    "code.exe": "coding",
    "cursor.exe": "coding",
    "antigravity.exe": "coding",
    "pycharm64.exe": "coding",
    "idea64.exe": "coding",
    "webstorm64.exe": "coding",
    "goland64.exe": "coding",
    "clion64.exe": "coding",
    "rider64.exe": "coding",
    "devenv.exe": "coding",
    "windowsterminal.exe": "coding",
    "wt.exe": "coding",
    "sublime_text.exe": "coding",
    "zed.exe": "coding",
    # Games & launchers
    "steam.exe": "gaming",
    "yuanshen.exe": "gaming",
    "genshinimpact.exe": "gaming",
    "starrail.exe": "gaming",
    "zenlesszonezero.exe": "gaming",
    "league of legends.exe": "gaming",
    "leagueclientux.exe": "gaming",
    "valorant-win64-shipping.exe": "gaming",
    "cs2.exe": "gaming",
    "dota2.exe": "gaming",
    "narakabladepoint.exe": "gaming",
    "tslgame.exe": "gaming",
    "b1-win64-shipping.exe": "gaming",
    "minecraft.exe": "gaming",
    "wegame.exe": "gaming",
    "epicgameslauncher.exe": "gaming",
    "battle.net.exe": "gaming",
    "wuthering waves.exe": "gaming",
    "client-win64-shipping.exe": "gaming",
    # Office / Docs / Meetings
    "winword.exe": "office",
    "excel.exe": "office",
    "powerpnt.exe": "office",
    "wps.exe": "office",
    "et.exe": "office",
    "wpp.exe": "office",
    "notion.exe": "office",
    "obsidian.exe": "office",
    "feishu.exe": "office",
    "lark.exe": "office",
    "dingtalk.exe": "office",
    "wxwork.exe": "office",
    "wemeetapp.exe": "office",
    "teams.exe": "office",
    "ms-teams.exe": "office",
    "zoom.exe": "office",
    # Creative / Design / Video Editing
    "photoshop.exe": "creative",
    "illustrator.exe": "creative",
    "afterfx.exe": "creative",
    "adobe premiere pro.exe": "creative",
    "jianyingpro.exe": "creative",
    "blender.exe": "creative",
    "clipstudiopaint.exe": "creative",
    "figma.exe": "creative",
    "davinci resolve.exe": "creative",
    # Video players
    "potplayermini64.exe": "video",
    "potplayermini.exe": "video",
    "vlc.exe": "video",
    "mpv.exe": "video",
    "bilibili.exe": "video",
    "iqiyi.exe": "video",
    "qqlive.exe": "video",
    # Chat / Social
    "wechat.exe": "chat",
    "weixin.exe": "chat",
    "qq.exe": "chat",
    "telegram.exe": "chat",
    "discord.exe": "chat",
    # Music players (when active in foreground)
    "cloudmusic.exe": "music",
    "qqmusic.exe": "music",
    "spotify.exe": "music",
    "kugou.exe": "music",
    "kwmusic.exe": "music",
    "foobar2000.exe": "music",
    "musicbee.exe": "music",
    "applemusic.exe": "music",
    "lx-music-desktop.exe": "music",
    "yesplaymusic.exe": "music",
}

_GAME_BG_EXES = {
    "yuanshen.exe",
    "genshinimpact.exe",
    "starrail.exe",
    "zenlesszonezero.exe",
    "league of legends.exe",
    "valorant-win64-shipping.exe",
    "cs2.exe",
    "dota2.exe",
    "narakabladepoint.exe",
    "tslgame.exe",
    "b1-win64-shipping.exe",
    "minecraft.exe",
    "wuthering waves.exe",
}

_MUSIC_BG_EXES = {
    "cloudmusic.exe",
    "qqmusic.exe",
    "spotify.exe",
    "kugou.exe",
    "kwmusic.exe",
    "foobar2000.exe",
    "musicbee.exe",
    "applemusic.exe",
    "lx-music-desktop.exe",
    "yesplaymusic.exe",
}

_BROWSER_EXES = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "arc.exe",
    "360chrome.exe",
}

_VIDEO_TITLE_KEYWORDS = (
    "哔哩哔哩",
    "bilibili",
    "youtube",
    "抖音",
    "爱奇艺",
    "腾讯视频",
    "优酷",
    "netflix",
    "twitch",
    "斗鱼",
    "虎牙",
)

_MUSIC_TITLE_KEYWORDS = (
    "网易云音乐",
    "qq音乐",
    "spotify",
    "apple music",
)


@dataclass(frozen=True)
class ActivitySnapshot:
    category: str | None
    app_name: str = ""
    title: str = ""


def _get_foreground_info() -> tuple[str, str]:
    """Return (exe_basename_lower, window_title) of the active foreground window."""
    if sys.platform != "win32":
        return "", ""
    try:
        fg = _user32.GetForegroundWindow()
        if not fg:
            return "", ""

        pid = wintypes.DWORD(0)
        _user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
        if not pid.value or pid.value == _MY_PID:
            return "", ""

        title_buf = ctypes.create_unicode_buffer(256)
        _user32.GetWindowTextW(fg, title_buf, 256)
        title = title_buf.value

        exe_name = ""
        handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if handle:
            try:
                path_buf = ctypes.create_unicode_buffer(512)
                size = wintypes.DWORD(512)
                if _kernel32.QueryFullProcessImageNameW(handle, 0, path_buf, ctypes.byref(size)):
                    exe_name = os.path.basename(path_buf.value).lower()
            finally:
                _kernel32.CloseHandle(handle)
        return exe_name, title
    except Exception:
        return "", ""


def _find_background_app() -> tuple[str | None, str]:
    """Scan running processes once for active game processes or background music players."""
    if sys.platform != "win32":
        return None, ""
    music_hit = ""
    try:
        snap = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if snap == wintypes.HANDLE(-1).value or not snap:
            return None, ""
        try:
            entry = _PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
            ok = _kernel32.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                exe = entry.szExeFile.lower()
                if exe in _GAME_BG_EXES:
                    return "gaming", exe
                if not music_hit and exe in _MUSIC_BG_EXES:
                    music_hit = exe
                ok = _kernel32.Process32NextW(snap, ctypes.byref(entry))
        finally:
            _kernel32.CloseHandle(snap)
    except Exception:
        pass
    if music_hit:
        return "music", music_hit
    return None, ""


def get_battery_low_percent() -> int | None:
    """Return battery percentage if running on battery at <= 20%, else None."""
    if sys.platform != "win32":
        return None
    try:
        status = _SYSTEM_POWER_STATUS()
        if not _kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return None
        ac_online = status.ACLineStatus == 1
        no_battery = (status.BatteryFlag & 128) != 0 or status.BatteryLifePercent == 255
        if ac_online or no_battery:
            return None
        pct = int(status.BatteryLifePercent)
        if 0 < pct <= 20:
            return pct
    except Exception:
        pass
    return None


def inspect_current_activity() -> ActivitySnapshot:
    """Inspect current user activity (low battery > active foreground app > background music)."""
    low_pct = get_battery_low_percent()
    if low_pct is not None:
        return ActivitySnapshot(category="low_battery", app_name=f"{low_pct}%")

    exe, title = _get_foreground_info()
    title_l = title.lower()

    if exe in _BROWSER_EXES:
        if any(k in title_l for k in _VIDEO_TITLE_KEYWORDS):
            return ActivitySnapshot(category="video", app_name=exe, title=title)
        if any(k in title_l for k in _MUSIC_TITLE_KEYWORDS):
            return ActivitySnapshot(category="music", app_name=exe, title=title)
        if "github" in title_l or "stackoverflow" in title_l or "localhost" in title_l:
            return ActivitySnapshot(category="coding", app_name=exe, title=title)

    if exe in _FOREGROUND_APPS:
        return ActivitySnapshot(category=_FOREGROUND_APPS[exe], app_name=exe, title=title)

    bg_cat, bg_exe = _find_background_app()
    if bg_cat is not None:
        return ActivitySnapshot(category=bg_cat, app_name=bg_exe)

    return ActivitySnapshot(category=None, app_name=exe, title=title)


class ActivityReactor:
    """Stateful debounced activity monitor with smart anti-spam cooldowns."""

    def __init__(
        self,
        global_cooldown_sec: float = 95.0,
        category_cooldown_sec: float = 720.0,
    ) -> None:
        self._global_cooldown = global_cooldown_sec
        self._category_cooldown = category_cooldown_sec
        self._last_global_at = 0.0
        self._last_cat_at: dict[str, float] = {}
        self._pending_cat: str | None = None
        self._pending_hits = 0

    def poll(self) -> ActivitySnapshot | None:
        """Called every ~5s; returns a snapshot only when confirmed & off cooldown."""
        now = time.monotonic()
        if now - self._last_global_at < self._global_cooldown:
            return None

        snap = inspect_current_activity()
        if snap.category is None:
            self._pending_cat = None
            self._pending_hits = 0
            return None

        # Debounce: require 2 consecutive polls (~5-10s) so quick Alt-Tab doesn't spam
        if snap.category == self._pending_cat:
            self._pending_hits += 1
        else:
            self._pending_cat = snap.category
            self._pending_hits = 1
            return None

        if self._pending_hits < 2:
            return None

        last_cat = self._last_cat_at.get(snap.category, 0.0)
        if now - last_cat < self._category_cooldown:
            return None

        self._last_global_at = now
        self._last_cat_at[snap.category] = now
        self._pending_hits = 0
        return snap
