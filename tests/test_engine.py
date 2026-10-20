# -*- coding: utf-8 -*-
"""
tests/test_engine.py -- Testes unitarios para OptimizationEngine

Cobre:
  - Swap Lock: camadas agressivas bloqueadas quando swap > swap_lock_gb
  - Whitelist: processo protegido e contabilizado em 'skipped', nao em 'cleaned'
  - Anti-Thrashing: processo com spike de page faults e poupado
  - Auto-Modo: disparo quando RAM ultrapassa o limite configurado
  - swap_lock_gb: lido do config e persistido em get_config_dict
"""

import os
import sys
import time
import threading
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# -- Helpers de mock -----------------------------------------------------------

def _make_mem(used_gb, total_gb=8.0, percent=None):
    m = MagicMock()
    m.used      = int(used_gb  * 1024 ** 3)
    m.total     = int(total_gb * 1024 ** 3)
    m.available = m.total - m.used
    m.percent   = percent if percent is not None else (used_gb / total_gb * 100)
    return m


def _make_swap(used_gb):
    s = MagicMock()
    s.used = int(used_gb * 1024 ** 3)
    return s


def _make_proc(name, pid, cpu=0.0, rss_mb=100.0, page_faults=0):
    p = MagicMock()
    p.info = {
        'pid':         pid,
        'name':        name,
        'cpu_percent': cpu,
        'memory_info': MagicMock(rss=int(rss_mb * 1024 * 1024),
                                 num_page_faults=page_faults),
    }
    return p


def _get_engine_class():
    import shared.win_api as wa
    wa.IS_WINDOWS = False
    wa.IS_ADMIN   = False
    if 'memoptima' in sys.modules:
        del sys.modules['memoptima']
    import memoptima as m
    return m.OptimizationEngine


def _windows_patches():
    """
    Patches que fazem o engine acreditar que esta no Windows sem admin.
    Inclui as referencias do modulo memoptima (nao apenas shared.win_api)
    porque o engine usa as referencias importadas no topo do arquivo.
    """
    import memoptima as m
    return [
        patch.object(m, 'IS_WINDOWS',          True),
        patch.object(m, 'IS_ADMIN',             False),
        patch.object(m, '_OpenProcess',         lambda *a: 1),
        patch.object(m, '_EmptyWS',             lambda *a: True),
        patch.object(m, '_CloseHandle',         lambda *a: True),
        patch.object(m, '_GetCurrentProcess',   lambda: 1),
        patch.object(m, '_get_foreground_pid',  lambda: 0),
        patch.object(m, 'PROC_ACCESS',          0x0400),  # garante handle valido
    ]


def _run_optimize(engine, procs=None, swap_gb=0.5, ram_gb=3.5):
    """Executa _do_optimize com mocks e retorna o dict 'done'."""
    if procs is None:
        procs = []
    results = []
    engine.register_callback(lambda ev, d: results.append((ev, d)))
    patches = _windows_patches()
    for p in patches:
        p.start()
    try:
        with patch('psutil.virtual_memory', return_value=_make_mem(ram_gb)), \
             patch('psutil.swap_memory',    return_value=_make_swap(swap_gb)), \
             patch('psutil.process_iter',   return_value=procs):
            engine._do_optimize("manual")
    finally:
        for p in patches:
            p.stop()
    return next(d for ev, d in results if ev == "done")


# == TESTES ====================================================================

class TestSwapLock(unittest.TestCase):
    """RF14 / RNF03 -- Swap Lock bloqueia camadas agressivas quando swap > limite."""

    def setUp(self):
        EngineClass = _get_engine_class()
        self.engine = EngineClass({"limit_gb": 3.0, "interval_sec": 60,
                                   "auto_mode": False, "swap_lock_gb": 4.0})
        self.engine.running = False

    def test_swap_lock_blocks_when_above_limit(self):
        """Swap Lock ativo: 'Swap Lock' nas camadas e cleaned == 0."""
        done = _run_optimize(self.engine, swap_gb=5.0)
        self.assertEqual(done["cleaned"], 0)
        self.assertTrue(any("Swap Lock" in l for l in done["layers"]),
                        "Esperado 'Swap Lock'. Obtido: {}".format(done["layers"]))

    def test_swap_below_limit_no_swap_lock(self):
        """Swap abaixo do limite: sem mensagem de Swap Lock."""
        done = _run_optimize(self.engine, swap_gb=1.0)
        self.assertFalse(any("Swap Lock" in l for l in done["layers"]))

    def test_swap_lock_gb_read_from_config(self):
        """swap_lock_gb e lido do config, nao hardcoded."""
        EngineClass = _get_engine_class()
        engine = EngineClass({"swap_lock_gb": 2.5})
        engine.running = False
        self.assertAlmostEqual(engine.swap_lock_gb, 2.5)

    def test_swap_lock_default_is_4gb(self):
        """Valor padrao de swap_lock_gb e 4.0 GB."""
        EngineClass = _get_engine_class()
        engine = EngineClass({})
        engine.running = False
        self.assertAlmostEqual(engine.swap_lock_gb, 4.0)

    def test_swap_lock_gb_in_config_dict(self):
        """swap_lock_gb deve estar em get_config_dict."""
        cfg = self.engine.get_config_dict()
        self.assertIn("swap_lock_gb", cfg)
        self.assertAlmostEqual(cfg["swap_lock_gb"], 4.0)


