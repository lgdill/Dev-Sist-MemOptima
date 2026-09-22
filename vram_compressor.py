# -*- coding: utf-8 -*-
"""
MemOptima VRAM — Virtual Memory (Swap/Pagefile) Optimizer
Monitora e tenta reduzir a pressão na memória virtual do Windows,
evitando que o sistema use excessivamente o arquivo de paginação (Swap).

Foco:
  C1: Page Combine   — Deduplicação de páginas idênticas (libera RAM, reduzindo a necessidade de Swap)
  C2: Purge Standby  — Purga a Standby List, liberando RAM física de arquivos cacheados

Roda de forma 100% independente do memoptima.py.
"""

import os
import sys
import time
import math
import threading
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
    try:
        IS_ADMIN = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        IS_ADMIN = False

# ═══════════════════════════════════════════════════════════════════════════════
# WINDOWS NATIVE API SETUP
# ═══════════════════════════════════════════════════════════════════════════════
if IS_WINDOWS:
    _adv = ctypes.WinDLL('advapi32', use_last_error=True)
    _k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _nt  = ctypes.WinDLL('ntdll',    use_last_error=True)

    _GetCurrentProcess     = _k32.GetCurrentProcess
    _GetCurrentProcess.restype = wintypes.HANDLE

    _CloseHandle           = _k32.CloseHandle
    _CloseHandle.restype   = wintypes.BOOL
    _CloseHandle.argtypes  = [wintypes.HANDLE]

    _NtSysInfo             = _nt.NtSetSystemInformation
    _NtSysInfo.restype     = ctypes.c_long
    _NtSysInfo.argtypes    = [ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]

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

    # Constants
    TOKEN_ADJUST          = 0x0020 | 0x0008
    SE_PRIV_ENABLED       = 0x00000002
    _SYSINFO_MEMLIST      = 80
    _MEM_PURGE_STANDBY    = 4
    _MEM_COMBINE_PAGES    = 5

# Processos críticos
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
        for priv in ["SeProfileSingleProcessPrivilege", "SeLockMemoryPrivilege"]:
            luid = LUID()
            if _LookupPriv(None, priv, ctypes.byref(luid)):
                tp = TokenPriv()
                tp.Count = 1
                tp.Privs[0].Luid = luid
                tp.Privs[0].Attributes = SE_PRIV_ENABLED
                _AdjustToken(hToken, False, ctypes.byref(tp), ctypes.sizeof(tp), None, None)
        _CloseHandle(hToken)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# DESIGN TOKENS — Dark Ocean / Violet Accent Theme
# ═══════════════════════════════════════════════════════════════════════════════
BG      = "#060913"   
CARD    = "#0b1021"   
C2      = "#11182c"   
C3      = "#1a1535"   
WHT     = "#f8fafc"   
GRY     = "#64748b"   
NEON    = "#a78bfa"   # Violet neon (Primary)
NE2     = "#7c5cdb"   
NE_DIM  = "#1e1435"   
ACCNT   = "#00d2ff"   
WARN    = "#f59e0b"   
RED     = "#f43f5e"   
BLU     = "#38bdf8"   
AC_DIM  = "#0a1035"   
BDR     = "#1e293b"   
DRK     = "#060913"   
GRN     = "#00e676"   


