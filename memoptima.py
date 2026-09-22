# -*- coding: utf-8 -*-
"""
MemOptima v3.1 ULTIMATE - Maximum RAM Optimizer for Windows
7-Layer memory compression using all available native Windows APIs.
Circular gauge, sparkline history, system tray — always running.

v3.1 Improvements:
  - Smart Trim: skips processes with CPU > 2% (actively running)
  - Foreground Protection: never trims the app the user is interacting with
  - Layer 5 fix: file cache limited to 256 MB instead of 1 byte
  - Adaptive Auto-Mode: dynamic interval based on RAM pressure
  - Process Whitelist: user-defined protected processes (right-click menu)
  - Process Grouping: duplicate processes aggregated by name
  - Config Persistence: settings saved to config.json
  - Toast Notifications: auto-mode notifies via system tray
  - Start with Windows: optional registry-based autostart
"""

import os
import sys
import time
import math
import json
import threading
import subprocess
from datetime import datetime
from collections import deque
import tkinter as tk
from tkinter import ttk, messagebox
import psutil

# ═══════════════════════════════════════════════════════════════════════════════
# PLATFORM + ADMIN DETECTION
# ═══════════════════════════════════════════════════════════════════════════════
IS_WINDOWS = sys.platform == "win32"
IS_ADMIN   = False

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes
    import winreg
    try:
        IS_ADMIN = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        IS_ADMIN = False

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_SCRIPT_DIR, "config.json")

_DEFAULT_CONFIG = {
    "limit_gb":      4.0,
    "interval_sec":  60,
    "auto_mode":     True,
    "use_filecache": True,
    "whitelist":     [],
    "start_with_windows": False,
}

def _load_config():
    """Load config from JSON file, merging with defaults for missing keys."""
    cfg = dict(_DEFAULT_CONFIG)
    try:
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg.update(saved)
    except Exception:
        pass
    return cfg

def _save_config(cfg):
    """Persist config to JSON file."""
    try:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════════════════════
# STARTUP WITH WINDOWS (Registry)
# ═══════════════════════════════════════════════════════════════════════════════
_STARTUP_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
_STARTUP_NAME = "MemOptima"

def _is_startup_enabled():
    """Check if MemOptima is registered to start with Windows."""
    if not IS_WINDOWS:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, _STARTUP_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False

def _set_startup(enabled):
    """Add or remove MemOptima from Windows startup."""
    if not IS_WINDOWS:
        return
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_KEY, 0, winreg.KEY_SET_VALUE)
        if enabled:
            exe = sys.executable
            script = os.path.abspath(__file__)
            winreg.SetValueEx(key, _STARTUP_NAME, 0, winreg.REG_SZ,
                              '"{}" "{}"'.format(exe, script))
        else:
            try:
                winreg.DeleteValue(key, _STARTUP_NAME)
            except Exception:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════════════════════
# WINDOWS NATIVE API SETUP
# ═══════════════════════════════════════════════════════════════════════════════
if IS_WINDOWS:
    _adv = ctypes.WinDLL('advapi32', use_last_error=True)
    _k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _ps  = ctypes.WinDLL('psapi',    use_last_error=True)
    _nt  = ctypes.WinDLL('ntdll',    use_last_error=True)
    _u32 = ctypes.WinDLL('user32',   use_last_error=True)

    # kernel32 — process handles
    _OpenProcess           = _k32.OpenProcess
    _OpenProcess.restype   = wintypes.HANDLE
    _OpenProcess.argtypes  = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

    _CloseHandle           = _k32.CloseHandle
    _CloseHandle.restype   = wintypes.BOOL
    _CloseHandle.argtypes  = [wintypes.HANDLE]

    _GetCurrentProcess     = _k32.GetCurrentProcess
    _GetCurrentProcess.restype = wintypes.HANDLE

    # kernel32 — working set trim (Layer 2b)
    _SetWSEx               = _k32.SetProcessWorkingSetSizeEx
    _SetWSEx.restype       = wintypes.BOOL
    _SetWSEx.argtypes      = [wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]

    # kernel32 — memory priority (Layer 2c, Win8+)
    try:
        _SetProcInfo           = _k32.SetProcessInformation
        _SetProcInfo.restype   = wintypes.BOOL
        _SetProcInfo.argtypes  = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        HAS_PROCINFO = True
    except AttributeError:
        HAS_PROCINFO = False

    # kernel32 — file cache reduction (Layer 5)
    _SetFileCache          = _k32.SetSystemFileCacheSize
    _SetFileCache.restype  = wintypes.BOOL
    _SetFileCache.argtypes = [ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]

    # psapi — empty working set (Layer 2)
    _EmptyWS               = _ps.EmptyWorkingSet
    _EmptyWS.restype       = wintypes.BOOL
    _EmptyWS.argtypes      = [wintypes.HANDLE]

    # ntdll — system-level memory commands (Layers 1, 3, 4, 6)
    _NtSysInfo             = _nt.NtSetSystemInformation
    _NtSysInfo.restype     = ctypes.c_long
    _NtSysInfo.argtypes    = [ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]

    # advapi32 — privilege management (Layer 0)
    _OpenProcToken         = _adv.OpenProcessToken
    _OpenProcToken.restype = wintypes.BOOL
    _OpenProcToken.argtypes= [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]

    _LookupPriv            = _adv.LookupPrivilegeValueW
    _LookupPriv.restype    = wintypes.BOOL
    _LookupPriv.argtypes   = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]

    _AdjustToken           = _adv.AdjustTokenPrivileges
    _AdjustToken.restype   = wintypes.BOOL
    _AdjustToken.argtypes  = [wintypes.HANDLE, wintypes.BOOL, ctypes.c_void_p,
                               wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]

    # user32 — foreground window detection (Foreground Protection)
    _GetForegroundWindow   = _u32.GetForegroundWindow
    _GetForegroundWindow.restype = wintypes.HANDLE

    _GetWindowThreadProcessId = _u32.GetWindowThreadProcessId
    _GetWindowThreadProcessId.restype = wintypes.DWORD
    _GetWindowThreadProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]

    # Constants
    PROC_ACCESS           = 0x0400 | 0x0100 | 0x0200   # QUERY | SET_QUOTA | SET_INFO
    TOKEN_ADJUST          = 0x0020 | 0x0008             # ADJUST_PRIVILEGES | QUERY
    SE_PRIV_ENABLED       = 0x00000002
    _SYSINFO_MEMLIST      = 80
    _MEM_EMPTY_ALL_WS     = 2    # System-wide working set empty (admin)
    _MEM_FLUSH_MODIFIED   = 3    # Flush modified page list
    _MEM_PURGE_STANDBY    = 4    # Purge standby list
    _MEM_COMBINE_PAGES    = 5    # Memory page combining (Win8+)
    _PROC_MEM_PRIORITY    = 39   # ProcessMemoryPriority class for SetProcessInformation
    MEMORY_PRIORITY_LOW   = 1    # MEMORY_PRIORITY_VERY_LOW
    _SIZE_MAX             = ctypes.c_size_t(-1).value
    _FILECACHE_MIN        = 256 * 1024 * 1024  # 256 MB — reasonable minimum, not destructive

