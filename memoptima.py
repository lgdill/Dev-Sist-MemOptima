# -*- coding: utf-8 -*-
"""
MemOptima v3.2 — Maximum RAM Optimizer for Windows
7-Layer memory compression using all available native Windows APIs.
Circular gauge, sparkline history, system tray — always running.

v3.2 Improvements over v3.1:
  - [FIX]     config.json escrito atomicamente (write-tmp + rename) → RNF12
  - [FIX]     _pb inicializado em __init__ (anti-padrão hasattr removido)
  - [FIX]     _on_close: comportamento consistente com/sem pystray
  - [FEAT]    Log de otimizações persistido em optimization_log.jsonl (carregado na abertura)
  - [FEAT]    Countdown visual para próxima otimização automática
  - [FEAT]    CPU% exibida na lista de processos da UI
  - [FEAT]    Scrollbar na lista de processos e no log
  - [REFACTOR] CircularGauge, Sparkline extraídos para shared/widgets.py
  - [REFACTOR] ctypes/win_api extraídos para shared/win_api.py
  - [REFACTOR] Design tokens extraídos para shared/design.py
  - [REFACTOR] Config/log extraídos para shared/config.py
"""

import os
import sys
import time
import threading
import subprocess
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import psutil

# ── Shared modules ─────────────────────────────────────────────────────────────
from shared.design import (
    BG, CARD, C2, C3, WHT, GRY, NEON, NE2, NE_DIM,
    ACCNT, WARN, RED, BLU, AC_DIM, BDR, DRK,
)
from shared.widgets import CircularGauge, Sparkline
from shared.config import load_config, save_config, append_log, load_log
from shared.win_api import (
    IS_WINDOWS, IS_ADMIN,
    SYSTEM_PROCS,
    _enable_privileges, _get_foreground_pid,
    _OpenProcess, _CloseHandle, _GetCurrentProcess,
    _SetWSEx, _SetFileCache, _EmptyWS, _NtSysInfo,
    PROC_ACCESS, _SIZE_MAX, _SYSINFO_MEMLIST,
    _MEM_EMPTY_ALL_WS, _MEM_PURGE_STANDBY, _MEM_COMBINE_PAGES,
    _FILECACHE_MIN,
)

# ── Windows-only imports (registry) ────────────────────────────────────────────
if IS_WINDOWS:
    import winreg
    import ctypes

# ═══════════════════════════════════════════════════════════════════════════════
# STARTUP WITH WINDOWS (Registry)
# ═══════════════════════════════════════════════════════════════════════════════
_STARTUP_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
_STARTUP_NAME = "MemOptima"