# ═══════════════════════════════════════════════════════════════════════════════
# CIRCULAR GAUGE WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class CircularGauge(tk.Canvas):
    def __init__(self, parent, size=190, **kwargs):
        super().__init__(parent, width=size, height=size, bg=CARD, highlightthickness=0, **kwargs)
        self._sz  = size
        self._cx  = size / 2
        self._cy  = size / 2
        self._r   = size * 0.40
        self._lw  = int(size * 0.075)

        self._target  = 0.0
        self._current = 0.0
        self._anim_id = None
        self._label   = "SWAP"
        self._draw(0.0)

    def set_label(self, label: str):
        self._label = label
        self._draw(self._current)

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

        gr = r + lw + 4
        self.create_oval(cx - gr, cy - gr, cx + gr, cy + gr, outline=NE_DIM, width=1)
        self.create_arc(x0, y0, x1, y1, start=135, extent=-270, style=tk.ARC, outline=NE_DIM, width=lw)

        color  = self._color(pct)
        extent = -(pct / 100.0 * 270.0)
        if abs(extent) > 0.5:
            self.create_arc(x0, y0, x1, y1, start=135, extent=extent, style=tk.ARC, outline=color, width=lw)

        fsz = int(self._sz * 0.115)
        self.create_text(cx, cy - fsz * 0.55, text="{:.1f}%".format(pct), font=("Segoe UI", fsz, "bold"), fill=WHT)
        self.create_text(cx, cy + fsz * 0.60, text=self._label, font=("Segoe UI", int(self._sz * 0.055)), fill=GRY)

        if pct > 1:
            angle_deg = 135 - (pct / 100 * 270)
            angle_rad = math.radians(angle_deg)
            tip_x = cx + r * math.cos(angle_rad)
            tip_y = cy - r * math.sin(angle_rad)
            dr = lw * 0.6
            self.create_oval(tip_x - dr, tip_y - dr, tip_x + dr, tip_y + dr, fill=color, outline="")


# ═══════════════════════════════════════════════════════════════════════════════
# SPARKLINE WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class Sparkline(tk.Canvas):
    def __init__(self, parent, height=52, maxpoints=90, line_color=None, fill_color=None, **kwargs):
        super().__init__(parent, height=height, bg=CARD, highlightthickness=0, **kwargs)
        self._width  = 100
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

        step = w / (n - 1)
        pts  = []
        for i, v in enumerate(data):
            x = i * step
            y = pad + h - (v / 100.0) * h
            pts.append((x, y))

        poly = [(0, self._height)] + pts + [(w, self._height)]
        flat = [c for p in poly for c in p]
        self.create_polygon(flat, fill=self._fill_c, outline="")

        flat_pts = [c for p in pts for c in p]
        self.create_line(flat_pts, fill=self._line_c, width=2, smooth=True)

        lx, ly = pts[-1]
        self.create_oval(lx - 4, ly - 4, lx + 4, ly + 4, fill=self._line_c, outline=BG, width=2)

        for pct_mark in [25, 50, 75, 100]:
            yy = pad + h - (pct_mark / 100.0) * h
            self.create_line(0, yy, w, yy, fill=BDR, dash=(2, 6))
            self.create_text(w - 3, yy, text="{}%".format(pct_mark), font=("Consolas", 7), fill=GRY, anchor="e")


