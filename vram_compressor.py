# -*- coding: utf-8 -*-
"""
MemOptima VRAM v1.2 — Virtual Memory (Swap/Pagefile) Optimizer
Monitora e tenta reduzir a pressão na memória virtual do Windows,
evitando que o sistema use excessivamente o arquivo de paginação (Swap).

Foco:
  C1: Page Combine   — Deduplicação de páginas idênticas (libera RAM)
  C2: Purge Standby  — Purga a Standby List, liberando RAM de arquivos em cache

v1.2 Improvements:
  - [FIX]     Configurações (limit_gb, interval_sec, auto_mode) persistidas em config.json
  - [FIX]     _pb inicializado em __init__ (anti-padrão hasattr removido)
  - [FIX]     Comportamento consistente no fechamento de janela (com/sem tray)
  - [FEAT]    Scrollbar na lista de processos e no log
  - [REFACTOR] CircularGauge, Sparkline migrados para shared/widgets.py
  - [REFACTOR] Design tokens migrados para shared/design.py (tema Violet)
  - [REFACTOR] ctypes/win_api migrados para shared/win_api.py
  - [REFACTOR] Config/log migrados para shared/config.py

Roda de forma 100% independente do memoptima.py.
"""

import os
import sys
import time
import threading
from datetime import datetime
import tkinter as tk
from tkinter import messagebox
import psutil

# ── Shared modules ─────────────────────────────────────────────────────────────
from shared.design import (
    BG, CARD, C2, BDR, WHT, GRY, DRK,
    WARN, RED, BLU, GRN,
    # Tema Violet (override do NEON padrão)
    VIOLET_NEON   as NEON,
    VIOLET_NE2    as NE2,
    VIOLET_NE_DIM as NE_DIM,
    VIOLET_ACCNT  as ACCNT,
    VIOLET_C3     as C3,
)
from shared.widgets import CircularGauge, Sparkline
from shared.config  import load_config, save_config, append_log
from shared.win_api import (
    IS_WINDOWS, IS_ADMIN,
    SYSTEM_PROCS,
    _enable_privileges,
    _NtSysInfo, _SYSINFO_MEMLIST,
    _MEM_PURGE_STANDBY, _MEM_COMBINE_PAGES,
)

if IS_WINDOWS:
    import ctypes


# ═══════════════════════════════════════════════════════════════════════════════
# OPTIMIZATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════
class VirtualMemoryEngine:
    """Motor de otimização de memória virtual.

    C1: Page Combine   — deduplicação de páginas físicas (zero I/O, qualquer user)
    C2: Purge Standby  — purga Standby List (libera RAM de cache, requer admin)
    """

    # Chaves no config.json para persistência
    _CFG_KEY_LIMIT    = "vram_limit_gb"
    _CFG_KEY_INTERVAL = "vram_interval_sec"
    _CFG_KEY_AUTO     = "vram_auto_mode"

    def __init__(self, config: dict):
        self.limit_gb     = config.get(self._CFG_KEY_LIMIT,    4.0)
        self.interval_sec = config.get(self._CFG_KEY_INTERVAL, 60)
        self.auto_mode    = config.get(self._CFG_KEY_AUTO,     False)

        self.total_runs   = 0
        self.layers_fired = []
        self.running      = True
        self._optimizing  = False
        self._callbacks   = []
        self._last_ts     = 0.0

        _enable_privileges(extra_privs=["SeProfileSingleProcessPrivilege", "SeLockMemoryPrivilege"])
        threading.Thread(target=self._auto_loop, daemon=True).start()

    def get_config_dict(self) -> dict:
        """Retorna as configurações VRAM para serem mescladas no config.json global."""
        return {
            self._CFG_KEY_LIMIT:    self.limit_gb,
            self._CFG_KEY_INTERVAL: self.interval_sec,
            self._CFG_KEY_AUTO:     self.auto_mode,
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

    def _auto_loop(self) -> None:
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

    def optimize_now(self) -> None:
        if not self._optimizing:
            threading.Thread(target=self._run, args=("manual",), daemon=True).start()

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
                "trigger": trigger, "layers": [], "total_runs": 0,
                "is_admin": False, "timestamp": datetime.now(),
            })
            return

        layers = []

        # C1: Page Combine (zero I/O — funciona sem admin)
        try:
            cmd = ctypes.c_int(_MEM_COMBINE_PAGES)
            st  = _NtSysInfo(_SYSINFO_MEMLIST, ctypes.byref(cmd), ctypes.sizeof(cmd))
            if st == 0:
                layers.append("C1: PageCombine")
        except Exception:
            pass

        # C2: Purge Standby List (libera cache — requer admin)
        if IS_ADMIN:
            try:
                cmd = ctypes.c_int(_MEM_PURGE_STANDBY)
                st  = _NtSysInfo(_SYSINFO_MEMLIST, ctypes.byref(cmd), ctypes.sizeof(cmd))
                if st == 0:
                    layers.append("C2: PurgeStandby")
            except Exception:
                pass

        self.total_runs += 1
        self._last_ts    = time.time()

        result = {
            "trigger":    trigger,
            "layers":     layers,
            "total_runs": self.total_runs,
            "is_admin":   IS_ADMIN,
            "timestamp":  datetime.now(),
            # VRAM engine não mede freed_mb diretamente (sem baseline de swap)
            "freed_mb":   0.0,
            "cleaned":    0,
            "skipped":    0,
        }
        append_log(result)
        self._emit("done", result)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════