def _is_startup_enabled() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, _STARTUP_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _set_startup(enabled: bool) -> None:
    if not IS_WINDOWS:
        return
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_KEY, 0, winreg.KEY_SET_VALUE)
        if enabled:
            exe    = sys.executable
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
# OPTIMIZATION ENGINE — 7 LAYERS (v3.2 Smart)
# ═══════════════════════════════════════════════════════════════════════════════
class OptimizationEngine:
    """
    7-Layer RAM optimization engine (v3.2 Smart):
      Layer 0:  Enable Windows privileges (SeDebug, SeIncreaseQuota, etc.)
      Layer 1:  NtSetSystemInformation(MemoryEmptyWorkingSet) — system-wide (admin)
      Layer 2b: EmptyWorkingSet + SetProcessWorkingSetSizeEx — per process
                ✓ Smart Trim: skips processes with CPU > 2%
                ✓ Foreground Protection: skips the active window's process
                ✓ Whitelist: skips user-protected processes
                ✓ Anti-Thrashing: skips processes with high page fault rate
      Layer 4:  NtSetSystemInformation(MemoryPurgeStandbyList) — admin
      Layer 5:  SetSystemFileCacheSize(256MB) — reduce file cache — admin
      Layer 6:  NtSetSystemInformation(MemoryCombinePhysicalMemory) — admin, Win8+
    """

    def __init__(self, config: dict):
        self.limit_gb       = config.get("limit_gb", 4.0)
        self.interval_sec   = config.get("interval_sec", 60)
        self.auto_mode      = config.get("auto_mode", True)
        self.use_filecache  = config.get("use_filecache", True)
        self.whitelist      = set(config.get("whitelist", []))
        # [FIX v3.3] swap_lock_gb agora lido do config (antes era hardcoded como 4.0)
        self.swap_lock_gb   = float(config.get("swap_lock_gb", 4.0))

        self.total_freed_mb  = 0.0
        self.total_runs      = 0
        self.layers_fired    = []
        self.running         = True
        self._optimizing     = False
        self._lock           = threading.Lock()
        self._callbacks      = []
        self._last_ts        = 0.0
        self._last_pf        = {}

        # Expose countdown info for UI
        self.next_auto_in_sec: float = 0.0
        self._effective_interval: float = float(self.interval_sec)

        _enable_privileges()
        threading.Thread(target=self._auto_loop, daemon=True).start()

    def get_config_dict(self) -> dict:
        return {
            "limit_gb":      self.limit_gb,
            "interval_sec":  self.interval_sec,
            "auto_mode":     self.auto_mode,
            "use_filecache": self.use_filecache,
            "whitelist":     sorted(list(self.whitelist)),
            "swap_lock_gb":  self.swap_lock_gb,   # [FIX v3.3] persiste junto com as demais configs
        }

    def register_callback(self, cb) -> None:
        self._callbacks.append(cb)

    def _emit(self, event: str, data=None) -> None:
        for cb in self._callbacks:
            try:
                cb(event, data)
            except Exception:
                pass

    def stop(self) -> None:
        self.running = False

    # ── Auto Loop (v3.2 Adaptive + Countdown) ────────────────────────────────
    def _auto_loop(self) -> None:
        """Loop principal de auto-otimização com intervalo adaptativo.

        Atualiza self.next_auto_in_sec a cada iteração para que a UI possa
        exibir um countdown preciso.
        """
        while self.running:
            time.sleep(5)
            if not self.auto_mode or self._optimizing:
                continue
            try:
                mem     = psutil.virtual_memory()
                used_gb = mem.used / (1024 ** 3)
                ram_pct = mem.percent
                elapsed = time.time() - self._last_ts

                # Adaptive interval
                if ram_pct > 85:
                    self._effective_interval = max(30, self.interval_sec // 2)
                elif ram_pct > 65:
                    self._effective_interval = self.interval_sec
                else:
                    self._effective_interval = self.interval_sec * 3

                self.next_auto_in_sec = max(0.0, self._effective_interval - elapsed)

                if used_gb > self.limit_gb or elapsed >= self._effective_interval:
                    self._run("auto")
            except Exception:
                pass

    # ── Public ────────────────────────────────────────────────────────────────
    def optimize_now(self) -> None:
        """Dispara uma otimização manual em thread daemon separada."""
        if not self._optimizing:
            threading.Thread(target=self._run, args=("manual",), daemon=True).start()

    # ── Core ──────────────────────────────────────────────────────────────────
    def _run(self, trigger: str) -> None:
        if self._optimizing:
            return
        self._optimizing = True
        self._emit("start", {"trigger": trigger})
        try:
            self._do_optimize(trigger)
        finally:
            self._optimizing = False

    def _do_optimize(self, trigger: str) -> None:
        if not IS_WINDOWS:
            self._emit("done", {
                "trigger": trigger, "freed_mb": 0.0, "cleaned": 0, "skipped": 0,
                "layers": [], "total_freed": 0.0, "total_runs": 0, "is_admin": False,
                "timestamp": datetime.now(),
            })
            return

        mem_before = psutil.virtual_memory().available
        cleaned    = 0
        skipped    = 0
        layers     = []

        # ── Swap Lock safety ────────────────────────────────────────────────
        swap         = psutil.swap_memory()
        swap_gb      = swap.used / (1024 ** 3)
        # [FIX v3.3] usa self.swap_lock_gb (configurável) em vez de 4.0 fixo
        is_swap_safe = (swap_gb < self.swap_lock_gb)
        if not is_swap_safe:
            layers.append("⚠ Swap Lock (>{:.1f}GB)".format(self.swap_lock_gb))

        # ── Foreground PID ──────────────────────────────────────────────────
        fg_pid = _get_foreground_pid()

        # ── Layer 1: System-wide working set empty (admin) ──────────────────
        if IS_ADMIN and is_swap_safe:
            try:
                cmd = ctypes.c_int(_MEM_EMPTY_ALL_WS)
                if _NtSysInfo(_SYSINFO_MEMLIST, ctypes.byref(cmd), ctypes.sizeof(cmd)) == 0:
                    layers.append("L1: SystemEmptyWS")
            except Exception:
                pass

        # ── Layer 2b: Per-Process Smart Trim ───────────────────────────────
        if is_swap_safe:
            trimmed    = 0
            current_pf = {}
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
                try:
                    pid  = proc.info['pid']
                    name = (proc.info['name'] or "").lower()
                    if pid == 0 or name in SYSTEM_PROCS:
                        continue
                    if pid == fg_pid:
                        skipped += 1
                        continue
                    if name in self.whitelist:
                        skipped += 1
                        continue
                    cpu = proc.info.get('cpu_percent', 0.0) or 0.0
                    if cpu > 2.0:
                        skipped += 1
                        continue
                    mem_info = proc.info.get('memory_info')
                    if mem_info:
                        pf      = getattr(mem_info, 'num_page_faults', 0)
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

        # ── Layer 4: Purge Standby List (admin) ────────────────────────────
        if IS_ADMIN:
            try:
                cmd = ctypes.c_int(_MEM_PURGE_STANDBY)
                if _NtSysInfo(_SYSINFO_MEMLIST, ctypes.byref(cmd), ctypes.sizeof(cmd)) == 0:
                    layers.append("L4: PurgeStandby")
            except Exception:
                pass

        # ── Layer 5: Reduce file cache (admin) ─────────────────────────────
        if IS_ADMIN and self.use_filecache:
            try:
                if _SetFileCache(_FILECACHE_MIN, _SIZE_MAX, 0):
                    layers.append("L5: FileCache(256MB)")
            except Exception:
                pass

        # ── Layer 6: Memory page combining (admin, Win8+) ──────────────────
        if IS_ADMIN:
            try:
                for _ in range(3):
                    cmd = ctypes.c_int(_MEM_COMBINE_PAGES)
                    st  = _NtSysInfo(_SYSINFO_MEMLIST, ctypes.byref(cmd), ctypes.sizeof(cmd))
                if st == 0:
                    layers.append("L6: PageCombine")
            except Exception:
                pass

        # ── Auto-trim do próprio processo ───────────────────────────────────
        try:
            own = _GetCurrentProcess()
            _EmptyWS(own)
            if IS_ADMIN:
                _SetWSEx(own, _SIZE_MAX, _SIZE_MAX, 0)
        except Exception:
            pass

        mem_after = psutil.virtual_memory().available
        freed_mb  = max(0.0, (mem_after - mem_before) / (1024 * 1024))
        ts        = datetime.now()

        self.total_freed_mb += freed_mb
        self.total_runs     += 1
        self.layers_fired    = layers
        self._last_ts        = time.time()
        self.next_auto_in_sec = float(self._effective_interval)

        result = {
            "trigger":     trigger,
            "freed_mb":    freed_mb,
            "cleaned":     cleaned,
            "skipped":     skipped,
            "layers":      layers,
            "total_freed": self.total_freed_mb,
            "total_runs":  self.total_runs,
            "is_admin":    IS_ADMIN,
            "timestamp":   ts,
        }

        # Persistir no log em disco
        append_log(result)

        self._emit("done", result)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════
class MemOptimaApp:

    def __init__(self, root: tk.Tk, engine: OptimizationEngine):
        self.root   = root
        self.engine = engine
        self._tray  = None
        self._pulse_job = None
        self._pb    = False          # [FIX] inicializado aqui, não via hasattr
        self._countdown_job = None

        engine.register_callback(self._on_engine_event)

        self._config_window()
        self._setup_styles()
        self._build_ui()
        self._load_history_from_disk()  # [FEAT] restaura log persistido
        self._start_monitor()
        self._start_countdown()          # [FEAT] countdown da próxima otimização

    # ── Window ────────────────────────────────────────────────────────────────
    def _config_window(self) -> None:
        self.root.title("MemOptima v3.2 ULTIMATE")
        self.root.geometry("600x930")
        self.root.minsize(500, 780)
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

    def _on_close(self) -> None:
        """[FIX v3.3] Comportamento consistente: persiste config SOMENTE se o usuário confirmar."""
        if self._tray:
            # Com tray disponível — oferecer escolha
            result = messagebox.askyesnocancel(
                "MemOptima",
                "O que deseja fazer?\n\n"
                "• Sim → Minimizar para o System Tray (continua otimizando)\n"
                "• Não → Encerrar o MemOptima\n"
                "• Cancelar → Voltar"
            )
            if result is True:
                self._persist_config()  # [FIX] só persiste ao confirmar
                self.root.withdraw()
            elif result is False:
                self._persist_config()  # [FIX] só persiste ao confirmar
                self._exit()
            # None (cancelar) → não faz nada, não persiste
        else:
            if messagebox.askyesno("Sair", "Encerrar o MemOptima?\nO monitoramento será interrompido."):
                self._persist_config()  # [FIX] só persiste ao confirmar
                self._exit()

    def _exit(self) -> None:
        self._persist_config()
        self.engine.stop()
        if self._countdown_job:
            self.root.after_cancel(self._countdown_job)
        if self._tray:
            try:
                self._tray.stop()
            except Exception:
                pass
        self.root.after(0, self.root.destroy)

    def _persist_config(self) -> None:
        cfg = self.engine.get_config_dict()
        cfg["start_with_windows"] = self._v_startup.get() if hasattr(self, '_v_startup') else False
        save_config(cfg)   # [FIX] escrita atômica via shared/config.py

    def set_tray(self, icon) -> None:
        self._tray = icon

    def restore(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _launch_vram_compressor(self) -> None:
        is_frozen = getattr(sys, "frozen", False)
        script_dir = os.path.dirname(os.path.abspath(__file__))

        if is_frozen:
            cmd = [sys.executable, "--vram-compressor"]
        else:
            compressor = os.path.join(script_dir, "vram_compressor.py")
            if not os.path.exists(compressor):
                messagebox.showerror("VirtualRAM Compressor",
                                     "Arquivo 'vram_compressor.py' não encontrado em:\n{}".format(script_dir))
                return
            exe = sys.executable
            # Prefere pythonw.exe para evitar janela preta de console
            if exe.lower().endswith("python.exe"):
                w_exe = exe[:-10] + "pythonw.exe"
                if os.path.exists(w_exe):
                    exe = w_exe
            cmd = [exe, compressor]

        try:
            flags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
            subprocess.Popen(
                cmd,
                cwd=script_dir,
                creationflags=flags,
            )
        except Exception as ex:
            messagebox.showerror("VirtualRAM Compressor",
                                 "Erro ao iniciar o Compressor:\n{}".format(ex))

    # ── Styles ────────────────────────────────────────────────────────────────
    def _setup_styles(self) -> None:
        s = ttk.Style()
        s.theme_use('clam')
        for name, c in [('G.Horizontal.TProgressbar', NEON),
                         ('W.Horizontal.TProgressbar', WARN),
                         ('R.Horizontal.TProgressbar', RED)]:
            s.configure(name, troughcolor=NE_DIM, background=c,
                        bordercolor=BG, lightcolor=c, darkcolor=c, thickness=6)

    # ── UI Assembly ───────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
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
    def _build_header(self, p) -> None:
        f = tk.Frame(p, bg=BG)
        f.pack(fill="x", pady=(16, 6))

        row = tk.Frame(f, bg=BG)
        row.pack()

        tk.Label(row, text="Mem",    font=("Segoe UI", 28, "bold"), fg=WHT,  bg=BG).pack(side="left")
        tk.Label(row, text="Optima", font=("Segoe UI", 28, "bold"), fg=NEON, bg=BG).pack(side="left")
        tk.Label(row, text=" v3.2",  font=("Segoe UI", 14),         fg=GRY,  bg=BG).pack(side="left", pady=(12, 0))

        badge_c = BLU if IS_ADMIN else WARN
        badge_t = "★ ADMIN" if IS_ADMIN else "⚠ USER"
        tk.Label(row, text="  {}  ".format(badge_t),
                 font=("Segoe UI", 8, "bold"), fg=DRK, bg=badge_c).pack(side="left", padx=(10, 0), pady=(14, 0))

        fs_btn = tk.Button(row, text="⛶", font=("Segoe UI", 12), fg=GRY, bg=BG, bd=0,
                           cursor="hand2", command=self.toggle_fullscreen,
                           activebackground=BG, activeforeground=WHT)
        fs_btn.pack(side="left", padx=(10, 0), pady=(12, 0))

        tk.Label(f, text="ULTIMATE RAM Optimizer — Smart 7 Layers — Always Running",
                 font=("Segoe UI", 9), fg=GRY, bg=BG).pack()

        action_row = tk.Frame(f, bg=BG)
        action_row.pack(pady=(4, 0))

        if not IS_ADMIN:
            tk.Label(action_row,
                     text="Execute run_admin.bat para ativar camadas de sistema",
                     font=("Segoe UI", 8), fg=WARN, bg=BG).pack(side="left", padx=(0, 12))

        compressor_btn = tk.Button(
            action_row, text="🗜  Compressor RAM",
            font=("Segoe UI", 8, "bold"),
            fg="#060913", bg="#a78bfa", activebackground="#7c5cdb",
            activeforeground="#060913", bd=0, cursor="hand2",
            padx=10, pady=3, command=self._launch_vram_compressor,
        )
        compressor_btn.pack(side="left")
        compressor_btn.bind("<Enter>", lambda e: compressor_btn.config(bg="#7c5cdb"))
        compressor_btn.bind("<Leave>", lambda e: compressor_btn.config(bg="#a78bfa"))

    # ── Metrics Card ──────────────────────────────────────────────────────────
    def _build_metrics(self, p) -> None:
        card = self._card(p)
        inn  = tk.Frame(card, bg=CARD)
        inn.pack(fill="x", padx=16, pady=14)

        # Left: circular gauge (agora usa shared/widgets.py)
        left = tk.Frame(inn, bg=CARD)
        left.pack(side="left", anchor="n")
        self.gauge = CircularGauge(left, size=188, label="RAM")
        self.gauge.pack()

        # Right: stat labels
        right = tk.Frame(inn, bg=CARD)
        right.pack(side="left", padx=(18, 0), fill="y", expand=True)

        tk.Label(right, text="Memória RAM (Física)",
                 font=("Segoe UI", 11, "bold"), fg=NEON, bg=CARD).pack(anchor="w")

        self.lbl_used  = self._stat_row(right, "Usado :")
        self.lbl_free  = self._stat_row(right, "Livre  :")
        self.lbl_total = self._stat_row(right, "Total  :")

        tk.Frame(right, bg=BDR, height=1).pack(fill="x", pady=6)

        self.lbl_limit_status = tk.Label(right, text="",
                                         font=("Segoe UI", 9, "bold"), fg=NEON, bg=CARD)
        self.lbl_limit_status.pack(anchor="w")

        spark_f = tk.Frame(card, bg=CARD)
        spark_f.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(spark_f, text="Histórico RAM (física) — últimos 3 min",
                 font=("Segoe UI", 7), fg=GRY, bg=CARD).pack(anchor="w")
        self.sparkline = Sparkline(spark_f, height=44)
        self.sparkline.pack(fill="x", expand=True)

    def _stat_row(self, parent, label: str) -> tk.Label:
        f = tk.Frame(parent, bg=CARD)
        f.pack(anchor="w", pady=3)
        tk.Label(f, text=label, font=("Consolas", 9), fg=GRY, bg=CARD,
                 width=9, anchor="w").pack(side="left")
        lbl = tk.Label(f, text="--- GB", font=("Consolas", 12, "bold"), fg=WHT, bg=CARD)
        lbl.pack(side="left")
        return lbl

    # ── Action Card ───────────────────────────────────────────────────────────
    def _build_action(self, p) -> None:
        card = self._card(p)
        inn  = tk.Frame(card, bg=CARD)
        inn.pack(fill="x", padx=16, pady=14)

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

        stats_f = tk.Frame(inn, bg=CARD)
        stats_f.pack(fill="x", pady=(10, 0))

        self.lbl_last  = tk.Label(stats_f, text="Última:  —",
                                  font=("Segoe UI", 9), fg=WHT, bg=CARD)
        self.lbl_last.pack(side="left")
        self.lbl_total_freed = tk.Label(stats_f, text="  |  Total: 0 MB",
                                        font=("Segoe UI", 9), fg=GRY, bg=CARD)
        self.lbl_total_freed.pack(side="left")
        self.lbl_runs  = tk.Label(stats_f, text="  |  Runs: 0",
                                  font=("Segoe UI", 9), fg=GRY, bg=CARD)
        self.lbl_runs.pack(side="left")

        # [FEAT] Countdown para próxima otimização automática
        self.lbl_countdown = tk.Label(inn, text="",
                                      font=("Segoe UI", 8), fg=GRY, bg=CARD)
        self.lbl_countdown.pack(anchor="w", pady=(4, 0))

    # ── Active Layers Bar ─────────────────────────────────────────────────────
    def _build_layers_bar(self, p) -> None:
        card = self._card(p, pad_v=0)
        f = tk.Frame(card, bg=C2)
        f.pack(fill="x")

        tk.Label(f, text="CAMADAS ATIVAS:",
                 font=("Consolas", 7, "bold"), fg=GRY, bg=C2,
                 pady=5, padx=10).pack(side="left")
        self.lbl_layers = tk.Label(f, text="—",
                                   font=("Consolas", 7), fg=ACCNT, bg=C2,
                                   pady=5, wraplength=380, justify="left")
        self.lbl_layers.pack(side="left", padx=4)

    # ── Settings Card ─────────────────────────────────────────────────────────
    def _build_settings(self, p) -> None:
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
                       **{**ck_style, "command": self._toggle_startup}).pack(side="left")

        # Row 4: Whitelist
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

    # ── Process List — [FIX] com scrollbar + [FEAT] CPU% ─────────────────────
    def _build_processes(self, p) -> None:
        card = self._card(p, expand=True)

        hdr = tk.Frame(card, bg=C2)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🔥  Top Consumidores de RAM (agrupados)",
                 font=("Segoe UI", 9, "bold"), fg=WHT, bg=C2,
                 pady=7, padx=12).pack(side="left")
        self.lbl_proc_time = tk.Label(hdr, text="",
                                      font=("Segoe UI", 7), fg=GRY, bg=C2)
        self.lbl_proc_time.pack(side="right", padx=10, pady=7)

        # [FIX] cabeçalho agora inclui CPU%
        chdr = tk.Frame(card, bg=C3)
        chdr.pack(fill="x")
        tk.Label(chdr,
                 text="  Processo                 Inst  RAM(MB)  CPU%   Status",
                 font=("Consolas", 8, "bold"), fg=ACCNT, bg=C3,
                 pady=4, padx=8).pack(anchor="w")

        # [FIX] Scrollbar na lista de processos
        proc_frame = tk.Frame(card, bg=CARD)
        proc_frame.pack(fill="both", expand=True, padx=8, pady=(2, 8))

        proc_sb = tk.Scrollbar(proc_frame, orient="vertical", bg=C2,
                                troughcolor=CARD, width=10)
        proc_sb.pack(side="right", fill="y")

        self.txt_procs = tk.Text(proc_frame, bg=CARD, fg=NEON, font=("Consolas", 9),
                                 bd=0, highlightthickness=0, height=8, wrap="none",
                                 yscrollcommand=proc_sb.set)
        self.txt_procs.pack(side="left", fill="both", expand=True)
        proc_sb.config(command=self.txt_procs.yview)
        self.txt_procs.config(state="disabled")

        # Context menu
        self._proc_menu = tk.Menu(self.root, tearoff=0,
                                   bg=CARD, fg=WHT, activebackground=C3,
                                   activeforeground=NEON, font=("Segoe UI", 9),
                                   bd=1, relief="flat")
        self._proc_menu.add_command(label="🛡 Proteger processo", command=self._whitelist_add)
        self._proc_menu.add_command(label="✕ Remover proteção",  command=self._whitelist_remove)
        self.txt_procs.bind("<Button-3>", self._on_proc_right_click)

        self._grouped_procs = []

    # ── History — [FIX] com scrollbar ─────────────────────────────────────────
    def _build_history(self, p) -> None:
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

        # [FIX] Scrollbar no log
        hist_frame = tk.Frame(card, bg=CARD)
        hist_frame.pack(fill="both", expand=True, padx=8, pady=6)

        hist_sb = tk.Scrollbar(hist_frame, orient="vertical", bg=C2,
                                troughcolor=CARD, width=10)
        hist_sb.pack(side="right", fill="y")

        self.txt_hist = tk.Text(hist_frame, bg=CARD, fg=WHT,
                                font=("Consolas", 10, "bold"),
                                bd=0, highlightthickness=0, height=5, wrap="none",
                                yscrollcommand=hist_sb.set)
        self.txt_hist.pack(side="left", fill="both", expand=True)
        hist_sb.config(command=self.txt_hist.yview)

        self.txt_hist.tag_config("neon",  foreground=NEON)
        self.txt_hist.tag_config("warn",  foreground=WARN)
        self.txt_hist.tag_config("admin", foreground=BLU)
        self.txt_hist.config(state="disabled")

    # ── Helper ────────────────────────────────────────────────────────────────
    def _card(self, parent, bottom_pad: int = 8, pad_v=None, expand: bool = False) -> tk.Frame:
        f = tk.Frame(parent, bg=CARD, highlightbackground=BDR, highlightthickness=1)
        if expand:
            f.pack(fill="both", expand=True, padx=16, pady=(0, bottom_pad))
        else:
            f.pack(fill="x", padx=16, pady=(0, bottom_pad))
        return f

    # ── Settings Logic ────────────────────────────────────────────────────────
    def _toggle_auto(self) -> None:
        self.engine.auto_mode = not self.engine.auto_mode
        self._apply_settings()
        self._refresh_auto_btn()
        self._manage_pulse()

    def _refresh_auto_btn(self) -> None:
        if self.engine.auto_mode:
            self.btn_auto.config(text="ON", fg=DRK, bg=NEON)
            self.lbl_auto_desc.config(
                text="Adaptativo — base {}s (ajusta por pressão RAM)".format(self.engine.interval_sec),
                fg=NEON)
        else:
            self.btn_auto.config(text="OFF", fg=WHT, bg="#1a1a30")
            self.lbl_auto_desc.config(text="Desativado", fg=GRY)

    def _apply_settings(self) -> None:
        try:
            self.engine.limit_gb = max(0.5, float(self._v_limit.get()))
        except Exception:
            self._v_limit.set("{:.1f}".format(self.engine.limit_gb))
        try:
            self.engine.interval_sec = max(10, int(self._v_interval.get()))
        except Exception:
            self._v_interval.set(str(self.engine.interval_sec))
        self.engine.use_filecache = self._v_filecache.get()
        self._refresh_auto_btn()
        self._persist_config()

    def _toggle_startup(self) -> None:
        _set_startup(self._v_startup.get())
        self._persist_config()

    def _clear_history(self) -> None:
        self.txt_hist.config(state="normal")
        self.txt_hist.delete("1.0", tk.END)
        self.txt_hist.config(state="disabled")

    def _refresh_whitelist_label(self) -> None:
        wl = self.engine.whitelist
        self.lbl_whitelist.config(
            text=", ".join(sorted(wl)) if wl else "nenhum")

    # ── Whitelist Logic ───────────────────────────────────────────────────────
    def _on_proc_right_click(self, event) -> None:
        try:
            index    = self.txt_procs.index("@{},{}".format(event.x, event.y))
            line_num = int(index.split(".")[0]) - 1
            if 0 <= line_num < len(self._grouped_procs):
                self._selected_proc = self._grouped_procs[line_num][0].lower()
                if self._selected_proc in self.engine.whitelist:
                    self._proc_menu.entryconfigure(0, state="disabled")
                    self._proc_menu.entryconfigure(1, state="normal")
                else:
                    self._proc_menu.entryconfigure(0, state="normal")
                    self._proc_menu.entryconfigure(1, state="disabled")
                self._proc_menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass

    def _whitelist_add(self) -> None:
        if hasattr(self, '_selected_proc') and self._selected_proc:
            self.engine.whitelist.add(self._selected_proc)
            self._refresh_whitelist_label()
            self._persist_config()
            self.root.after(0, self._ui_procs)

    def _whitelist_remove(self) -> None:
        if hasattr(self, '_selected_proc') and self._selected_proc:
            self.engine.whitelist.discard(self._selected_proc)
            self._refresh_whitelist_label()
            self._persist_config()
            self.root.after(0, self._ui_procs)

    # ── Pulse Button ──────────────────────────────────────────────────────────
    def _manage_pulse(self) -> None:
        if self.engine.auto_mode:
            self._pulse()
        else:
            if self._pulse_job:
                self.root.after_cancel(self._pulse_job)
                self._pulse_job = None
            if str(self.btn["state"]) == "normal":
                self.btn.config(bg=NEON)

    def _pulse(self) -> None:
        if not self.engine.auto_mode:
            return
        self._pb = not self._pb  # [FIX] _pb já inicializado em __init__
        if str(self.btn["state"]) == "normal":
            self.btn.config(bg=NE2 if self._pb else NEON)
        self._pulse_job = self.root.after(700, self._pulse)

    # ── Countdown — [FEAT] ────────────────────────────────────────────────────
    def _start_countdown(self) -> None:
        """Atualiza o label de countdown a cada segundo."""
        self._update_countdown()

    def _update_countdown(self) -> None:
        if self.engine.auto_mode and not self.engine._optimizing:
            secs = int(self.engine.next_auto_in_sec)
            if secs > 0:
                m, s = divmod(secs, 60)
                if m > 0:
                    self.lbl_countdown.config(
                        text="⏱ Próxima auto-otimização em {}m{:02d}s".format(m, s), fg=GRY)
                else:
                    self.lbl_countdown.config(
                        text="⏱ Próxima auto-otimização em {}s".format(s), fg=GRY)
                # Decrementar localmente enquanto o engine não atualiza
                self.engine.next_auto_in_sec = max(0.0, self.engine.next_auto_in_sec - 1.0)
            else:
                self.lbl_countdown.config(text="⚡ Auto-otimização iminente...", fg=NEON)
        elif self.engine._optimizing:
            self.lbl_countdown.config(text="⏳ Otimizando agora...", fg=WARN)
        else:
            self.lbl_countdown.config(text="")

        self._countdown_job = self.root.after(1000, self._update_countdown)

    # ── Optimize Click ────────────────────────────────────────────────────────
    def _on_opt_click(self) -> None:
        self.engine.optimize_now()

    # ── Engine Events (cross-thread safe via root.after) ─────────────────────
    def _on_engine_event(self, event: str, data=None) -> None:
        """Callback chamado pela thread do engine. SEMPRE usa root.after()."""
        if event == "start":
            self.root.after(0, self._ui_start, data)
        elif event == "done":
            self.root.after(0, self._ui_done, data)

    def _ui_start(self, data) -> None:
        t = (data or {}).get("trigger", "?")
        self.btn.config(state="disabled",
                        text="⏳  OTIMIZANDO {} CAMADAS...".format("7" if IS_ADMIN else "3"),
                        bg=C3, fg=WARN)
        self.lbl_auto_desc.config(text="Otimizando ({})...".format(t), fg=WARN)

    def _ui_done(self, data) -> None:
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

        self.lbl_last.config(
            text="Última: {}  ({} procs, {} skip)".format(freed_s, cleaned, skipped), fg=NEON)
        self.lbl_total_freed.config(text="  |  Total: {}".format(total_s))
        self.lbl_runs.config(text="  |  Runs: {}".format(runs))
        self.lbl_layers.config(text="  •  ".join(layers) if layers else "—")

        self.btn.config(state="normal", text="⚡  OTIMIZAR MEMÓRIA AGORA",
                        bg=NEON, fg=DRK)
        self._refresh_auto_btn()
        self._manage_pulse()

        # Log entry
        adm_mark  = "★" if adm else " "
        trig_mark = "AUTO  " if trigger == "auto" else "MANUAL"
        line = "[{}] {} {} | {:>8} | {} trim {} skip | {}\n".format(
            ts.strftime("%H:%M:%S"), adm_mark, trig_mark,
            freed_s, cleaned, skipped, " ".join(layers[:3]))

        self.txt_hist.config(state="normal")
        self.txt_hist.insert("1.0", line, "neon" if freed > 0 else "warn")
        n_lines = int(self.txt_hist.index("end-1c").split(".")[0])
        if n_lines > 30:
            self.txt_hist.delete("31.0", tk.END)
        self.txt_hist.config(state="disabled")

        # Toast notification (auto + tray + minimizado)
        if trigger == "auto" and self._tray and not self.root.winfo_viewable():
            try:
                self._tray.notify(
                    "MemOptima — {}".format(freed_s),
                    "{} processos otimizados, {} pulados".format(cleaned, skipped),
                )
            except Exception:
                pass

    # ── Live Monitor ──────────────────────────────────────────────────────────
    def _start_monitor(self) -> None:
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self) -> None:
        """Métricas de RAM: a cada 2s | Lista de processos: a cada 10s (5 ciclos)."""
        _proc_tick = 0
        while True:
            try:
                mem = psutil.virtual_memory()
                self.root.after(0, self._ui_metrics, mem)
                _proc_tick += 1
                if _proc_tick >= 5:
                    _proc_tick = 0
                    self.root.after(0, self._ui_procs)
            except Exception:
                pass
            time.sleep(2)

    def _ui_metrics(self, mem) -> None:
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
                text="⚠  {:.2f} GB > limite {:.1f} GB — otimização pendente".format(used_gb, lim),
                fg=RED)
        else:
            self.lbl_limit_status.config(
                text="✓  {:.2f} GB dentro do limite de {:.1f} GB".format(used_gb, lim),
                fg=NEON)

    def _ui_procs(self) -> None:
        """[FEAT] Lista de processos agrupados por nome com CPU% agregado."""
        raw_procs = []
        for p in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
            try:
                info = p.info
                name = info['name'] or "?"
                if name.lower() in SYSTEM_PROCS:
                    continue
                minfo = info['memory_info']
                if minfo:
                    mb  = minfo.rss / (1024 * 1024)
                    cpu = info.get('cpu_percent') or 0.0
                    raw_procs.append((name, mb, info['pid'], cpu))
            except Exception:
                continue

        # Group by name, aggregate RAM and CPU
        grouped: dict = {}
        for name, mb, pid, cpu in raw_procs:
            key = name.lower()
            if key in grouped:
                grouped[key]['mb']    += mb
                grouped[key]['cpu']   += cpu
                grouped[key]['count'] += 1
            else:
                grouped[key] = {'name': name, 'mb': mb, 'cpu': cpu, 'count': 1}

        display = [(d['name'], d['mb'], d['count'], d['cpu'])
                   for d in grouped.values()]
        display.sort(key=lambda x: x[1], reverse=True)
        self._grouped_procs = display

        self.txt_procs.config(state="normal")
        self.txt_procs.delete("1.0", tk.END)

        if display:
            max_mb = max(display[0][1], 1)
            for name, mb, inst_count, cpu in display[:20]:
                bar_len  = int((mb / max_mb) * 8)
                bar      = "█" * bar_len + "░" * (8 - bar_len)
                shield   = "🛡" if name.lower() in self.engine.whitelist else "  "
                inst_str = "×{}".format(inst_count) if inst_count > 1 else "  "
                # [FEAT] CPU% inclusa na linha
                line = "  {:<23} {:>3}  {:>8.1f}  {:>5.1f}%  {} {}\n".format(
                    name, inst_str, mb, min(cpu, 999.9), bar, shield)
                self.txt_procs.insert(tk.END, line)

        self.lbl_proc_time.config(text=datetime.now().strftime("%H:%M:%S"))
        self.txt_procs.config(state="disabled")

    # ── [FEAT] Restaurar log persistido ──────────────────────────────────────
    def _load_history_from_disk(self) -> None:
        """Carrega as últimas 30 entradas do log persistido em optimization_log.jsonl."""
        entries = load_log(max_entries=30)
        if not entries:
            return

        # [FIX v3.3] fmt() definida fora do loop para não ser recriada a cada iteração
        def fmt(mb: float) -> str:
            return "{:.2f}GB".format(mb / 1024) if mb >= 1024 else "{:.0f}MB".format(mb)

        self.txt_hist.config(state="normal")
        for entry in entries:
            try:
                ts      = entry.get("timestamp", "")[:8]   # HH:MM:SS ou ISO parcial
                trigger = entry.get("trigger", "?")
                adm     = entry.get("is_admin", False)
                freed   = entry.get("freed_mb", 0.0)
                cleaned = entry.get("cleaned", 0)
                skipped = entry.get("skipped", 0)
                layers  = entry.get("layers", [])

                freed_s   = "-" + fmt(freed)
                adm_mark  = "★" if adm else " "
                trig_mark = "AUTO  " if trigger == "auto" else "MANUAL"
                line = "[{}] {} {} | {:>8} | {} trim {} skip | {}\n".format(
                    ts, adm_mark, trig_mark, freed_s, cleaned, skipped,
                    " ".join(layers[:3]))
                self.txt_hist.insert(tk.END, line, "neon" if freed > 0 else "warn")
            except Exception:
                continue
        self.txt_hist.config(state="disabled")


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM TRAY
# ═══════════════════════════════════════════════════════════════════════════════
def setup_tray(app: MemOptimaApp):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, 62, 62], fill=(8, 8, 15, 255))
    draw.ellipse([2, 2, 62, 62], outline=(0, 255, 136, 255), width=4)
    draw.line([(14, 50), (14, 14), (32, 36), (50, 14), (50, 50)],
              fill=(0, 255, 136, 255), width=6)

    menu = pystray.Menu(
        pystray.MenuItem("Abrir MemOptima",   lambda i, _: app.root.after(0, app.restore), default=True),
        pystray.MenuItem("⚡ Otimizar Agora", lambda i, _: app.engine.optimize_now()),
        pystray.MenuItem(
            lambda item: "Auto-Modo: {}".format("ON ✓" if app.engine.auto_mode else "OFF"),
            lambda i, _: (
                setattr(app.engine, 'auto_mode', not app.engine.auto_mode),
                app.root.after(0, app._refresh_auto_btn),
                app.root.after(0, app._manage_pulse),
            ),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sair", lambda i, _: app._exit()),
    )

    icon = pystray.Icon("MemOptima", img, "MemOptima v3.2 ULTIMATE", menu)
    app.set_tray(icon)
    icon.run_detached()
    return icon


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    if "--vram-compressor" in sys.argv:
        try:
            import vram_compressor
            vram_compressor.main()
        except Exception as e:
            messagebox.showerror("Erro", "Falha ao iniciar o VirtualRAM Compressor:\n{}".format(e))
        return

    cfg    = load_config()
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