# ═══════════════════════════════════════════════════════════════════════════════
# OPTIMIZATION ENGINE 
# ═══════════════════════════════════════════════════════════════════════════════
class VirtualMemoryEngine:
    def __init__(self):
        self.limit_gb     = 4.0
        self.interval_sec = 60
        self.auto_mode    = False

        self.total_runs       = 0
        self.layers_fired     = []
        self.running          = True
        self._optimizing      = False
        self._callbacks       = []
        self._last_ts         = 0.0

        _enable_privileges()
        threading.Thread(target=self._auto_loop, daemon=True).start()

    def register_callback(self, cb):
        self._callbacks.append(cb)

    def _emit(self, event, data=None):
        for cb in self._callbacks:
            try: cb(event, data)
            except: pass

    def stop(self):
        self.running = False

    def _auto_loop(self):
        while self.running:
            time.sleep(5)
            if not self.auto_mode or self._optimizing:
                continue
            try:
                mem     = psutil.swap_memory()
                used_gb = mem.used / (1024 ** 3)
                elapsed = time.time() - self._last_ts

                if used_gb > self.limit_gb or elapsed >= self.interval_sec:
                    self._run("auto")
            except Exception:
                pass

    def optimize_now(self):
        if not self._optimizing:
            threading.Thread(target=self._run, args=("manual",), daemon=True).start()

    def _run(self, trigger: str):
        if self._optimizing: return
        self._optimizing = True
        self._emit("start", {"trigger": trigger})
        try:
            self._do_optimize(trigger)
        finally:
            self._optimizing = False

    def _do_optimize(self, trigger: str):
        if not IS_WINDOWS:
            self._emit("done", {"trigger": trigger, "layers": [], "total_runs": 0, "is_admin": False, "timestamp": datetime.now()})
            return

        layers = []

        # C1: Page Combine (Deduplicação da RAM - zero I/O)
        try:
            cmd = ctypes.c_int(_MEM_COMBINE_PAGES)
            st  = _NtSysInfo(_SYSINFO_MEMLIST, ctypes.byref(cmd), ctypes.sizeof(cmd))
            if st == 0: layers.append("C1: PageCombine")
        except Exception:
            pass

        # C2: Purge Standby List (Libera caches da RAM)
        if IS_ADMIN:
            try:
                cmd = ctypes.c_int(_MEM_PURGE_STANDBY)
                st  = _NtSysInfo(_SYSINFO_MEMLIST, ctypes.byref(cmd), ctypes.sizeof(cmd))
                if st == 0: layers.append("C2: PurgeStandby")
            except Exception:
                pass

        self.total_runs  += 1
        self._last_ts    = time.time()

        self._emit("done", {
            "trigger": trigger,
            "layers": layers,
            "total_runs": self.total_runs,
            "is_admin": IS_ADMIN,
            "timestamp": datetime.now(),
        })


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════
class VirtualMemoryApp:
    def __init__(self, root: tk.Tk, engine: VirtualMemoryEngine):
        self.root   = root
        self.engine = engine
        self._tray  = None
        self._pulse_job = None
        self.is_fullscreen = False

        engine.register_callback(self._on_engine_event)
        self._config_window()
        self._build_ui()
        self._start_monitor()

    def _config_window(self):
        self.root.title("VirtualRAM Compressor — MemOptima VRAM Add-on")
        self.root.geometry("600x900")
        self.root.minsize(500, 750)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
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
        if self._tray: self.root.withdraw()
        else:
            if messagebox.askyesno("Sair", "Encerrar o Otimizador de Memória Virtual?"):
                self._exit()

    def _exit(self):
        self.engine.stop()
        if self._tray:
            try: self._tray.stop()
            except: pass
        self.root.after(0, self.root.destroy)

    def set_tray(self, icon):
        self._tray = icon

    def restore(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

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

    def _build_header(self, p):
        f = tk.Frame(p, bg=BG)
        f.pack(fill="x", pady=(16, 6))

        row = tk.Frame(f, bg=BG)
        row.pack()

        tk.Label(row, text="MemOptima", font=("Segoe UI", 28, "bold"), fg=WHT, bg=BG).pack(side="left")
        tk.Label(row, text=" VRAM", font=("Segoe UI", 28, "bold"), fg=NEON, bg=BG).pack(side="left")

        badge_c = BLU if IS_ADMIN else WARN
        badge_t = "★ ADMIN" if IS_ADMIN else "⚠ USER"
        tk.Label(row, text="  {}  ".format(badge_t), font=("Segoe UI", 8, "bold"), fg=DRK, bg=badge_c).pack(side="left", padx=(10, 0), pady=(14, 0))

        fs_btn = tk.Button(row, text="⛶", font=("Segoe UI", 12), fg=GRY, bg=BG, bd=0, cursor="hand2", command=self.toggle_fullscreen, activebackground=BG, activeforeground=WHT)
        fs_btn.pack(side="left", padx=(10, 0), pady=(12, 0))

        tk.Label(f, text="Monitoramento do Arquivo de Paginação (Swap / Disco)", font=("Segoe UI", 9), fg=GRY, bg=BG).pack()

        if not IS_ADMIN:
            tk.Label(f, text="Execute como Administrador para purgar a Standby List", font=("Segoe UI", 8), fg=WARN, bg=BG).pack(pady=(2, 0))

    def _build_metrics(self, p):
        card = self._card(p)
        inn  = tk.Frame(card, bg=CARD)
        inn.pack(fill="x", padx=16, pady=14)

        left = tk.Frame(inn, bg=CARD)
        left.pack(side="left", anchor="n")
        self.gauge = CircularGauge(left, size=188)
        self.gauge.set_label("SWAP USADO")
        self.gauge.pack()

        right = tk.Frame(inn, bg=CARD)
        right.pack(side="left", padx=(18, 0), fill="y", expand=True)

        tk.Label(right, text="Arquivo de Paginação (Swap no Disco)", font=("Segoe UI", 11, "bold"), fg=NEON, bg=CARD).pack(anchor="w")

        self.lbl_used  = self._stat_row(right, "Usado :")
        self.lbl_free  = self._stat_row(right, "Livre :")
        self.lbl_total = self._stat_row(right, "Total :")

        sep = tk.Frame(right, bg=BDR, height=1)
        sep.pack(fill="x", pady=6)

        self.lbl_limit_status = tk.Label(right, text="", font=("Segoe UI", 9, "bold"), fg=NEON, bg=CARD)
        self.lbl_limit_status.pack(anchor="w")

        spark_f = tk.Frame(card, bg=CARD)
        spark_f.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(spark_f, text="Histórico Pagefile (Swap) — últimos 3 min", font=("Segoe UI", 7), fg=GRY, bg=CARD).pack(anchor="w")
        self.sparkline = Sparkline(spark_f, height=44)
        self.sparkline.pack(fill="x", expand=True)

    def _stat_row(self, parent, label):
        f = tk.Frame(parent, bg=CARD)
        f.pack(anchor="w", pady=3)
        tk.Label(f, text=label, font=("Consolas", 9), fg=GRY, bg=CARD, width=9, anchor="w").pack(side="left")
        lbl = tk.Label(f, text="--- GB", font=("Consolas", 12, "bold"), fg=WHT, bg=CARD)
        lbl.pack(side="left")
        return lbl

    def _build_action(self, p):
        card = self._card(p)
        inn  = tk.Frame(card, bg=CARD)
        inn.pack(fill="x", padx=16, pady=14)

        self.btn = tk.Button(inn, text="🗜  OTIMIZAR MEMÓRIA VIRTUAL", font=("Segoe UI", 13, "bold"),
                             fg=DRK, bg=NEON, activebackground=NE2, activeforeground=DRK, bd=0, cursor="hand2",
                             relief="flat", padx=20, pady=12, command=self.engine.optimize_now)
        self.btn.pack(fill="x")
        self.btn.bind("<Enter>", lambda e: self.btn.config(bg=NE2) if str(self.btn["state"]) == "normal" else None)
        self.btn.bind("<Leave>", lambda e: self.btn.config(bg=NEON) if str(self.btn["state"]) == "normal" else None)

        stats_f = tk.Frame(inn, bg=CARD)
        stats_f.pack(fill="x", pady=(10, 0))

        self.lbl_last  = tk.Label(stats_f, text="Última:  —", font=("Segoe UI", 9), fg=WHT, bg=CARD)
        self.lbl_last.pack(side="left")

        self.lbl_runs  = tk.Label(stats_f, text="  |  Runs: 0", font=("Segoe UI", 9), fg=GRY, bg=CARD)
        self.lbl_runs.pack(side="left")

    def _build_layers_bar(self, p):
        card = self._card(p, pad_v=0)
        f = tk.Frame(card, bg=C2)
        f.pack(fill="x", padx=0, pady=0)
        tk.Label(f, text="CAMADAS ATIVAS:", font=("Consolas", 7, "bold"), fg=GRY, bg=C2, pady=5, padx=10).pack(side="left")
        self.lbl_layers = tk.Label(f, text="—", font=("Consolas", 7), fg=NEON, bg=C2, pady=5, wraplength=380, justify="left")
        self.lbl_layers.pack(side="left", padx=4)

    def _build_settings(self, p):
        card = self._card(p)
        hdr = tk.Frame(card, bg=C2)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙  Auto-Modo & Configurações", font=("Segoe UI", 9, "bold"), fg=WHT, bg=C2, pady=7, padx=12).pack(side="left")

        inn = tk.Frame(card, bg=CARD)
        inn.pack(fill="x", padx=14, pady=10)

        r1 = tk.Frame(inn, bg=CARD)
        r1.pack(fill="x", pady=(0, 8))
        tk.Label(r1, text="Auto-Modo:", font=("Segoe UI", 10, "bold"), fg=WHT, bg=CARD).pack(side="left")

        self.btn_auto = tk.Button(r1, text="OFF", font=("Segoe UI", 9, "bold"), fg=WHT, bg=C3, bd=0, padx=18, pady=5, cursor="hand2", command=self._toggle_auto)
        self.btn_auto.pack(side="left", padx=(8, 12))

        self.lbl_auto_desc = tk.Label(r1, text="Desativado", font=("Segoe UI", 8), fg=GRY, bg=CARD)
        self.lbl_auto_desc.pack(side="left")

        r2 = tk.Frame(inn, bg=CARD)
        r2.pack(fill="x", pady=(0, 6))

        tk.Label(r2, text="Limite (GB):", font=("Segoe UI", 9), fg=GRY, bg=CARD).pack(side="left")
        self._v_limit = tk.StringVar(value="4.0")
        tk.Entry(r2, textvariable=self._v_limit, font=("Segoe UI", 9), bg=C3, fg=WHT, bd=0, width=5, justify="center").pack(side="left", padx=(3, 10))

        tk.Label(r2, text="Intervalo (s):", font=("Segoe UI", 9), fg=GRY, bg=CARD).pack(side="left")
        self._v_interval = tk.StringVar(value="60")
        tk.Entry(r2, textvariable=self._v_interval, font=("Segoe UI", 9), bg=C3, fg=WHT, bd=0, width=5, justify="center").pack(side="left", padx=(3, 10))

        tk.Button(r2, text="Aplicar", font=("Segoe UI", 8), fg=DRK, bg=NEON, bd=0, padx=10, pady=4, cursor="hand2", command=self._apply_settings).pack(side="left")

    def _build_processes(self, p):
        card = self._card(p, expand=True)

        hdr = tk.Frame(card, bg=C2)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🔥  Top 8 — Consumidores de Memória Virtual (VMS)", font=("Segoe UI", 9, "bold"), fg=WHT, bg=C2, pady=7, padx=12).pack(side="left")
        
        self.lbl_proc_time = tk.Label(hdr, text="", font=("Segoe UI", 7), fg=GRY, bg=C2)
        self.lbl_proc_time.pack(side="right", padx=10, pady=7)

        chdr = tk.Frame(card, bg=C3)
        chdr.pack(fill="x")
        tk.Label(chdr, text="  Processo                          VMS (MB)      PID", font=("Consolas", 8, "bold"), fg=ACCNT, bg=C3, pady=4, padx=8).pack(anchor="w")

        self.txt_procs = tk.Text(card, bg=CARD, fg=NEON, font=("Consolas", 9), bd=0, highlightthickness=0, height=8, wrap="none")
        self.txt_procs.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        self.txt_procs.config(state="disabled")

    def _build_history(self, p):
        card = self._card(p, bottom_pad=14, expand=True)

        hdr  = tk.Frame(card, bg=C2)
        hdr.pack(fill="x")
        hrow = tk.Frame(hdr, bg=C2)
        hrow.pack(fill="x", pady=7, padx=12)
        tk.Label(hrow, text="📜  Log de Otimizações de Swap", font=("Segoe UI", 9, "bold"), fg=WHT, bg=C2).pack(side="left")
        tk.Button(hrow, text="Limpar", font=("Segoe UI", 7), fg=GRY, bg=C3, bd=0, padx=6, pady=1, cursor="hand2", command=self._clear_history).pack(side="right")

        self.txt_hist = tk.Text(card, bg=CARD, fg=WHT, font=("Consolas", 10, "bold"), bd=0, highlightthickness=0, height=5, wrap="none")
        self.txt_hist.pack(fill="both", expand=True, padx=8, pady=6)
        self.txt_hist.tag_config("neon",  foreground=NEON)
        self.txt_hist.tag_config("warn",  foreground=WARN)
        self.txt_hist.tag_config("admin", foreground=BLU)
        self.txt_hist.config(state="disabled")

    def _card(self, parent, bottom_pad=8, pad_v=None, expand=False):
        f = tk.Frame(parent, bg=CARD, highlightbackground=BDR, highlightthickness=1)
        if expand: f.pack(fill="both", expand=True, padx=16, pady=(0, bottom_pad))
        else: f.pack(fill="x", padx=16, pady=(0, bottom_pad))
        return f

    def _toggle_auto(self):
        self.engine.auto_mode = not self.engine.auto_mode
        self._apply_settings()
        self._refresh_auto_btn()
        self._manage_pulse()

    def _refresh_auto_btn(self):
        if self.engine.auto_mode:
            self.btn_auto.config(text="ON", fg=DRK, bg=NEON)
            self.lbl_auto_desc.config(text="Ativo — Swap > {:.1f} GB ou a cada {}s".format(self.engine.limit_gb, self.engine.interval_sec), fg=NEON)
        else:
            self.btn_auto.config(text="OFF", fg=WHT, bg=C3)
            self.lbl_auto_desc.config(text="Desativado", fg=GRY)

    def _apply_settings(self):
        try: self.engine.limit_gb = max(0.5, float(self._v_limit.get()))
        except Exception: self._v_limit.set("{:.1f}".format(self.engine.limit_gb))
        try: self.engine.interval_sec = max(10, int(self._v_interval.get()))
        except Exception: self._v_interval.set(str(self.engine.interval_sec))
        self._refresh_auto_btn()

    def _clear_history(self):
        self.txt_hist.config(state="normal")
        self.txt_hist.delete("1.0", tk.END)
        self.txt_hist.config(state="disabled")

    def _manage_pulse(self):
        if self.engine.auto_mode: self._pulse()
        else:
            if self._pulse_job:
                self.root.after_cancel(self._pulse_job)
                self._pulse_job = None
            if str(self.btn["state"]) == "normal": self.btn.config(bg=NEON)

    def _pulse(self):
        if not self.engine.auto_mode: return
        if not hasattr(self, '_pb'): self._pb = False
        self._pb = not self._pb
        if str(self.btn["state"]) == "normal":
            self.btn.config(bg=NE2 if self._pb else NEON)
        self._pulse_job = self.root.after(700, self._pulse)

    def _on_engine_event(self, event, data):
        if event == "start": self.root.after(0, self._ui_start, data)
        elif event == "done": self.root.after(0, self._ui_done, data)

    def _ui_start(self, data):
        t = (data or {}).get("trigger", "?")
        self.btn.config(state="disabled", text="⏳  OTIMIZANDO VIRTUAL...", bg=C3, fg=WARN)
        self.lbl_auto_desc.config(text="Otimizando ({})...".format(t), fg=WARN)

    def _ui_done(self, data):
        runs    = data.get("total_runs",  0)
        trigger = data.get("trigger",     "?")
        ts      = data.get("timestamp",   datetime.now())
        adm     = data.get("is_admin",    False)
        layers  = data.get("layers",      [])

        self.lbl_last.config(text="Última: {}".format(ts.strftime("%H:%M:%S")), fg=NEON)
        self.lbl_runs.config(text="  |  Runs: {}".format(runs))
        self.lbl_layers.config(text="  •  ".join(layers) if layers else "—")

        self.btn.config(state="normal", text="🗜  OTIMIZAR MEMÓRIA VIRTUAL", bg=NEON, fg=DRK)
        self._refresh_auto_btn()
        self._manage_pulse()

        adm_mark  = "★" if adm else " "
        trig_mark = "AUTO  " if trigger == "auto" else "MANUAL"
        line = "[{}] {} {} | {}\n".format(ts.strftime("%H:%M:%S"), adm_mark, trig_mark, " ".join(layers[:3]))

        self.txt_hist.config(state="normal")
        self.txt_hist.insert("1.0", line, "neon")
        n_lines = int(self.txt_hist.index("end-1c").split(".")[0])
        if n_lines > 30: self.txt_hist.delete("31.0", tk.END)
        self.txt_hist.config(state="disabled")

    def _start_monitor(self):
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self):
        _proc_tick = 0
        while True:
            try:
                mem = psutil.swap_memory()
                self.root.after(0, self._ui_metrics, mem)
                
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
        avail_gb = mem.free      / (1024 ** 3)
        total_gb = mem.total     / (1024 ** 3)

        self.gauge.set_value(pct)
        self.sparkline.add(pct)

        self.lbl_used.config(text="{:.2f} GB".format(used_gb))
        self.lbl_free.config(text="{:.2f} GB".format(avail_gb))
        self.lbl_total.config(text="{:.2f} GB".format(total_gb))

        lim = self.engine.limit_gb
        if used_gb > lim:
            self.lbl_limit_status.config(text="⚠  {:.2f} GB > limite {:.1f} GB — swap alto".format(used_gb, lim), fg=RED)
        else:
            self.lbl_limit_status.config(text="✓  {:.2f} GB dentro do limite de {:.1f} GB".format(used_gb, lim), fg=NEON)

    def _ui_procs(self):
        procs = []
        count = 0
        for p in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                info = p.info
                name = info['name'] or "?"
                if name.lower() in SYSTEM_PROCS: continue
                minfo = info['memory_info']
                if minfo and hasattr(minfo, 'vms'):
                    mb = minfo.vms / (1024 * 1024)
                    procs.append((name, mb, info['pid']))
                    count += 1
                    if count >= 50: break
            except Exception:
                continue
        procs.sort(key=lambda x: x[1], reverse=True)

        self.txt_procs.config(state="normal")
        self.txt_procs.delete("1.0", tk.END)
        if procs:
            max_vms = max(procs[0][1], 1)
            for i, (name, mb, pid) in enumerate(procs[:30]):
                bar_len = int((mb / max_vms) * 12)
                bar = "█" * bar_len + "░" * (12 - bar_len)
                line = "  {:<28}  {:>9.1f}  {:>8}  {}\n".format(name, mb, pid, bar)
                self.txt_procs.insert(tk.END, line)
        self.lbl_proc_time.config(text=datetime.now().strftime("%H:%M:%S"))
        self.txt_procs.config(state="disabled")


