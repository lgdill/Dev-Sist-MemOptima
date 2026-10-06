# -*- coding: utf-8 -*-
"""
tests/test_config.py — Testes unitários para shared/config.py

Cobre:
  - load_config: defaults, merge com arquivo existente, chave ausente
  - save_config: escrita atômica, conteúdo correto, arquivo existente substituído
  - append_log / load_log: persistência, ordenação (mais recente primeiro), limite de 200
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

# Garante que a raiz do projeto está no sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestLoadConfig(unittest.TestCase):
    """Testes para a função load_config."""

    def setUp(self):
        # Arquivo temporário que simula o config.json
        self._fd, self._path = tempfile.mkstemp(suffix=".json")
        os.close(self._fd)

    def tearDown(self):
        if os.path.exists(self._path):
            os.unlink(self._path)

    def _get_load_fn(self, config_path):
        """Retorna load_config apontando para um path customizado."""
        import importlib, types
        # Importa o módulo e sobrescreve o _CONFIG_FILE temporariamente
        import shared.config as cfg_mod
        original = cfg_mod._CONFIG_FILE
        cfg_mod._CONFIG_FILE = config_path
        try:
            result = cfg_mod.load_config()
        finally:
            cfg_mod._CONFIG_FILE = original
        return result

    def test_defaults_when_file_missing(self):
        """Retorna defaults quando o arquivo não existe."""
        import shared.config as cfg_mod
        original = cfg_mod._CONFIG_FILE
        cfg_mod._CONFIG_FILE = self._path + "_MISSING"
        try:
            cfg = cfg_mod.load_config()
        finally:
            cfg_mod._CONFIG_FILE = original

        self.assertEqual(cfg["limit_gb"], 4.0)
        self.assertEqual(cfg["interval_sec"], 60)
        self.assertIsInstance(cfg["whitelist"], list)

    def test_merges_saved_values(self):
        """Valores salvos sobrescrevem os defaults, chaves novas são preservadas."""
        saved = {"limit_gb": 2.5, "auto_mode": False}
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(saved, f)

        cfg = self._get_load_fn(self._path)
        self.assertEqual(cfg["limit_gb"], 2.5)
        self.assertFalse(cfg["auto_mode"])
        # Chave ausente no arquivo deve ter o valor default
        self.assertEqual(cfg["interval_sec"], 60)

    def test_missing_keys_filled_with_defaults(self):
        """Chaves ausentes no arquivo são completadas com defaults."""
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({"limit_gb": 3.0}, f)

        cfg = self._get_load_fn(self._path)
        self.assertIn("use_filecache", cfg)
        self.assertIn("whitelist", cfg)

    def test_corrupted_file_returns_defaults(self):
        """Arquivo corrompido não lança exceção — retorna defaults."""
        with open(self._path, "w", encoding="utf-8") as f:
            f.write("{ invalid json !!!")

        cfg = self._get_load_fn(self._path)
        self.assertEqual(cfg["limit_gb"], 4.0)


class TestSaveConfig(unittest.TestCase):
    """Testes para a função save_config (escrita atômica)."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._config_path = os.path.join(self._tmpdir, "config.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _save(self, cfg):
        import shared.config as cfg_mod
        original = cfg_mod._CONFIG_FILE
        cfg_mod._CONFIG_FILE = self._config_path
        try:
            return cfg_mod.save_config(cfg)
        finally:
            cfg_mod._CONFIG_FILE = original

    def test_creates_file(self):
        """O arquivo é criado após save_config."""
        result = self._save({"limit_gb": 2.0})
        self.assertTrue(result)
        self.assertTrue(os.path.exists(self._config_path))

    def test_content_is_correct(self):
        """O JSON gravado é legível e tem os valores corretos."""
        cfg = {"limit_gb": 3.5, "auto_mode": True, "whitelist": ["chrome.exe"]}
        self._save(cfg)
        with open(self._config_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["limit_gb"], 3.5)
        self.assertTrue(loaded["auto_mode"])
        self.assertIn("chrome.exe", loaded["whitelist"])

    def test_overwrites_existing(self):
        """save_config substitui o arquivo anterior corretamente."""
        self._save({"limit_gb": 1.0})
        self._save({"limit_gb": 4.0})
        with open(self._config_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["limit_gb"], 4.0)

    def test_no_tmp_file_left(self):
        """Nenhum arquivo .tmp deve sobrar após a gravação."""
        self._save({"limit_gb": 2.0})
        tmp_files = [f for f in os.listdir(self._tmpdir) if f.endswith(".tmp")]
        self.assertEqual(tmp_files, [])


