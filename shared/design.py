# -*- coding: utf-8 -*-
"""
shared/design.py — Design tokens (cores, fontes) do MemOptima.
Importado por memoptima.py e vram_compressor.py para garantir
consistência visual e eliminar duplicação.

Cada módulo pode sobrescrever NEON/NE2/NE_DIM para o seu tema:
  - memoptima.py    → tema Cyan/Neon Blue
  - vram_compressor → tema Violet
"""

# ── Base — paleta comum ────────────────────────────────────────────────────────
BG      = "#060913"   # Deep ocean background
CARD    = "#0b1021"   # Dark blue card
C2      = "#11182c"   # Secondary card
C3      = "#192440"   # Hover / input bg
WHT     = "#f8fafc"   # Bright text
GRY     = "#64748b"   # Slate text
WARN    = "#f59e0b"   # Amber warning
RED     = "#f43f5e"   # Rose red
BLU     = "#38bdf8"   # Info blue
BDR     = "#1e293b"   # Border
DRK     = "#020617"   # Dark text on bright bg
GRN     = "#00e676"   # Green

# ── Tema padrão (Cyan — memoptima.py) ─────────────────────────────────────────
NEON    = "#00d2ff"   # Cyan/Neon Blue (Primary)
NE2     = "#00a1cc"   # Cyan active state
NE_DIM  = "#002b3a"   # Cyan dimmed (track bg)
ACCNT   = "#a78bfa"   # Violet accent
AC_DIM  = "#1a162e"   # Accent dimmed

# ── Tema Violet (vram_compressor.py) — use como override ──────────────────────
VIOLET_NEON   = "#a78bfa"
VIOLET_NE2    = "#7c5cdb"
VIOLET_NE_DIM = "#1e1435"
VIOLET_ACCNT  = "#00d2ff"
VIOLET_C3     = "#1a1535"