# ═══════════════════════════════════════════════════════════════════════════════
def setup_tray(app: VirtualMemoryApp):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError: return None

    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, 62, 62], fill=(8, 6, 20, 255))
    draw.ellipse([2, 2, 62, 62], outline=(167, 139, 250, 255), width=4)
    draw.line([(16, 16), (32, 32)], fill=(167, 139, 250, 255), width=5)
    draw.line([(48, 16), (32, 32)], fill=(167, 139, 250, 255), width=5)
    draw.line([(16, 48), (32, 32)], fill=(167, 139, 250, 255), width=5)
    draw.line([(48, 48), (32, 32)], fill=(167, 139, 250, 255), width=5)

    def _show(icon, item): app.root.after(0, app.restore)
    def _compress(icon, item): app.engine.optimize_now()
    def _toggle_auto(icon, item):
        app.engine.auto_mode = not app.engine.auto_mode
        app.root.after(0, app._refresh_auto_btn)
        app.root.after(0, app._manage_pulse)
    def _exit(icon, item): app._exit()
    def _auto_lbl(item): return "Auto-Modo: {}".format("ON ✓" if app.engine.auto_mode else "OFF")

    menu = pystray.Menu(
        pystray.MenuItem("Abrir VirtualRAM Compressor", _show, default=True),
        pystray.MenuItem("🗜 Otimizar Swap", _compress),
        pystray.MenuItem(_auto_lbl, _toggle_auto),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sair", _exit),
    )

    icon = pystray.Icon("VRAMCompressor", img, "MemOptima VRAM", menu)
    app.set_tray(icon)
    icon.run_detached()
    return icon


def main():
    engine = VirtualMemoryEngine()
    root = tk.Tk()
    app  = VirtualMemoryApp(root, engine)
    tray = setup_tray(app)
    root.mainloop()
    engine.stop()
    if tray:
        try: tray.stop()
        except: pass

if __name__ == "__main__":
    main()
