# -*- coding: utf-8 -*-
"""
shared/widgets.py — Widgets Tkinter reutilizáveis do MemOptima.

Classes:
  CircularGauge  — gauge circular animado com gradiente de cor por pressão
  Sparkline      — gráfico de histórico em tempo real com área preenchida
"""

import math
import tkinter as tk
from collections import deque

from shared.design import (
    BG, CARD, BDR, GRY, WHT, NEON, NE_DIM, RED, WARN
)


# ═══════════════════════════════════════════════════════════════════════════════
# CIRCULAR GAUGE WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class CircularGauge(tk.Canvas):
    """Gauge circular animado. Cor muda de NEON → WARN → RED conforme pressão.

    Args:
        parent: widget pai do Tkinter.
        size:   tamanho em pixels (quadrado). Padrão 190.
        neon_color: cor do arco em situação normal.
        warn_color: cor do arco em atenção (≥65%).
        red_color:  cor do arco em crítico (≥85%).
        label:  texto exibido abaixo da porcentagem (ex: "RAM", "SWAP").
    """

    def __init__(self, parent, size: int = 190,
                 neon_color: str = NEON, warn_color: str = WARN,
                 red_color: str = RED, label: str = "RAM",
                 **kwargs):
        super().__init__(parent, width=size, height=size,
                         bg=CARD, highlightthickness=0, **kwargs)
        self._sz       = size
        self._cx       = size / 2
        self._cy       = size / 2
        self._r        = size * 0.40
        self._lw       = int(size * 0.075)
        self._label    = label
        self._neon     = neon_color
        self._warn     = warn_color
        self._red      = red_color

        self._target   = 0.0
        self._current  = 0.0
        self._anim_id  = None
        self._draw(0.0)

    # ── Public API ────────────────────────────────────────────────────────────
    def set_value(self, pct: float) -> None:
        """Define o valor alvo (0–100). A animação interpola suavemente."""
        self._target = max(0.0, min(100.0, pct))
        if self._anim_id is None:
            self._animate()

    def set_label(self, label: str) -> None:
        """Atualiza o rótulo interno do gauge (ex: "SWAP USADO")."""
        self._label = label
        self._draw(self._current)

    # ── Internals ─────────────────────────────────────────────────────────────
    def _animate(self) -> None:
        diff = self._target - self._current
        if abs(diff) < 0.3:
            self._current = self._target
            self._anim_id = None
        else:
            self._current += diff * 0.12
            self._anim_id = self.after(16, self._animate)
        self._draw(self._current)

    def _color(self, pct: float) -> str:
        if pct >= 85:
            return self._red
        if pct >= 65:
            return self._warn
        return self._neon

    def _draw(self, pct: float) -> None:
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
                         text=self._label,
                         font=("Segoe UI", int(self._sz * 0.055)),
                         fill=GRY)

        # Indicator dot at arc tip
        if pct > 1:
            angle_rad = math.radians(135 - (pct / 100 * 270))
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
    """Gráfico de histórico em tempo real com linha suavizada e área preenchida.

    Args:
        parent:      widget pai.
        height:      altura em pixels.
        maxpoints:   quantidade máxima de pontos no histórico (ring buffer).
        line_color:  cor da linha e do ponto atual.
        fill_color:  cor da área sob a curva.
    """

    def __init__(self, parent, height: int = 52, maxpoints: int = 90,
                 line_color: str = None, fill_color: str = None, **kwargs):
        super().__init__(parent, height=height,
                         bg=CARD, highlightthickness=0, **kwargs)
        self._width  = 100   # fallback; atualizado no resize
        self._height = height
        self._data   = deque(maxlen=maxpoints)
        self._line_c = line_color if line_color is not None else NEON
        self._fill_c = fill_color if fill_color is not None else NE_DIM
        self.bind("<Configure>", self._on_resize)
        self._draw()

    # ── Public API ────────────────────────────────────────────────────────────
    def add(self, value: float) -> None:
        """Adiciona um valor (0–100) ao histórico e redesenha."""
        self._data.append(max(0.0, min(100.0, value)))
        self._draw()

    # ── Internals ─────────────────────────────────────────────────────────────
    def _on_resize(self, event) -> None:
        self._width = event.width
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        data = list(self._data)
        n    = len(data)
        if n < 2:
            return

        pad  = 4
        h    = self._height - pad * 2
        w    = self._width
        step = w / (n - 1)

        pts = [(i * step, pad + h - (v / 100.0) * h) for i, v in enumerate(data)]

        # Filled area under curve
        poly = [(0, self._height)] + pts + [(w, self._height)]
        self.create_polygon([c for p in poly for c in p],
                            fill=self._fill_c, outline="")

        # Line
        self.create_line([c for p in pts for c in p],
                         fill=self._line_c, width=2, smooth=True)

        # Current value dot
        lx, ly = pts[-1]
        self.create_oval(lx - 4, ly - 4, lx + 4, ly + 4,
                         fill=self._line_c, outline=BG, width=2)

        # Y-axis reference lines
        for pct_mark in (25, 50, 75, 100):
            yy = pad + h - (pct_mark / 100.0) * h
            self.create_line(0, yy, w, yy, fill=BDR, dash=(2, 6))
            self.create_text(w - 3, yy,
                             text="{}%".format(pct_mark),
                             font=("Consolas", 7), fill=GRY, anchor="e")