class VirtualMemoryApp:

    def __init__(self, root: tk.Tk, engine: VirtualMemoryEngine, cfg: dict):
        self.root    = root
        self.engine  = engine
        self._cfg    = cfg       # referência ao config global para persistência
        self._tray   = None
        self._pulse_job = None
        self._pb     = False     # [FIX] inicializado aqui, não via hasattr
        self.is_fullscreen = False

        engine.register_callback(self._on_engine_event)
        self._config_window()
        self._build_ui()
        self._start_monitor()

    def _config_window(self) -> None:
        self.root.title("VirtualRAM Compressor — MemOptima VRAM v1.2")
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

    def _on_close(self) -> None:
        """[FIX] Comportamento consistente: sempre pergunta antes de fechar ou minimizar."""
        self._persist_config()
        if self._tray:
            result = messagebox.askyesnocancel(
                "VirtualRAM Compressor",
                "O que deseja fazer?\n\n"
                "• Sim → Minimizar para o System Tray\n"
                "• Não → Encerrar\n"
                "• Cancelar → Voltar"
            )
            if result is True:
                self.root.withdraw()
            elif result is False:
                self._exit()
        else:
            if messagebox.askyesno("Sair", "Encerrar o Otimizador de Memória Virtual?"):
                self._exit()

    def _exit(self) -> None:
        self._persist_config()
        self.engine.stop()
        if self._tray:
            try:
                self._tray.stop()
            except Exception:
                pass
        self.root.after(0, self.root.destroy)

    def _persist_config(self) -> None:
        """[FIX] Persiste configurações VRAM no config.json global (escrita atômica)."""
        self._cfg.update(self.engine.get_config_dict())
        save_config(self._cfg)

    def set_tray(self, icon) -> None:
        self._tray = icon

    def restore(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    # ── UI ────────────────────────────────────────────────────────────────────
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

    def _build_header(self, p) -> None:
        f = tk.Frame(p, bg=BG)
        f.pack(fill="x", pady=(16, 6))

        row = tk.Frame(f, bg=BG)
        row.pack()

        tk.Label(row, text="MemOptima", font=("Segoe UI", 28, "bold"), fg=WHT,  bg=BG).pack(side="left")
        tk.Label(row, text=" VRAM",     font=("Segoe UI", 28, "bold"), fg=NEON, bg=BG).pack(side="left")

        badge_c = BLU if IS_ADMIN else WARN
        badge_t = "★ ADMIN" if IS_ADMIN else "⚠ USER"
        tk.Label(row, text="  {}  ".format(badge_t),
                 font=("Segoe UI", 8, "bold"), fg=DRK, bg=badge_c).pack(side="left", padx=(10, 0), pady=(14, 0))

        fs_btn = tk.Button(row, text="⛶", font=("Segoe UI", 12), fg=GRY, bg=BG, bd=0,
                           cursor="hand2", command=self.toggle_fullscreen,
                           activebackground=BG, activeforeground=WHT)
        fs_btn.pack(side="left", padx=(10, 0), pady=(12, 0))

        tk.Label(f, text="Monitoramento do Arquivo de Paginação (Swap / Disco)",
                 font=("Segoe UI", 9), fg=GRY, bg=BG).pack()

        if not IS_ADMIN:
            tk.Label(f, text="Execute como Administrador para purgar a Standby List",
                     font=("Segoe UI", 8), fg=WARN, bg=BG).pack(pady=(2, 0))

    def _build_metrics(self, p) -> None:
        card = self._card(p)
        inn  = tk.Frame(card, bg=CARD)
        inn.pack(fill="x", padx=16, pady=14)

        left = tk.Frame(inn, bg=CARD)
        left.pack(side="left", anchor="n")
        self.gauge = CircularGauge(left, size=188,
                                   neon_color=NEON, warn_color=WARN,
                                   red_color=RED, label="SWAP")
        self.gauge.pack()

        right = tk.Frame(inn, bg=CARD)
        right.pack(side="left", padx=(18, 0), fill="y", expand=True)

        tk.Label(right, text="Arquivo de Paginação (Swap no Disco)",
                 font=("Segoe UI", 11, "bold"), fg=NEON, bg=CARD).pack(anchor="w")

        self.lbl_used  = self._stat_row(right, "Usado :")
        self.lbl_free  = self._stat_row(right, "Livre :")
        self.lbl_total = self._stat_row(right, "Total :")

        tk.Frame(right, bg=BDR, height=1).pack(fill="x", pady=6)

        self.lbl_limit_status = tk.Label(right, text="",
                                         font=("Segoe UI", 9, "bold"), fg=NEON, bg=CARD)
        self.lbl_limit_status.pack(anchor="w")

        spark_f = tk.Frame(card, bg=CARD)
        spark_f.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(spark_f, text="Histórico Pagefile (Swap) — últimos 3 min",
                 font=("Segoe UI", 7), fg=GRY, bg=CARD).pack(anchor="w")
        self.sparkline = Sparkline(spark_f, height=44,
                                   line_color=NEON, fill_color=NE_DIM)
        self.sparkline.pack(fill="x", expand=True)

    def _stat_row(self, parent, label: str) -> tk.Label:
        f = tk.Frame(parent, bg=CARD)
        f.pack(anchor="w", pady=3)
        tk.Label(f, text=label, font=("Consolas", 9), fg=GRY, bg=CARD,
                 width=9, anchor="w").pack(side="left")
        lbl = tk.Label(f, text="--- GB", font=("Consolas", 12, "bold"), fg=WHT, bg=CARD)
        lbl.pack(side="left")
        return lbl

    def _build_action(self, p) -> None:
        card = self._card(p)
        inn  = tk.Frame(card, bg=CARD)
        inn.pack(fill="x", padx=16, pady=14)

        self.btn = tk.Button(inn, text="🗜  OTIMIZAR MEMÓRIA VIRTUAL",
                             font=("Segoe UI", 13, "bold"),
                             fg=DRK, bg=NEON, activebackground=NE2,
                             activeforeground=DRK, bd=0, cursor="hand2",
                             relief="flat", padx=20, pady=12,
                             command=self.engine.optimize_now)
        self.btn.pack(fill="x")
        self.btn.bind("<Enter>", lambda e: self.btn.config(bg=NE2)
                      if str(self.btn["state"]) == "normal" else None)
        self.btn.bind("<Leave>", lambda e: self.btn.config(bg=NEON)
                      if str(self.btn["state"]) == "normal" else None)

        stats_f = tk.Frame(inn, bg=CARD)
        stats_f.pack(fill="x", pady=(10, 0))

        self.lbl_last = tk.Label(stats_f, text="Última:  —",
                                 font=("Segoe UI", 9), fg=WHT, bg=CARD)
        self.lbl_last.pack(side="left")
        self.lbl_runs = tk.Label(stats_f, text="  |  Runs: 0",
                                 font=("Segoe UI", 9), fg=GRY, bg=CARD)
        self.lbl_runs.pack(side="left")

    def _build_layers_bar(self, p) -> None:
        card = self._card(p, pad_v=0)
        f = tk.Frame(card, bg=C2)
        f.pack(fill="x")
        tk.Label(f, text="CAMADAS ATIVAS:",
                 font=("Consolas", 7, "bold"), fg=GRY, bg=C2,
                 pady=5, padx=10).pack(side="left")
        self.lbl_layers = tk.Label(f, text="—",
                                   font=("Consolas", 7), fg=NEON, bg=C2,
                                   pady=5, wraplength=380, justify="left")
        self.lbl_layers.pack(side="left", padx=4)

    def _build_settings(self, p) -> None:
        card = self._card(p)
        hdr  = tk.Frame(card, bg=C2)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙  Auto-Modo & Configurações",
                 font=("Segoe UI", 9, "bold"), fg=WHT, bg=C2,
                 pady=7, padx=12).pack(side="left")

        inn = tk.Frame(card, bg=CARD)
        inn.pack(fill="x", padx=14, pady=10)

        r1 = tk.Frame(inn, bg=CARD)
        r1.pack(fill="x", pady=(0, 8))
        tk.Label(r1, text="Auto-Modo:", font=("Segoe UI", 10, "bold"),
                 fg=WHT, bg=CARD).pack(side="left")
        self.btn_auto = tk.Button(r1, text="OFF",
                                  font=("Segoe UI", 9, "bold"),
                                  fg=WHT, bg=C3, bd=0, padx=18, pady=5,
                                  cursor="hand2", command=self._toggle_auto)
        self.btn_auto.pack(side="left", padx=(8, 12))
        self.lbl_auto_desc = tk.Label(r1, text="Desativado",
                                      font=("Segoe UI", 8), fg=GRY, bg=CARD)
        self.lbl_auto_desc.pack(side="left")

        r2 = tk.Frame(inn, bg=CARD)
        r2.pack(fill="x", pady=(0, 6))

        tk.Label(r2, text="Limite (GB):", font=("Segoe UI", 9), fg=GRY, bg=CARD).pack(side="left")
        self._v_limit = tk.StringVar(value="{:.1f}".format(self.engine.limit_gb))
        tk.Entry(r2, textvariable=self._v_limit, font=("Segoe UI", 9),
                 bg=C3, fg=WHT, bd=0, width=5, justify="center",
                 highlightthickness=1, highlightbackground=BDR).pack(side="left", padx=(3, 10))

        tk.Label(r2, text="Intervalo (s):", font=("Segoe UI", 9), fg=GRY, bg=CARD).pack(side="left")
        self._v_interval = tk.StringVar(value=str(self.engine.interval_sec))
        tk.Entry(r2, textvariable=self._v_interval, font=("Segoe UI", 9),
                 bg=C3, fg=WHT, bd=0, width=5, justify="center",
                 highlightthickness=1, highlightbackground=BDR).pack(side="left", padx=(3, 10))

        tk.Button(r2, text="Aplicar", font=("Segoe UI", 8),
                  fg=DRK, bg=NEON, bd=0, padx=10, pady=4,
                  cursor="hand2", command=self._apply_settings).pack(side="left")

        self._refresh_auto_btn()

    def _build_processes(self, p) -> None:
        """[FIX] Lista de processos VMS com scrollbar."""
        card = self._card(p, expand=True)

        hdr = tk.Frame(card, bg=C2)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🔥  Top Consumidores de Memória Virtual (VMS)",
                 font=("Segoe UI", 9, "bold"), fg=WHT, bg=C2,
                 pady=7, padx=12).pack(side="left")
        self.lbl_proc_time = tk.Label(hdr, text="",
                                      font=("Segoe UI", 7), fg=GRY, bg=C2)
        self.lbl_proc_time.pack(side="right", padx=10, pady=7)

        chdr = tk.Frame(card, bg=C3)
        chdr.pack(fill="x")
        tk.Label(chdr, text="  Processo                          VMS (MB)      PID",
                 font=("Consolas", 8, "bold"), fg=ACCNT, bg=C3,
                 pady=4, padx=8).pack(anchor="w")

        proc_frame = tk.Frame(card, bg=CARD)
        proc_frame.pack(fill="both", expand=True, padx=8, pady=(2, 8))

        proc_sb = tk.Scrollbar(proc_frame, orient="vertical", bg=C2,
                                troughcolor=CARD, width=10)
        proc_sb.pack(side="right", fill="y")

        self.txt_procs = tk.Text(proc_frame, bg=CARD, fg=NEON,
                                 font=("Consolas", 9), bd=0,
                                 highlightthickness=0, height=8, wrap="none",
                                 yscrollcommand=proc_sb.set)
        self.txt_procs.pack(side="left", fill="both", expand=True)
        proc_sb.config(command=self.txt_procs.yview)
        self.txt_procs.config(state="disabled")

    def _build_history(self, p) -> None:
        """[FIX] Log de otimizações com scrollbar."""
        card = self._card(p, bottom_pad=14, expand=True)

        hdr  = tk.Frame(card, bg=C2)
        hdr.pack(fill="x")
        hrow = tk.Frame(hdr, bg=C2)
        hrow.pack(fill="x", pady=7, padx=12)
        tk.Label(hrow, text="📜  Log de Otimizações de Swap",
                 font=("Segoe UI", 9, "bold"), fg=WHT, bg=C2).pack(side="left")
        tk.Button(hrow, text="Limpar", font=("Segoe UI", 7),
                  fg=GRY, bg=C3, bd=0, padx=6, pady=1,
                  cursor="hand2", command=self._clear_history).pack(side="right")

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
                text="Ativo — Swap > {:.1f} GB ou a cada {}s".format(
                    self.engine.limit_gb, self.engine.interval_sec),
                fg=NEON)
        else:
            self.btn_auto.config(text="OFF", fg=WHT, bg=C3)
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
        self._refresh_auto_btn()
        self._persist_config()

    def _clear_history(self) -> None:
        self.txt_hist.config(state="normal")
        self.txt_hist.delete("1.0", tk.END)
        self.txt_hist.config(state="disabled")

    # ── Pulse ─────────────────────────────────────────────────────────────────
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
        self._pb = not self._pb  # [FIX] _pb inicializado em __init__
        if str(self.btn["state"]) == "normal":
            self.btn.config(bg=NE2 if self._pb else NEON)
        self._pulse_job = self.root.after(700, self._pulse)

    # ── Engine Events ─────────────────────────────────────────────────────────
    def _on_engine_event(self, event: str, data=None) -> None:
        """Callback do engine. SEMPRE usa root.after() para thread safety."""
        if event == "start":
            self.root.after(0, self._ui_start, data)
        elif event == "done":
            self.root.after(0, self._ui_done, data)

    def _ui_start(self, data) -> None:
        t = (data or {}).get("trigger", "?")
        self.btn.config(state="disabled", text="⏳  OTIMIZANDO VIRTUAL...", bg=C3, fg=WARN)
        self.lbl_auto_desc.config(text="Otimizando ({})...".format(t), fg=WARN)

    def _ui_done(self, data) -> None:
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
        line = "[{}] {} {} | {}\n".format(
            ts.strftime("%H:%M:%S"), adm_mark, trig_mark, " ".join(layers[:3]))

        self.txt_hist.config(state="normal")
        self.txt_hist.insert("1.0", line, "neon" if layers else "warn")
        n_lines = int(self.txt_hist.index("end-1c").split(".")[0])
        if n_lines > 30:
            self.txt_hist.delete("31.0", tk.END)
        self.txt_hist.config(state="disabled")

    # ── Monitor ───────────────────────────────────────────────────────────────
    def _start_monitor(self) -> None:
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self) -> None:
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

    def _ui_metrics(self, mem) -> None:
        pct      = mem.percent
        used_gb  = mem.used  / (1024 ** 3)
        avail_gb = mem.free  / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)

        self.gauge.set_value(pct)
        self.sparkline.add(pct)

        self.lbl_used.config(text="{:.2f} GB".format(used_gb))
        self.lbl_free.config(text="{:.2f} GB".format(avail_gb))
        self.lbl_total.config(text="{:.2f} GB".format(total_gb))

        lim = self.engine.limit_gb
        if used_gb > lim:
            self.lbl_limit_status.config(
                text="⚠  {:.2f} GB > limite {:.1f} GB — swap alto".format(used_gb, lim),
                fg=RED)
        else:
            self.lbl_limit_status.config(
                text="✓  {:.2f} GB dentro do limite de {:.1f} GB".format(used_gb, lim),
                fg=NEON)

    def _ui_procs(self) -> None:
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'memory_info']):
            try:
                info  = p.info
                name  = info['name'] or "?"
                if name.lower() in SYSTEM_PROCS:
                    continue
                minfo = info['memory_info']
                if minfo and hasattr(minfo, 'vms'):
                    mb = minfo.vms / (1024 * 1024)
                    procs.append((name, mb, info['pid']))
            except Exception:
                continue

        procs.sort(key=lambda x: x[1], reverse=True)
        self.txt_procs.config(state="normal")
        self.txt_procs.delete("1.0", tk.END)

        if procs:
            max_vms = max(procs[0][1], 1)
            for name, mb, pid in procs[:30]:
                bar_len = int((mb / max_vms) * 12)
                bar = "█" * bar_len + "░" * (12 - bar_len)
                line = "  {:<28}  {:>9.1f}  {:>8}  {}\n".format(name, mb, pid, bar)
                self.txt_procs.insert(tk.END, line)

        self.lbl_proc_time.config(text=datetime.now().strftime("%H:%M:%S"))
        self.txt_procs.config(state="disabled")


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM TRAY
# ═══════════════════════════════════════════════════════════════════════════════
def setup_tray(app: VirtualMemoryApp):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, 62, 62], fill=(8, 6, 20, 255))
    draw.ellipse([2, 2, 62, 62], outline=(167, 139, 250, 255), width=4)
    draw.line([(16, 16), (32, 32)], fill=(167, 139, 250, 255), width=5)
    draw.line([(48, 16), (32, 32)], fill=(167, 139, 250, 255), width=5)
    draw.line([(16, 48), (32, 32)], fill=(167, 139, 250, 255), width=5)
    draw.line([(48, 48), (32, 32)], fill=(167, 139, 250, 255), width=5)

    menu = pystray.Menu(
        pystray.MenuItem("Abrir VirtualRAM Compressor",
                         lambda i, _: app.root.after(0, app.restore), default=True),
        pystray.MenuItem("🗜 Otimizar Swap", lambda i, _: app.engine.optimize_now()),
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

    icon = pystray.Icon("VRAMCompressor", img, "MemOptima VRAM v1.2", menu)
    app.set_tray(icon)
    icon.run_detached()
    return icon


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    cfg    = load_config()   # carrega config global (inclui chaves vram_*)
    engine = VirtualMemoryEngine(cfg)
    root   = tk.Tk()
    app    = VirtualMemoryApp(root, engine, cfg)
    tray   = setup_tray(app)
    root.mainloop()
    engine.stop()
    if tray:
        try:
            tray.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