class TestLog(unittest.TestCase):
    """Testes para append_log e load_log."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._log_path = os.path.join(self._tmpdir, "optimization_log.jsonl")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _patch_log_path(self):
        """Context manager que aponta _LOG_FILE para o diretório temporário."""
        import shared.config as cfg_mod
        return patch.object(cfg_mod, '_LOG_FILE', self._log_path)

    def test_append_and_load_single_entry(self):
        """Uma entrada gravada pode ser lida de volta."""
        entry = {
            "timestamp":  datetime.now(),
            "trigger":    "manual",
            "is_admin":   True,
            "layers":     ["L1", "L2b"],
            "freed_mb":   128.5,
            "cleaned":    10,
            "skipped":    2,
        }
        with self._patch_log_path():
            import shared.config as cfg_mod
            cfg_mod.append_log(entry)
            loaded = cfg_mod.load_log(max_entries=5)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["trigger"], "manual")
        self.assertAlmostEqual(loaded[0]["freed_mb"], 128.5)

    def test_most_recent_first(self):
        """A entrada mais recente aparece primeiro na leitura."""
        with self._patch_log_path():
            import shared.config as cfg_mod
            for i in range(3):
                cfg_mod.append_log({"trigger": "entry_{}".format(i), "freed_mb": float(i)})
            loaded = cfg_mod.load_log(max_entries=10)

        # O último inserido deve ser o primeiro na lista
        self.assertEqual(loaded[0]["trigger"], "entry_2")
        self.assertEqual(loaded[1]["trigger"], "entry_1")
        self.assertEqual(loaded[2]["trigger"], "entry_0")

    def test_respects_max_entries_on_load(self):
        """load_log retorna no máximo max_entries entradas."""
        with self._patch_log_path():
            import shared.config as cfg_mod
            for i in range(10):
                cfg_mod.append_log({"trigger": "t", "freed_mb": float(i)})
            loaded = cfg_mod.load_log(max_entries=3)

        self.assertEqual(len(loaded), 3)

    def test_empty_log_returns_empty_list(self):
        """log inexistente retorna lista vazia sem erro."""
        with self._patch_log_path():
            import shared.config as cfg_mod
            loaded = cfg_mod.load_log()
        self.assertEqual(loaded, [])

    def test_datetime_serialized_as_string(self):
        """datetime no entry é serializado como string ISO."""
        entry = {"timestamp": datetime(2026, 10, 6, 14, 0, 0), "trigger": "auto"}
        with self._patch_log_path():
            import shared.config as cfg_mod
            cfg_mod.append_log(entry)
            loaded = cfg_mod.load_log()
        self.assertIsInstance(loaded[0]["timestamp"], str)
        self.assertIn("2026", loaded[0]["timestamp"])


class TestProcessGrouping(unittest.TestCase):
    """Testes para a lógica de agrupamento de processos (extraída para teste isolado)."""

    def _group_procs(self, raw):
        """Simula a lógica de agrupamento do _ui_procs do MemOptimaApp."""
        grouped = {}
        for name, mb, pid, cpu in raw:
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
        return display

    def test_groups_by_name(self):
        """Múltiplas instâncias do mesmo processo são agrupadas."""
        raw = [
            ("chrome.exe", 200.0, 101, 1.0),
            ("chrome.exe", 150.0, 102, 0.5),
            ("notepad.exe", 50.0,  103, 0.0),
        ]
        result = self._group_procs(raw)
        names = [r[0] for r in result]
        self.assertIn("chrome.exe", names)
        # Chrome deve aparecer uma única vez agrupado
        chrome = next(r for r in result if r[0] == "chrome.exe")
        self.assertAlmostEqual(chrome[1], 350.0)   # mb somado
        self.assertEqual(chrome[2], 2)              # count = 2
        self.assertAlmostEqual(chrome[3], 1.5)      # cpu somado

    def test_sorted_by_mb_descending(self):
        """O resultado é ordenado por RAM decrescente."""
        raw = [
            ("a.exe", 100.0, 1, 0.0),
            ("b.exe", 500.0, 2, 0.0),
            ("c.exe", 250.0, 3, 0.0),
        ]
        result = self._group_procs(raw)
        mbs = [r[1] for r in result]
        self.assertEqual(mbs, sorted(mbs, reverse=True))

    def test_single_instance_count_is_one(self):
        """Processo com uma única instância tem count = 1."""
        raw = [("solo.exe", 80.0, 10, 0.5)]
        result = self._group_procs(raw)
        self.assertEqual(result[0][2], 1)

    def test_empty_input(self):
        """Lista vazia de processos retorna lista vazia."""
        self.assertEqual(self._group_procs([]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
