#!/usr/bin/env python3
"""Primitivas de dibujo de mapas del informe (planta georreferenciada).

Isopiezas con niveles redondos (Guia SEA: 10-20 m), flecha de norte, barra de
escala y vectores de flujo. Las usan resultados.py y calibration/predict.py.
"""

from __future__ import annotations

from pathlib import Path

import flopy
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _paso_redondo(rango: float, divisiones: int = 8) -> float:
    """Paso 'redondo' (1/2/5·10ⁿ) para curvas de nivel o barras de escala."""
    if rango <= 0:
        return 1.0
    objetivo = rango / divisiones
    for paso in (0.5, 1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000):
        if paso >= objetivo:
            return float(paso)
    return float(paso)


def _niveles_isopiezas(data: np.ndarray):
    """Niveles 'redondos' para isopiezas (~8 contornos; la Guía SEA pide 10–20 m)."""
    v = data.compressed() if isinstance(data, np.ma.MaskedArray) else np.asarray(data, float).ravel()
    v = v[np.isfinite(v)]
    if v.size < 4 or v.max() <= v.min():
        return None
    paso = _paso_redondo(float(v.max() - v.min()))
    lo = np.floor(v.min() / paso) * paso
    hi = np.ceil(v.max() / paso) * paso
    niveles = np.arange(lo, hi + paso, paso)
    return niveles if niveles.size >= 2 else None


def _norte_y_escala(ax, grid) -> None:
    """Flecha de norte (arriba-derecha) y barra de escala en metros (abajo-izquierda)."""
    ax.annotate("N", xy=(0.95, 0.95), xytext=(0.95, 0.80), xycoords="axes fraction",
                ha="center", va="center", fontsize=11, fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color="k", lw=1.6))
    try:
        xmin, xmax, ymin, ymax = grid.extent
    except Exception:  # noqa: BLE001
        return
    ancho, alto = xmax - xmin, ymax - ymin
    if ancho <= 0:
        return
    largo = _paso_redondo(ancho, divisiones=4)
    if largo > ancho / 2.0:
        largo = _paso_redondo(ancho, divisiones=8)
    x0 = xmin + 0.06 * ancho
    y0 = ymin + 0.06 * alto
    ax.plot([x0, x0 + largo], [y0, y0], color="k", lw=3, solid_capstyle="butt", zorder=5)
    etiqueta = f"{largo / 1000:.0f} km" if largo >= 1000 else f"{largo:.0f} m"
    ax.text(x0 + largo / 2, y0 + 0.02 * alto, etiqueta, ha="center", va="bottom",
            fontsize=8, zorder=5)


def _dibujar_mapa(data, grid, png: Path, *, titulo: str, cbar_label: str,
                  cmap: str = "viridis", isopiezas: bool = False, vectores=None) -> Path:
    """Dibuja un mapa en planta. Con grilla estructurada va georreferenciado (UTM):
    isopiezas etiquetadas, flecha de norte y barra de escala. Sin grilla cae a fila/columna.
    `vectores=(qx, qy)` (2D) superpone vectores de flujo (direccion del agua subterranea).
    """
    png.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    if grid is not None and getattr(grid, "grid_type", "") == "structured":
        pmv = flopy.plot.PlotMapView(modelgrid=grid, ax=ax)
        quad = pmv.plot_array(data, cmap=cmap)
        if isopiezas:
            try:
                cs = pmv.contour_array(data, levels=_niveles_isopiezas(data),
                                       colors="0.15", linewidths=0.6)
                if cs is not None and cs.levels.size:
                    ax.clabel(cs, fmt="%.0f", fontsize=7, inline=True)
            except Exception:  # noqa: BLE001
                pass
        if vectores is not None:
            try:
                qx, qy = vectores
                paso = max(1, min(grid.nrow, grid.ncol) // 18)   # ralea los vectores
                pmv.plot_vector(qx, qy, normalize=True, istep=paso, jstep=paso,
                                color="0.2", scale=35, width=0.0025, headwidth=3)
            except Exception:  # noqa: BLE001
                pass
        ax.set_xlabel("Este (m)")
        ax.set_ylabel("Norte (m)")
        ax.set_aspect("equal")
        ax.ticklabel_format(style="plain", useOffset=False)
        _norte_y_escala(ax, grid)
        fig.colorbar(quad, ax=ax, label=cbar_label, shrink=0.85)
    else:
        im = ax.imshow(data, origin="lower", cmap=cmap)
        ax.set_xlabel("columna")
        ax.set_ylabel("fila")
        fig.colorbar(im, ax=ax, label=cbar_label)
    ax.set_title(titulo)
    fig.tight_layout()
    fig.savefig(png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return png