class TestWhitelist(unittest.TestCase):
    """RF12 / RF13 -- Processos na whitelist sao pulados, nao trimados."""

    def setUp(self):
        EngineClass = _get_engine_class()
        self.engine = EngineClass({
            "limit_gb": 3.0, "interval_sec": 60,
            "auto_mode": False, "swap_lock_gb": 99.0,
            "whitelist": ["chrome.exe"],
        })
        self.engine.running = False

    def test_whitelisted_process_is_skipped(self):
        """Processo na whitelist: skipped > 0 e cleaned == 0."""
        proc = _make_proc("chrome.exe", pid=1234, cpu=0.0)
        done = _run_optimize(self.engine, procs=[proc])
        self.assertEqual(done["cleaned"], 0)
        self.assertGreater(done["skipped"], 0)

    def test_high_cpu_process_is_skipped(self):
        """Processo com CPU > 2%: skipped > 0 e cleaned == 0."""
        proc = _make_proc("busy.exe", pid=5678, cpu=50.0)
        done = _run_optimize(self.engine, procs=[proc])
        self.assertEqual(done["cleaned"], 0)
        self.assertGreater(done["skipped"], 0)

    def test_normal_process_is_cleaned(self):
        """Processo sem protecao e com CPU baixo: cleaned > 0."""
        proc = _make_proc("notepad.exe", pid=9999, cpu=0.0)
        done = _run_optimize(self.engine, procs=[proc])
        self.assertGreater(done["cleaned"], 0)
        self.assertEqual(done["skipped"], 0)


class TestAntiThrashing(unittest.TestCase):
    """RNF04 -- Processos com spike de page faults sao poupados."""

    def setUp(self):
        EngineClass = _get_engine_class()
        self.engine = EngineClass({
            "limit_gb": 3.0, "interval_sec": 60,
            "auto_mode": False, "swap_lock_gb": 99.0,
        })
        self.engine.running = False

    def test_page_fault_spike_skips_process(self):
        """Delta > 1000 page faults: processo e poupado."""
        pid = 9999
        _run_optimize(self.engine, procs=[_make_proc("heavy.exe", pid=pid, page_faults=1000)])
        done = _run_optimize(self.engine, procs=[_make_proc("heavy.exe", pid=pid, page_faults=3000)])
        self.assertGreater(done["skipped"], 0)
        self.assertEqual(done["cleaned"], 0)

    def test_stable_page_faults_not_skipped(self):
        """Delta <= 1000 page faults: processo e trimado normalmente."""
        pid = 1111
        _run_optimize(self.engine, procs=[_make_proc("stable.exe", pid=pid, page_faults=500)])
        done = _run_optimize(self.engine, procs=[_make_proc("stable.exe", pid=pid, page_faults=700)])
        self.assertGreater(done["cleaned"], 0)


class TestAutoMode(unittest.TestCase):
    """RF08 / RF09 -- Auto-Modo dispara quando RAM > limite."""

    def setUp(self):
        EngineClass = _get_engine_class()
        self.engine = EngineClass({
            "limit_gb": 2.0, "interval_sec": 5,
            "auto_mode": True, "swap_lock_gb": 99.0,
        })

    def tearDown(self):
        self.engine.running = False

    def test_auto_mode_triggers_above_limit(self):
        """Auto-Modo dispara quando RAM > limit_gb."""
        triggered = threading.Event()
        results   = []

        def cb(ev, d):
            if ev == "done" and d.get("trigger") == "auto":
                results.append(d)
                triggered.set()

        self.engine.register_callback(cb)
        patches = _windows_patches()
        for p in patches:
            p.start()

        self.engine._last_ts = 0.0
        try:
            with patch('psutil.virtual_memory', return_value=_make_mem(3.0, percent=75.0)), \
                 patch('psutil.swap_memory',    return_value=_make_swap(0.5)), \
                 patch('psutil.process_iter',   return_value=[]):
                fired = triggered.wait(timeout=15)
        finally:
            for p in patches:
                p.stop()

        self.assertTrue(fired, "Auto-Modo nao disparou dentro do tempo esperado")
        self.assertEqual(results[0]["trigger"], "auto")

    def test_auto_mode_off_never_triggers(self):
        """Com Auto-Modo OFF nenhuma otimizacao automatica ocorre."""
        self.engine.auto_mode = False
        results = []
        self.engine.register_callback(lambda ev, d: results.append((ev, d)))
        time.sleep(0.5)
        auto_runs = [d for ev, d in results if ev == "done" and d.get("trigger") == "auto"]
        self.assertEqual(len(auto_runs), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