# Processos críticos — NUNCA tocar
SYSTEM_PROCS = {
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "winlogon.exe", "lsass.exe", "lsm.exe", "services.exe",
    "svchost.exe", "dwm.exe", "fontdrvhost.exe", "lsaiso.exe",
    "memory compression", "secure system", "ntoskrnl.exe",
    "idle", "[system process]", "spoolsv.exe"
}

# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 0 — PRIVILEGE ELEVATION
# ═══════════════════════════════════════════════════════════════════════════════
def _enable_privileges():
    """Enable all memory-related Windows privileges in our token."""
    if not IS_WINDOWS or not IS_ADMIN:
        return

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class LuidAttr(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

    class TokenPriv(ctypes.Structure):
        _fields_ = [("Count", wintypes.DWORD), ("Privs", LuidAttr * 1)]

    try:
        hToken = wintypes.HANDLE()
        if not _OpenProcToken(_GetCurrentProcess(), TOKEN_ADJUST, ctypes.byref(hToken)):
            return
        for priv in ["SeDebugPrivilege", "SeIncreaseQuotaPrivilege",
                     "SeProfileSingleProcessPrivilege", "SeLockMemoryPrivilege"]:
            luid = LUID()
            if _LookupPriv(None, priv, ctypes.byref(luid)):
                tp = TokenPriv()
                tp.Count = 1
                tp.Privs[0].Luid = luid
                tp.Privs[0].Attributes = SE_PRIV_ENABLED
                _AdjustToken(hToken, False, ctypes.byref(tp),
                             ctypes.sizeof(tp), None, None)
        _CloseHandle(hToken)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# FOREGROUND PROCESS DETECTION
# ═══════════════════════════════════════════════════════════════════════════════
def _get_foreground_pid():
    """Return the PID of the process that owns the foreground window, or 0."""
    if not IS_WINDOWS:
        return 0
    try:
        hwnd = _GetForegroundWindow()
        if not hwnd:
            return 0
        pid = wintypes.DWORD(0)
        _GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value
    except Exception:
        return 0


# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# DESIGN TOKENS — Dark Ocean / Neon Blue Theme
# ═══════════════════════════════════════════════════════════════════════════════
BG      = "#060913"   # Deep ocean background
CARD    = "#0b1021"   # Dark blue card
C2      = "#11182c"   # Secondary card
C3      = "#192440"   # Hover/input bg
WHT     = "#f8fafc"   # Bright text
GRY     = "#64748b"   # Slate text
NEON    = "#00d2ff"   # Cyan/Neon Blue (Primary)
NE2     = "#00a1cc"   # Cyan active state
NE_DIM  = "#002b3a"   # Cyan dimmed (track bg)
ACCNT   = "#a78bfa"   # Violet accent
WARN    = "#f59e0b"   # Amber warning
RED     = "#f43f5e"   # Rose red
BLU     = "#38bdf8"   # Info blue
AC_DIM  = "#1a162e"   # Accent dimmed
BDR     = "#1e293b"   # Border
DRK     = "#020617"   # Dark text on bright bg


# ═══════════════════════════════════════════════════════════════════════════════
# CIRCULAR GAUGE WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class CircularGauge(tk.Canvas):
    """Animated circular RAM usage gauge drawn on a Canvas."""

    def __init__(self, parent, size=190, **kwargs):
        super().__init__(parent, width=size, height=size,
                         bg=CARD, highlightthickness=0, **kwargs)
        self._sz  = size
        self._cx  = size / 2
        self._cy  = size / 2
        self._r   = size * 0.40   # arc radius
        self._lw  = int(size * 0.075)  # arc line width

        self._target  = 0.0
        self._current = 0.0
        self._anim_id = None
        self._draw(0.0)

    def set_value(self, pct: float):
        self._target = max(0.0, min(100.0, pct))
        if self._anim_id is None:
            self._animate()

    def _animate(self):
        diff = self._target - self._current
        if abs(diff) < 0.3:
            self._current = self._target
            self._anim_id = None
        else:
            self._current += diff * 0.12
            self._anim_id = self.after(16, self._animate)
        self._draw(self._current)

    def _color(self, pct):
        if pct >= 85:
            return RED
        elif pct >= 65:
            return WARN
        return NEON

    def _draw(self, pct):
        self.delete("all")
        cx, cy, r, lw = self._cx, self._cy, self._r, self._lw
        x0, y0, x1, y1 = cx - r, cy - r, cx + r, cy + r

        # Outer glow ring
        gr = r + lw + 4
        self.create_oval(cx - gr, cy - gr, cx + gr, cy + gr,
                         outline=NE_DIM, width=1)

        # Track arc (background)
        self.create_arc(x0, y0, x1, y1,
                        start=135, extent=-270,
                        style=tk.ARC, outline=NE_DIM, width=lw)

        # Value arc (fill)
        color  = self._color(pct)
        extent = -(pct / 100.0 * 270.0)
        if abs(extent) > 0.5:
            self.create_arc(x0, y0, x1, y1,
                            start=135, extent=extent,
                            style=tk.ARC, outline=color, width=lw)

        # Center percentage text
        fsz = int(self._sz * 0.115)
        self.create_text(cx, cy - fsz * 0.55,
                         text="{:.1f}%".format(pct),
                         font=("Segoe UI", fsz, "bold"), fill=WHT)
        self.create_text(cx, cy + fsz * 0.60,
                         text="RAM", font=("Segoe UI", int(self._sz * 0.062)),
                         fill=GRY)

        # Small indicator dot at tip of arc
        if pct > 1:
            angle_deg = 135 - (pct / 100 * 270)
            angle_rad = math.radians(angle_deg)
            tip_x = cx + r * math.cos(angle_rad)
            tip_y = cy - r * math.sin(angle_rad)
            dr = lw * 0.6
            self.create_oval(tip_x - dr, tip_y - dr,
                             tip_x + dr, tip_y + dr,
                             fill=color, outline="")


# ═══════════════════════════════════════════════════════════════════════════════
# SPARKLINE WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class Sparkline(tk.Canvas):
    """Real-time sparkline graph of memory usage history.
    Supports configurable line and fill colors for reuse across RAM and pagefile."""

    def __init__(self, parent, height=52, maxpoints=90,
                 line_color=None, fill_color=None, **kwargs):
        super().__init__(parent, height=height,
                         bg=CARD, highlightthickness=0, **kwargs)
        self._width  = 100 # Initial fallback, will update on resize
        self._height = height
        self._data   = deque(maxlen=maxpoints)
        self._line_c = line_color if line_color is not None else NEON
        self._fill_c = fill_color if fill_color is not None else NE_DIM
        self.bind("<Configure>", self._on_resize)
        self._draw()

    def _on_resize(self, event):
        self._width = event.width
        self._draw()

    def add(self, value: float):
        self._data.append(max(0.0, min(100.0, value)))
        self._draw()

    def _draw(self):
        self.delete("all")
        data = list(self._data)
        n    = len(data)
        if n < 2:
            return

        pad  = 4
        h    = self._height - pad * 2
        w    = self._width

        # Compute point coordinates
        step = w / (n - 1)
        pts  = []
        for i, v in enumerate(data):
            x = i * step
            y = pad + h - (v / 100.0) * h
            pts.append((x, y))

        # Filled area under curve
        poly = [(0, self._height)] + pts + [(w, self._height)]
        flat = [c for p in poly for c in p]
        self.create_polygon(flat, fill=self._fill_c, outline="")

        # Line
        flat_pts = [c for p in pts for c in p]
        self.create_line(flat_pts, fill=self._line_c, width=2, smooth=True)

        # Current value dot
        lx, ly = pts[-1]
        self.create_oval(lx - 4, ly - 4, lx + 4, ly + 4,
                         fill=self._line_c, outline=BG, width=2)

        # Y-axis labels
        for pct_mark in [25, 50, 75, 100]:
            yy = pad + h - (pct_mark / 100.0) * h
            self.create_line(0, yy, w, yy, fill=BDR, dash=(2, 6))
            self.create_text(w - 3, yy, text="{}%".format(pct_mark),
                             font=("Consolas", 7), fill=GRY, anchor="e")


# ═══════════════════════════════════════════════════════════════════════════════
# OPTIMIZATION ENGINE — 7 LAYERS (v3.1 Smart)
# ═══════════════════════════════════════════════════════════════════════════════
class OptimizationEngine:
    """
    7-Layer RAM optimization engine (v3.1 Smart):
      Layer 0:  Enable Windows privileges (SeDebug, SeIncreaseQuota, etc.)
      Layer 1:  NtSetSystemInformation(MemoryEmptyWorkingSet) — system-wide (admin)
      Layer 2b: EmptyWorkingSet + SetProcessWorkingSetSizeEx — per process
                ✓ Smart Trim: skips processes with CPU > 2%
                ✓ Foreground Protection: skips the active window's process
                ✓ Whitelist: skips user-protected processes
      Layer 4:  NtSetSystemInformation(MemoryPurgeStandbyList) — admin
      Layer 5:  SetSystemFileCacheSize(256MB) — reduce file cache — admin
      Layer 6:  NtSetSystemInformation(MemoryCombinePhysicalMemory) — admin, Win8+
    """

    def __init__(self, config: dict):
        self.limit_gb      = config.get("limit_gb", 2.0)
        self.interval_sec  = config.get("interval_sec", 60)
        self.auto_mode     = config.get("auto_mode", True)
        self.use_filecache = config.get("use_filecache", True)
        self.whitelist     = set(config.get("whitelist", []))

        self.total_freed_mb = 0.0
        self.total_runs     = 0
        self.layers_fired    = []   # Last run active layers
        self.running        = True
        self._optimizing    = False
        self._lock          = threading.Lock()
        self._callbacks     = []
        self._last_ts       = 0.0
        self._privs_enabled = False
        self._last_pf       = {}

        # Enable privileges immediately
        _enable_privileges()
        self._privs_enabled = True

        threading.Thread(target=self._auto_loop, daemon=True).start()

    def get_config_dict(self):
        """Return current settings as a dict for persistence."""
        return {
            "limit_gb":      self.limit_gb,
            "interval_sec":  self.interval_sec,
            "auto_mode":     self.auto_mode,
            "use_filecache": self.use_filecache,
            "whitelist":     sorted(list(self.whitelist)),
        }

    def register_callback(self, cb):
        self._callbacks.append(cb)

    def _emit(self, event, data=None):
        for cb in self._callbacks:
            try:
                cb(event, data)
            except Exception:
                pass

    def stop(self):
        self.running = False

    # ── Auto Loop (v3.1 Adaptive) ─────────────────────────────────────────────
    def _auto_loop(self):
        while self.running:
            time.sleep(5)
            if not self.auto_mode or self._optimizing:
                continue
            try:
                mem     = psutil.virtual_memory()
                used_gb = mem.used / (1024 ** 3)
                ram_pct = mem.percent
                elapsed = time.time() - self._last_ts

                # Adaptive interval based on RAM pressure
                if ram_pct > 85:
                    effective_interval = max(30, self.interval_sec // 2)
                elif ram_pct > 65:
                    effective_interval = self.interval_sec
                else:
                    # RAM is comfortable — use 3× interval (only optimize if over limit)
                    effective_interval = self.interval_sec * 3

                if used_gb > self.limit_gb or elapsed >= effective_interval:
                    self._run("auto")
            except Exception:
                pass

    # ── Public ────────────────────────────────────────────────────────────────
    def optimize_now(self):
        if not self._optimizing:
            threading.Thread(target=self._run, args=("manual",), daemon=True).start()

    # ── Core ──────────────────────────────────────────────────────────────────
    def _run(self, trigger: str):
        if self._optimizing:
            return
        self._optimizing = True
        self._emit("start", {"trigger": trigger})
        try:
            self._do_optimize(trigger)
        finally:
            self._optimizing = False

    def _do_optimize(self, trigger: str):
        if not IS_WINDOWS:
            self._emit("done", {"trigger": trigger, "freed_mb": 0.0, "cleaned": 0,
                                "skipped": 0, "layers": [], "total_freed": 0.0,
                                "total_runs": 0, "is_admin": False,
                                "timestamp": datetime.now(),
                                "pf_pct": 0.0, "pf_used_mb": 0.0, "pf_free_mb": 0.0,
                                "pf_protected": False})
            return

        mem_before = psutil.virtual_memory().available
        cleaned    = 0
        skipped    = 0
        layers     = []

        # ── Check Swap Lock (4GB Limit Safety) ────────────────────────────────────
        swap = psutil.swap_memory()
        swap_gb = swap.used / (1024 ** 3)
        is_swap_safe = (swap_gb < 4.0)

        if not is_swap_safe:
            layers.append("⚠ Swap Lock (>4.0GB)")

        # ── Detect foreground process PID (Foreground Protection) ──────────────
        fg_pid = _get_foreground_pid()

        # ── Layer 1: System-wide working set empty (admin) ───────────────────────
        if IS_ADMIN and is_swap_safe:
            try:
                cmd = ctypes.c_int(_MEM_EMPTY_ALL_WS)
                st  = _NtSysInfo(_SYSINFO_MEMLIST, ctypes.byref(cmd), ctypes.sizeof(cmd))
                if st == 0:
                    layers.append("L1: SystemEmptyWS")
            except Exception:
                pass

        # ── Layer 2b: Per-Process Smart Trim ─────────────────────────────────────
        # v3.1: Skip processes that are actively running (CPU > 2%),
        #       the foreground window process, and whitelisted processes.
        #       Also skips processes with high page faults to avoid thrashing.
        if is_swap_safe:
            trimmed = 0
            current_pf = {}
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
                try:
                    pid  = proc.info['pid']
                    name = (proc.info['name'] or "").lower()
                    if pid == 0 or name in SYSTEM_PROCS:
                        continue

                    # v3.1: Foreground Protection — never trim the app the user is using
                    if pid == fg_pid:
                        skipped += 1
                        continue

                    # v3.1: Whitelist Protection — skip user-protected processes
                    if name in self.whitelist:
                        skipped += 1
                        continue

                    # v3.1: Smart Trim — skip processes with CPU > 2%
                    cpu = proc.info.get('cpu_percent', 0.0) or 0.0
                    if cpu > 2.0:
                        skipped += 1
                        continue
                        
                    # v3.1: Thrashing Protection — don't trim if it's actively paging in
                    mem_info = proc.info.get('memory_info')
                    if mem_info:
                        pf = getattr(mem_info, 'num_page_faults', 0)
                        current_pf[pid] = pf
                        last_pf = self._last_pf.get(pid, pf)
                        if (pf - last_pf) > 1000:
                            skipped += 1
                            continue

                    handle = _OpenProcess(PROC_ACCESS, False, pid)
                    if handle:
                        _EmptyWS(handle)
                        if IS_ADMIN:
                            _SetWSEx(handle, _SIZE_MAX, _SIZE_MAX, 0)
                        _CloseHandle(handle)
                        trimmed += 1
                        cleaned += 1
                except Exception:
                    continue
            
            self._last_pf = current_pf
            if trimmed > 0 or skipped > 0:
                layers.append("L2b: Trim({}) Skip({})".format(trimmed, skipped))

        # ── Layers 3 & 4: System memory list commands (admin) ─────────────────
        # These reorganize pages between memory lists (Modified → Standby → Free)
        # sem gerar pico imediato de I/O no disco (FlushModified foi removido para poupar o SSD).
        if IS_ADMIN:
            for cmd_val, label in [(_MEM_PURGE_STANDBY,  "L4: PurgeStandby")]:
                try:
                    cmd = ctypes.c_int(cmd_val)
                    st  = _NtSysInfo(_SYSINFO_MEMLIST, ctypes.byref(cmd), ctypes.sizeof(cmd))
                    if st == 0:
                        layers.append(label)
                except Exception:
                    pass

        # ── Layer 5: Reduce system file cache (admin) ──────────────────────────
        # v3.1: Changed from 1 byte to 256 MB minimum.
        # Setting to 1 byte was counterproductive — it forced the OS to re-read
        # everything from disk, causing SSD wear and worse performance.
        # 256 MB is a reasonable floor that still frees substantial RAM.
        if IS_ADMIN and self.use_filecache:
            try:
                if _SetFileCache(_FILECACHE_MIN, _SIZE_MAX, 0):
                    layers.append("L5: FileCache(256MB)")
            except Exception:
                pass

        # ── Layer 6 & 7: Memory page combining (admin, Win8+) ─────────────────────
        # Deduplicates identical physical pages purely in RAM — zero disk I/O.
        if IS_ADMIN:
            try:
                for _ in range(3):  # Multiple passes for maximum in-RAM dedup
                    cmd = ctypes.c_int(_MEM_COMBINE_PAGES)
                    st  = _NtSysInfo(_SYSINFO_MEMLIST, ctypes.byref(cmd), ctypes.sizeof(cmd))
                if st == 0:
                    layers.append("L6: PageCombine")
            except Exception:
                pass

        # ── Auto-trim do próprio processo ────────────────────────────────────
        # O processo Python do MemOptima acumula memória de working set ao longo
        # do tempo. Esvaziar o próprio WS depois de cada ciclo mantém o footprint
        # do app mínimo sem gerar I/O (as páginas já estão em RAM).
        if IS_WINDOWS:
            try:
                own = _GetCurrentProcess()
                _EmptyWS(own)
                if IS_ADMIN:
                    _SetWSEx(own, _SIZE_MAX, _SIZE_MAX, 0)
            except Exception:
                pass

        mem_after  = psutil.virtual_memory().available
        freed_mb   = max(0.0, (mem_after - mem_before) / (1024 * 1024))

        self.total_freed_mb += freed_mb
        self.total_runs     += 1
        self.layers_fired    = layers
        self._last_ts        = time.time()

        self._emit("done", {
            "trigger":      trigger,
            "freed_mb":     freed_mb,
            "cleaned":      cleaned,
            "skipped":      skipped,
            "layers":       layers,
            "total_freed":  self.total_freed_mb,
            "total_runs":   self.total_runs,
            "is_admin":     IS_ADMIN,
            "timestamp":    datetime.now(),
        })


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════
class MemOptimaApp:

    def __init__(self, root: tk.Tk, engine: OptimizationEngine):
        self.root   = root
        self.engine = engine
        self._tray  = None
        self._pulse_job = None

        engine.register_callback(self._on_engine_event)

        self._config_window()
        self._setup_styles()
        self._build_ui()
        self._start_monitor()

    # ── Window ────────────────────────────────────────────────────────────────
    def _config_window(self):
        self.root.title("MemOptima v3.1 ULTIMATE")
        self.root.geometry("600x900")
        self.root.minsize(500, 750)
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        self.is_fullscreen = False
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)
        return "break"
        
    def exit_fullscreen(self, event=None):
        self.is_fullscreen = False
        self.root.attributes("-fullscreen", False)
        return "break"

    def _on_close(self):
        self._persist_config()
        if self._tray:
            self.root.withdraw()
        else:
            if messagebox.askyesno("Sair", "Encerrar o MemOptima?\nO monitoramento será interrompido."):
                self._exit()

    def _exit(self):
        self._persist_config()
        self.engine.stop()
        if self._tray:
            try:
                self._tray.stop()
            except Exception:
                pass
        self.root.after(0, self.root.destroy)

    def _persist_config(self):
        """Save current settings to config.json."""
        cfg = self.engine.get_config_dict()
        cfg["start_with_windows"] = self._v_startup.get() if hasattr(self, '_v_startup') else False
        _save_config(cfg)

    def set_tray(self, icon):
        self._tray = icon

    def restore(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _launch_vram_compressor(self):
        """Abre o VirtualRAM Compressor como processo independente."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        compressor = os.path.join(script_dir, "vram_compressor.py")
        if not os.path.exists(compressor):
            messagebox.showerror(
                "VirtualRAM Compressor",
                "Arquivo 'vram_compressor.py' não encontrado em:\n{}".format(script_dir)
            )
            return
        try:
            subprocess.Popen(
                [sys.executable, compressor],
                cwd=script_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE if IS_WINDOWS else 0
            )
        except Exception as ex:
            messagebox.showerror("VirtualRAM Compressor",
                                 "Erro ao iniciar o Compressor:\n{}".format(ex))

    # ── Styles ────────────────────────────────────────────────────────────────
    def _setup_styles(self):
        s = ttk.Style()
        s.theme_use('clam')
        for name, c in [('G.Horizontal.TProgressbar', NEON),
                         ('W.Horizontal.TProgressbar', WARN),
                         ('R.Horizontal.TProgressbar', RED)]:
            s.configure(name, troughcolor=NE_DIM, background=c,
                        bordercolor=BG, lightcolor=c, darkcolor=c, thickness=6)

    # ── UI Assembly ───────────────────────────────────────────────────────────
    def _build_ui(self):
        wrap = tk.Frame(self.root, bg=BG)
        wrap.pack(fill="both", expand=True)

        self._build_header(wrap)
        self._build_metrics(wrap)
        self._build_action(wrap)
        self._build_layers_bar(wrap)
        self._build_settings(wrap)
        self._build_processes(wrap)
        self._build_history(wrap)

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self, p):
        f = tk.Frame(p, bg=BG)
        f.pack(fill="x", pady=(16, 6))

        row = tk.Frame(f, bg=BG)
        row.pack()

        tk.Label(row, text="Mem", font=("Segoe UI", 28, "bold"),
                 fg=WHT, bg=BG).pack(side="left")
        tk.Label(row, text="Optima", font=("Segoe UI", 28, "bold"),
                 fg=NEON, bg=BG).pack(side="left")
        tk.Label(row, text=" v3.1", font=("Segoe UI", 14),
                 fg=GRY, bg=BG).pack(side="left", pady=(12, 0))

        badge_c = BLU if IS_ADMIN else WARN
        badge_t = "★ ADMIN" if IS_ADMIN else "⚠ USER"
        tk.Label(row, text="  {}  ".format(badge_t),
                 font=("Segoe UI", 8, "bold"),
                 fg=DRK, bg=badge_c).pack(side="left", padx=(10, 0), pady=(14, 0))

        fs_btn = tk.Button(row, text="⛶", font=("Segoe UI", 12), fg=GRY, bg=BG, bd=0,
                           cursor="hand2", command=self.toggle_fullscreen, activebackground=BG, activeforeground=WHT)
        fs_btn.pack(side="left", padx=(10, 0), pady=(12, 0))

        # Botão launcher do VirtualRAM Compressor (abre como processo independente)
        tk.Label(f, text="ULTIMATE RAM Optimizer — Smart 7 Layers — Always Running",
                 font=("Segoe UI", 9), fg=GRY, bg=BG).pack()

        # Linha de ação rápida: warning admin + launcher do Compressor
        action_row = tk.Frame(f, bg=BG)
        action_row.pack(pady=(4, 0))

        if not IS_ADMIN:
            tk.Label(action_row,
                text="Execute run_admin.bat para ativar camadas de sistema",
                font=("Segoe UI", 8), fg=WARN, bg=BG).pack(side="left", padx=(0, 12))

        compressor_btn = tk.Button(
            action_row,
            text="🗜  Compressor RAM",
            font=("Segoe UI", 8, "bold"),
            fg="#060913", bg="#a78bfa",
            activebackground="#7c5cdb",
            activeforeground="#060913",
            bd=0, cursor="hand2", padx=10, pady=3,
            command=self._launch_vram_compressor
        )
        compressor_btn.pack(side="left")
        compressor_btn.bind("<Enter>", lambda e: compressor_btn.config(bg="#7c5cdb"))
        compressor_btn.bind("<Leave>", lambda e: compressor_btn.config(bg="#a78bfa"))

    # ── Metrics Card ──────────────────────────────────────────────────────────
    def _build_metrics(self, p):
        card = self._card(p)
        inn  = tk.Frame(card, bg=CARD)
        inn.pack(fill="x", padx=16, pady=14)

        # Left: circular gauge
        left = tk.Frame(inn, bg=CARD)
        left.pack(side="left", anchor="n")
        self.gauge = CircularGauge(left, size=188)
        self.gauge.pack()

        # Right: RAM + Pagefile stat labels
        right = tk.Frame(inn, bg=CARD)
        right.pack(side="left", padx=(18, 0), fill="y", expand=True)

        # ── RAM (Physical) ──────────────────────────────────────────────
        tk.Label(right, text="Memória RAM (Física)",
                 font=("Segoe UI", 11, "bold"), fg=NEON, bg=CARD).pack(anchor="w")

        self.lbl_used  = self._stat_row(right, "Usado :")
        self.lbl_free  = self._stat_row(right, "Livre  :")
        self.lbl_total = self._stat_row(right, "Total  :")

        sep = tk.Frame(right, bg=BDR, height=1)
        sep.pack(fill="x", pady=6)

        self.lbl_limit_status = tk.Label(right, text="",
            font=("Segoe UI", 9, "bold"), fg=NEON, bg=CARD)
        self.lbl_limit_status.pack(anchor="w")

        spark_f = tk.Frame(card, bg=CARD)
        spark_f.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(spark_f, text="Histórico RAM (física) — últimos 3 min",
                 font=("Segoe UI", 7), fg=GRY, bg=CARD).pack(anchor="w")
        self.sparkline = Sparkline(spark_f, height=44)
        self.sparkline.pack(fill="x", expand=True)

    def _stat_row(self, parent, label):
        f = tk.Frame(parent, bg=CARD)
        f.pack(anchor="w", pady=3)
        tk.Label(f, text=label, font=("Consolas", 9), fg=GRY, bg=CARD,
                 width=9, anchor="w").pack(side="left")
        lbl = tk.Label(f, text="--- GB", font=("Consolas", 12, "bold"),
                       fg=WHT, bg=CARD)
        lbl.pack(side="left")
        return lbl

    # ── Action Card ───────────────────────────────────────────────────────────
    def _build_action(self, p):
        card = self._card(p)
        inn  = tk.Frame(card, bg=CARD)
        inn.pack(fill="x", padx=16, pady=14)

        # Button
        self.btn = tk.Button(inn, text="⚡  OTIMIZAR MEMÓRIA AGORA",
                             font=("Segoe UI", 13, "bold"),
                             fg=DRK, bg=NEON, activebackground=NE2,
                             activeforeground=DRK, bd=0, cursor="hand2",
                             relief="flat", padx=20, pady=12,
                             command=self._on_opt_click)
        self.btn.pack(fill="x")
        self.btn.bind("<Enter>", lambda e: self.btn.config(bg=NE2)
                      if str(self.btn["state"]) == "normal" else None)
        self.btn.bind("<Leave>", lambda e: self.btn.config(bg=NEON)
                      if str(self.btn["state"]) == "normal" else None)

        # Stats row
        stats_f = tk.Frame(inn, bg=CARD)
        stats_f.pack(fill="x", pady=(10, 0))

        self.lbl_last  = tk.Label(stats_f, text="Última:  —",
                                  font=("Segoe UI", 9), fg=WHT, bg=CARD)
        self.lbl_last.pack(side="left")

        self.lbl_total = tk.Label(stats_f, text="  |  Total: 0 MB",
                                  font=("Segoe UI", 9), fg=GRY, bg=CARD)
        self.lbl_total.pack(side="left")

        self.lbl_runs  = tk.Label(stats_f, text="  |  Runs: 0",
                                  font=("Segoe UI", 9), fg=GRY, bg=CARD)
        self.lbl_runs.pack(side="left")

    # ── Active Layers Bar ─────────────────────────────────────────────────────
    def _build_layers_bar(self, p):
        card = self._card(p, pad_v=0)
        f = tk.Frame(card, bg=C2)
        f.pack(fill="x", padx=0, pady=0)

        tk.Label(f, text="CAMADAS ATIVAS:",
                 font=("Consolas", 7, "bold"), fg=GRY, bg=C2,
                 pady=5, padx=10).pack(side="left")

        self.lbl_layers = tk.Label(f, text="—",
            font=("Consolas", 7), fg=ACCNT, bg=C2, pady=5, wraplength=380, justify="left")
        self.lbl_layers.pack(side="left", padx=4)

    # ── Settings Card ─────────────────────────────────────────────────────────
    def _build_settings(self, p):
        card = self._card(p)

        hdr = tk.Frame(card, bg=C2)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙  Auto-Modo & Configurações",
                 font=("Segoe UI", 9, "bold"), fg=WHT, bg=C2,
                 pady=7, padx=12).pack(side="left")

        inn = tk.Frame(card, bg=CARD)
        inn.pack(fill="x", padx=14, pady=10)

        # Row 1: Auto toggle
        r1 = tk.Frame(inn, bg=CARD)
        r1.pack(fill="x", pady=(0, 8))

        tk.Label(r1, text="Auto-Modo:", font=("Segoe UI", 10, "bold"),
                 fg=WHT, bg=CARD).pack(side="left")

        self.btn_auto = tk.Button(r1, text="OFF",
                                  font=("Segoe UI", 9, "bold"),
                                  fg=WHT, bg="#1a1a30", bd=0,
                                  padx=18, pady=5, cursor="hand2",
                                  command=self._toggle_auto)
        self.btn_auto.pack(side="left", padx=(8, 12))

        self.lbl_auto_desc = tk.Label(r1, text="Desativado",
                                      font=("Segoe UI", 8), fg=GRY, bg=CARD)
        self.lbl_auto_desc.pack(side="left")

        # Row 2: Limit + Interval + Apply
        r2 = tk.Frame(inn, bg=CARD)
        r2.pack(fill="x", pady=(0, 6))

        def field(parent_frame, label, var, width=5):
            tk.Label(parent_frame, text=label, font=("Segoe UI", 9),
                     fg=GRY, bg=CARD).pack(side="left")
            e = tk.Entry(parent_frame, textvariable=var, font=("Segoe UI", 9),
                         bg=C3, fg=WHT, insertbackground=WHT,
                         bd=0, width=width, justify="center",
                         highlightthickness=1, highlightbackground=BDR)
            e.pack(side="left", padx=(3, 6))
            return e

        self._v_limit    = tk.StringVar(value="{:.1f}".format(self.engine.limit_gb))
        self._v_interval = tk.StringVar(value=str(self.engine.interval_sec))

        field(r2, "Limite:", self._v_limit)
        tk.Label(r2, text="GB   ", font=("Segoe UI", 9), fg=GRY, bg=CARD).pack(side="left")
        field(r2, "Intervalo:", self._v_interval)
        tk.Label(r2, text="s   ", font=("Segoe UI", 9), fg=GRY, bg=CARD).pack(side="left")

        tk.Button(r2, text="Aplicar", font=("Segoe UI", 8),
                  fg=DRK, bg=NEON, bd=0, padx=10, pady=4,
                  cursor="hand2", command=self._apply_settings).pack(side="left")

        # Row 3: Checkboxes
        r3 = tk.Frame(inn, bg=CARD)
        r3.pack(fill="x", pady=(0, 4))

        self._v_filecache = tk.BooleanVar(value=self.engine.use_filecache)
        self._v_startup   = tk.BooleanVar(value=_is_startup_enabled())

        ck_style = dict(font=("Segoe UI", 9), fg=WHT, bg=CARD,
                        selectcolor=C3, activebackground=CARD,
                        activeforeground=WHT, bd=0, cursor="hand2",
                        command=self._apply_settings)

        tk.Checkbutton(r3, text=" Cache Disco (L5)", variable=self._v_filecache,
                       **ck_style).pack(side="left", padx=(0, 8))

        tk.Checkbutton(r3, text=" Iniciar com Windows", variable=self._v_startup,
                       **{**ck_style, "command": self._toggle_startup}).pack(side="left", padx=(0, 8))

        # Row 4: Whitelist display
        r4 = tk.Frame(inn, bg=CARD)
        r4.pack(fill="x", pady=(2, 0))

        tk.Label(r4, text="🛡 Protegidos:", font=("Segoe UI", 8),
                 fg=GRY, bg=CARD).pack(side="left")

        self.lbl_whitelist = tk.Label(r4, text="nenhum",
                                      font=("Consolas", 8), fg=ACCNT, bg=CARD,
                                      wraplength=350, justify="left")
        self.lbl_whitelist.pack(side="left", padx=(4, 0))

        self._refresh_auto_btn()
        self._refresh_whitelist_label()

    # ── Process List ──────────────────────────────────────────────────────────
    def _build_processes(self, p):
        card = self._card(p, expand=True)

        hdr = tk.Frame(card, bg=C2)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🔥  Top Consumidores de RAM (agrupados)",
                 font=("Segoe UI", 9, "bold"), fg=WHT, bg=C2,
                 pady=7, padx=12).pack(side="left")

        self.lbl_proc_time = tk.Label(hdr, text="",
                                      font=("Segoe UI", 7), fg=GRY, bg=C2)
        self.lbl_proc_time.pack(side="right", padx=10, pady=7)

        chdr = tk.Frame(card, bg=C3)
        chdr.pack(fill="x")
        tk.Label(chdr, text="  Processo                     Inst  RAM (MB)    Status",
                 font=("Consolas", 8, "bold"), fg=ACCNT, bg=C3,
                 pady=4, padx=8).pack(anchor="w")

        self.txt_procs = tk.Text(card, bg=CARD, fg=NEON, font=("Consolas", 9),
                                 bd=0, highlightthickness=0, height=8, wrap="none")
        self.txt_procs.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        self.txt_procs.config(state="disabled")

        # Context menu for whitelist (right-click)
        self._proc_menu = tk.Menu(self.root, tearoff=0,
                                   bg=CARD, fg=WHT, activebackground=C3,
                                   activeforeground=NEON, font=("Segoe UI", 9),
                                   bd=1, relief="flat")
        self._proc_menu.add_command(label="🛡 Proteger processo", command=self._whitelist_add)
        self._proc_menu.add_command(label="✕ Remover proteção", command=self._whitelist_remove)
        self.txt_procs.bind("<Button-3>", self._on_proc_right_click)

        # Store grouped process data for right-click reference
        self._grouped_procs = []

    # ── History ───────────────────────────────────────────────────────────────
    def _build_history(self, p):
        card = self._card(p, bottom_pad=14, expand=True)

        hdr  = tk.Frame(card, bg=C2)
        hdr.pack(fill="x")
        hrow = tk.Frame(hdr, bg=C2)
        hrow.pack(fill="x", pady=7, padx=12)
        tk.Label(hrow, text="📜  Log de Otimizações",
                 font=("Segoe UI", 9, "bold"), fg=WHT, bg=C2).pack(side="left")
        tk.Button(hrow, text="Limpar", font=("Segoe UI", 7),
                  fg=GRY, bg=C3, bd=0, padx=6, pady=1,
                  cursor="hand2", command=self._clear_history).pack(side="right")

        self.txt_hist = tk.Text(card, bg=CARD, fg=WHT, font=("Consolas", 10, "bold"),
                                bd=0, highlightthickness=0, height=5, wrap="none")
        self.txt_hist.pack(fill="both", expand=True, padx=8, pady=6)
        # Coloring tags
        self.txt_hist.tag_config("neon",  foreground=NEON)
        self.txt_hist.tag_config("warn",  foreground=WARN)
        self.txt_hist.tag_config("admin", foreground=BLU)
        self.txt_hist.config(state="disabled")

    # ── Helper ────────────────────────────────────────────────────────────────
    def _card(self, parent, bottom_pad=8, pad_v=None, expand=False):
        f = tk.Frame(parent, bg=CARD,
                     highlightbackground=BDR, highlightthickness=1)
        if expand:
            f.pack(fill="both", expand=True, padx=16, pady=(0, bottom_pad))
        else:
            f.pack(fill="x", padx=16, pady=(0, bottom_pad))
        return f

    # ── Settings Logic ────────────────────────────────────────────────────────
    def _toggle_auto(self):
        self.engine.auto_mode = not self.engine.auto_mode
        self._apply_settings()
        self._refresh_auto_btn()
        self._manage_pulse()

    def _refresh_auto_btn(self):
        if self.engine.auto_mode:
            self.btn_auto.config(text="ON", fg=DRK, bg=NEON)
            self.lbl_auto_desc.config(
                text="Adaptativo — base {}s (ajusta por pressão RAM)".format(
                    self.engine.interval_sec),
                fg=NEON)
        else:
            self.btn_auto.config(text="OFF", fg=WHT, bg="#1a1a30")
            self.lbl_auto_desc.config(text="Desativado", fg=GRY)

    def _apply_settings(self):
        try:
            self.engine.limit_gb = max(0.5, float(self._v_limit.get()))
        except Exception:
            self._v_limit.set("{:.1f}".format(self.engine.limit_gb))
        try:
            self.engine.interval_sec = max(10, int(self._v_interval.get()))
        except Exception:
            self._v_interval.set(str(self.engine.interval_sec))
        self.engine.use_filecache     = self._v_filecache.get()
        self._refresh_auto_btn()
        self._persist_config()

    def _toggle_startup(self):
        """Toggle 'Start with Windows' and update registry."""
        enabled = self._v_startup.get()
        _set_startup(enabled)
        self._persist_config()

    def _clear_history(self):
        self.txt_hist.config(state="normal")
        self.txt_hist.delete("1.0", tk.END)
        self.txt_hist.config(state="disabled")

    def _refresh_whitelist_label(self):
        """Update the whitelist display label."""
        wl = self.engine.whitelist
        if wl:
            self.lbl_whitelist.config(text=", ".join(sorted(wl)))
        else:
            self.lbl_whitelist.config(text="nenhum")

    # ── Whitelist Logic (Right-Click Menu) ────────────────────────────────────
    def _on_proc_right_click(self, event):
        """Show context menu on right-click in process list."""
        # Determine which line was clicked
        try:
            index = self.txt_procs.index("@{},{}".format(event.x, event.y))
            line_num = int(index.split(".")[0]) - 1
            if 0 <= line_num < len(self._grouped_procs):
                self._selected_proc = self._grouped_procs[line_num][0].lower()
                # Update menu labels based on whitelist status
                if self._selected_proc in self.engine.whitelist:
                    self._proc_menu.entryconfigure(0, state="disabled")
                    self._proc_menu.entryconfigure(1, state="normal")
                else:
                    self._proc_menu.entryconfigure(0, state="normal")
                    self._proc_menu.entryconfigure(1, state="disabled")
                self._proc_menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass

    def _whitelist_add(self):
        """Add selected process to whitelist."""
        if hasattr(self, '_selected_proc') and self._selected_proc:
            self.engine.whitelist.add(self._selected_proc)
            self._refresh_whitelist_label()
            self._persist_config()
            self.root.after(0, self._ui_procs)  # Refresh list to show shield

    def _whitelist_remove(self):
        """Remove selected process from whitelist."""
        if hasattr(self, '_selected_proc') and self._selected_proc:
            self.engine.whitelist.discard(self._selected_proc)
            self._refresh_whitelist_label()
            self._persist_config()
            self.root.after(0, self._ui_procs)

    # ── Pulsing Button (when auto is ON) ─────────────────────────────────────
    def _manage_pulse(self):
        if self.engine.auto_mode:
            self._pulse()
        else:
            if self._pulse_job:
                self.root.after_cancel(self._pulse_job)
                self._pulse_job = None
            if str(self.btn["state"]) == "normal":
                self.btn.config(bg=NEON)

    def _pulse(self):
        if not self.engine.auto_mode:
            return
        if not hasattr(self, '_pb'):
            self._pb = False
        self._pb = not self._pb
        if str(self.btn["state"]) == "normal":
            self.btn.config(bg=NE2 if self._pb else NEON)
        self._pulse_job = self.root.after(700, self._pulse)

    # ── Optimize Click ────────────────────────────────────────────────────────
    def _on_opt_click(self):
        self.engine.optimize_now()

    # ── Engine Events (cross-thread) ──────────────────────────────────────────
    def _on_engine_event(self, event, data):
        if event == "start":
            self.root.after(0, self._ui_start, data)
        elif event == "done":
            self.root.after(0, self._ui_done, data)

    def _ui_start(self, data):
        t = (data or {}).get("trigger", "?")
        self.btn.config(state="disabled",
                        text="⏳  OTIMIZANDO {} CAMADAS...".format(
                            "7" if IS_ADMIN else "3"),
                        bg=C3, fg=WARN)
        self.lbl_auto_desc.config(text="Otimizando ({})...".format(t), fg=WARN)

    def _ui_done(self, data):
        freed   = data.get("freed_mb",    0.0)
        cleaned = data.get("cleaned",     0)
        skipped = data.get("skipped",     0)
        runs    = data.get("total_runs",  0)
        total   = data.get("total_freed", 0.0)
        trigger = data.get("trigger",     "?")
        ts      = data.get("timestamp",   datetime.now())
        adm     = data.get("is_admin",    False)
        layers  = data.get("layers",      [])

        def fmt(mb):
            return "{:.2f} GB".format(mb / 1024) if mb >= 1024 else "{:.0f} MB".format(mb)

        freed_s = "-" + fmt(freed)
        total_s = fmt(total)

        # Update action labels
        self.lbl_last.config(
            text="Última: {}  ({} procs, {} skip)".format(freed_s, cleaned, skipped), fg=NEON)
        self.lbl_total.config(text="  |  Total: {}".format(total_s))
        self.lbl_runs.config(text="  |  Runs: {}".format(runs))

        # Update layers bar
        self.lbl_layers.config(text="  •  ".join(layers) if layers else "—")

        # Reset button
        self.btn.config(state="normal", text="⚡  OTIMIZAR MEMÓRIA AGORA",
                        bg=NEON, fg=DRK)
        self._refresh_auto_btn()
        self._manage_pulse()

        # History log entry
        adm_mark  = "★" if adm else " "
        trig_mark = "AUTO  " if trigger == "auto" else "MANUAL"
        line = "[{}] {} {} | {:>8} | {} trim {} skip | {}\n".format(
            ts.strftime("%H:%M:%S"), adm_mark, trig_mark,
            freed_s, cleaned, skipped, " ".join(layers[:3]))

        self.txt_hist.config(state="normal")
        self.txt_hist.insert("1.0", line, "neon" if freed > 0 else "warn")
        # Keep max 30 lines
        n_lines = int(self.txt_hist.index("end-1c").split(".")[0])
        if n_lines > 30:
            self.txt_hist.delete("31.0", tk.END)
        self.txt_hist.config(state="disabled")

        # v3.1: Toast notification when auto-mode optimizes in background
        if trigger == "auto" and self._tray and not self.root.winfo_viewable():
            try:
                self._tray.notify(
                    "MemOptima — {}".format(freed_s),
                    "{} processos otimizados, {} pulados".format(cleaned, skipped)
                )
            except Exception:
                pass

    # ── Live Monitor ──────────────────────────────────────────────────────────
    def _start_monitor(self):
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self):
        """Loop de monitoramento com dois intervalos distintos:
        - Métricas de RAM/swap: a cada 2s (leve — só lê contadores do kernel)
        - Lista de processos: a cada 10s (pesado — varre todos os processos)
          Separar esses intervalos elimina os picos de SSD a cada 2s.
        """
        _proc_tick = 0  # contador de ciclos para decidir quando atualizar processos
        while True:
            try:
                mem  = psutil.virtual_memory()
                self.root.after(0, self._ui_metrics, mem)

                # Atualizar lista de processos só a cada 5 ciclos (= 10s)
                # Ler RSS de todos os processos a cada 2s é o maior causador
                # de picos de I/O no SSD.
                _proc_tick += 1
                if _proc_tick >= 5:
                    _proc_tick = 0
                    self.root.after(0, self._ui_procs)
            except Exception:
                pass
            time.sleep(2)

    def _ui_metrics(self, mem):
        pct      = mem.percent
        used_gb  = mem.used      / (1024 ** 3)
        avail_gb = mem.available / (1024 ** 3)
        total_gb = mem.total     / (1024 ** 3)

        self.gauge.set_value(pct)
        self.sparkline.add(pct)

        self.lbl_used.config(text="{:.2f} GB".format(used_gb))
        self.lbl_free.config(text="{:.2f} GB".format(avail_gb))
        self.lbl_total.config(text="{:.2f} GB".format(total_gb))

        lim = self.engine.limit_gb
        if used_gb > lim:
            self.lbl_limit_status.config(
                text="⚠  {:.2f} GB > limite {:.1f} GB — otimização pendente".format(
                    used_gb, lim),
                fg=RED)
        else:
            self.lbl_limit_status.config(
                text="✓  {:.2f} GB dentro do limite de {:.1f} GB".format(
                    used_gb, lim),
                fg=NEON)



    def _ui_procs(self):
        """Atualiza a lista de processos agrupados por nome.
        v3.1: Processos duplicados (ex: chrome.exe ×12) são agregados em uma linha.
        Processos na whitelist exibem 🛡 como indicador.
        """
        raw_procs = []
        count = 0
        for p in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                info = p.info
                name = info['name'] or "?"
                if name.lower() in SYSTEM_PROCS:
                    continue
                minfo = info['memory_info']
                if minfo:
                    mb = minfo.rss / (1024 * 1024)
                    raw_procs.append((name, mb, info['pid']))
                    count += 1
                    if count >= 50:   # Limitar a 50 processos para evitar I/O excessivo
                        break
            except Exception:
                continue

        # v3.1: Group by process name
        grouped = {}
        for name, mb, pid in raw_procs:
            key = name.lower()
            if key in grouped:
                grouped[key]['mb'] += mb
                grouped[key]['count'] += 1
            else:
                grouped[key] = {'name': name, 'mb': mb, 'count': 1}

        # Convert to sorted list: (display_name, total_mb, instance_count)
        display = [(d['name'], d['mb'], d['count']) for d in grouped.values()]
        display.sort(key=lambda x: x[1], reverse=True)

        # Store for right-click reference
        self._grouped_procs = display

        self.txt_procs.config(state="normal")
        self.txt_procs.delete("1.0", tk.END)

        if display:
            max_mb = max(display[0][1], 1)
            for name, mb, inst_count in display[:20]:
                bar_len = int((mb / max_mb) * 10)
                bar = "█" * bar_len + "░" * (10 - bar_len)
                # Show shield icon for whitelisted processes
                shield = "🛡" if name.lower() in self.engine.whitelist else "  "
                inst_str = "×{}".format(inst_count) if inst_count > 1 else "  "
                line = "  {:<25} {:>3}  {:>8.1f}  {} {}\n".format(
                    name, inst_str, mb, bar, shield)
                self.txt_procs.insert(tk.END, line)

        self.lbl_proc_time.config(text=datetime.now().strftime("%H:%M:%S"))
        self.txt_procs.config(state="disabled")


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM TRAY
# ═══════════════════════════════════════════════════════════════════════════════
def setup_tray(app: MemOptimaApp):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    # Generate icon
    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, 62, 62], fill=(8, 8, 15, 255))
    draw.ellipse([2, 2, 62, 62], outline=(0, 255, 136, 255), width=4)
    draw.line([(14, 50), (14, 14), (32, 36), (50, 14), (50, 50)],
              fill=(0, 255, 136, 255), width=6)

    def _show(icon, item):
        app.root.after(0, app.restore)

    def _optimize(icon, item):
        app.engine.optimize_now()

    def _toggle_auto(icon, item):
        app.engine.auto_mode = not app.engine.auto_mode
        app.root.after(0, app._refresh_auto_btn)
        app.root.after(0, app._manage_pulse)

    def _exit(icon, item):
        app._exit()

    def _auto_lbl(item):
        return "Auto-Modo: {}".format("ON ✓" if app.engine.auto_mode else "OFF")

    menu = pystray.Menu(
        pystray.MenuItem("Abrir MemOptima",   _show,         default=True),
        pystray.MenuItem("⚡ Otimizar Agora", _optimize),
        pystray.MenuItem(_auto_lbl,            _toggle_auto),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sair",               _exit),
    )

    icon = pystray.Icon("MemOptima", img, "MemOptima v3.1 ULTIMATE", menu)
    app.set_tray(icon)
    icon.run_detached()
    return icon


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    cfg    = _load_config()
    engine = OptimizationEngine(cfg)

    root = tk.Tk()
    app  = MemOptimaApp(root, engine)

    tray = setup_tray(app)

    root.mainloop()

    engine.stop()
    if tray:
        try:
            tray.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
