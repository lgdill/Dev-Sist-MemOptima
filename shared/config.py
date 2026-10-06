# -*- coding: utf-8 -*-
"""
shared/config.py — Persistência de configurações e log de otimizações.

Funções:
  load_config()   — carrega config.json com fallback para defaults
  save_config()   — grava config.json de forma ATÔMICA (write-tmp + rename)
  append_log()    — adiciona uma entrada ao optimization_log.jsonl
  load_log()      — lê as últimas N entradas do log persistido
"""

import os
import json
import shutil
import tempfile
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
_SCRIPT_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_FILE = os.path.join(_SCRIPT_DIR, "config.json")
_LOG_FILE    = os.path.join(_SCRIPT_DIR, "optimization_log.jsonl")

# ── Defaults ──────────────────────────────────────────────────────────────────
_DEFAULT_CONFIG = {
    # — Módulo principal (memoptima.py) —
    "limit_gb":           4.0,
    "interval_sec":       60,
    "auto_mode":          True,
    "use_filecache":      True,
    "whitelist":          [],
    "start_with_windows": False,
    # — Módulo VRAM Compressor —
    "vram_limit_gb":      4.0,
    "vram_interval_sec":  60,
    "vram_auto_mode":     False,
}

_MAX_LOG_ENTRIES = 200   # máximo de entradas persistidas em disco


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
def load_config() -> dict:
    """Carrega config.json, preenchendo chaves ausentes com os valores padrão.

    Returns:
        dict com a configuração completa (nunca lança exceção).
    """
    cfg = dict(_DEFAULT_CONFIG)
    try:
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg.update(saved)
    except Exception:
        pass
    return cfg


def save_config(cfg: dict) -> bool:
    """Grava cfg em config.json de forma ATÔMICA.

    A escrita é feita num arquivo temporário no mesmo diretório e depois
    renomeado atomicamente, evitando corrupção em caso de encerramento abrupto.
    Isso atende ao RNF12 da SPEC.

    Returns:
        True se bem-sucedido, False em caso de erro.
    """
    try:
        dir_path = os.path.dirname(_CONFIG_FILE)
        # Usar o mesmo diretório garante que o rename seja atômico (mesmo volume)
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            raise
        shutil.move(tmp_path, _CONFIG_FILE)
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# LOG PERSISTIDO
# ═══════════════════════════════════════════════════════════════════════════════
def append_log(entry: dict) -> None:
    """Adiciona uma entrada de otimização ao log persistido (JSONL).

    O arquivo é limitado a _MAX_LOG_ENTRIES linhas — entradas antigas são
    removidas quando o limite é atingido (rotação simples).

    Args:
        entry: dicionário com campos: timestamp, trigger, is_admin,
               layers, freed_mb, cleaned, skipped.
    """
    # Serializar timestamp se for objeto datetime
    if "timestamp" in entry and isinstance(entry["timestamp"], datetime):
        entry = dict(entry)
        entry["timestamp"] = entry["timestamp"].isoformat()

    line = json.dumps(entry, ensure_ascii=False) + "\n"
    try:
        # Ler todas as linhas existentes
        existing: list[str] = []
        if os.path.exists(_LOG_FILE):
            with open(_LOG_FILE, "r", encoding="utf-8") as f:
                existing = f.readlines()

        # Adicionar a nova entrada no topo, manter limite
        all_lines = [line] + existing
        if len(all_lines) > _MAX_LOG_ENTRIES:
            all_lines = all_lines[:_MAX_LOG_ENTRIES]

        # Escrever de volta de forma atômica
        dir_path = os.path.dirname(_LOG_FILE)
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.writelines(all_lines)
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            raise
        shutil.move(tmp_path, _LOG_FILE)
    except Exception:
        pass


def load_log(max_entries: int = 30) -> list[dict]:
    """Carrega as últimas `max_entries` entradas do log persistido.

    Returns:
        Lista de dicts com as entradas (mais recente primeiro).
        Retorna lista vazia se o arquivo não existir ou estiver corrompido.
    """
    entries = []
    try:
        if not os.path.exists(_LOG_FILE):
            return []
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(entries) >= max_entries:
                    break
    except Exception:
        pass
    return entries
