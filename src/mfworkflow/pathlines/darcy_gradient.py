#!/usr/bin/env python3
"""Trayectorias de flujo aproximadas desde el gradiente de carga (v = -K grad h).

Migrado desde 10_trayectorias/trayectorias_flujo.py. Aproximacion conceptual: no
calcula pathlines exactas ni tiempos de viaje (MODPATH 7 no esta disponible en
conda-forge ARM64). Usa el .hds del proyecto y parametros_modelo.csv.
"""

from __future__ import annotations

from pathlib import Path

import flopy
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def run(hds_path: Path, data_dir: Path, output_dir: Path) -> Path:
    """Genera campo de velocidad aproximado y streamplot. Devuelve la figura."""
    hds_path = Path(hds_path)
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not hds_path.exists():
        raise FileNotFoundError(f"Falta {hds_path.name}. Corre 'mfw run' primero.")

    params_frame = pd.read_csv(data_dir / "parametros_modelo.csv")
    params = {str(r["clave"]): float(r["valor"]) for _, r in params_frame.iterrows()}
    delr, delc, k = float(params["delr"]), float(params["delc"]), float(params["k"])

    # Porosidad efectiva: la velocidad ADVECTIVA (de poro) es q/n, no el flujo de
    # Darcy q. Necesaria para que las "velocidades" sean tiempos de viaje reales.
    porosidad = params.get("porosidad", params.get("porosidad_efectiva", None))
    if porosidad is None:
        capas = data_dir / "capas_modelo.csv"
        if capas.exists():
            df_c = pd.read_csv(capas)
            if "sy" in df_c.columns and len(df_c):
                porosidad = float(df_c.sort_values("layer").iloc[0]["sy"])
    porosidad = float(porosidad) if porosidad else 0.2  # default razonable

    hds = flopy.utils.HeadFile(str(hds_path), precision="double")
    times = hds.get_times()
    head = hds.get_data(totim=times[-1]) if times else hds.get_data()
    layer = np.asarray(head[0], dtype=float)

    dh_dy, dh_dx = np.gradient(layer, delc, delr)
    # Flujo especifico de Darcy (q = -K grad h) y velocidad de poro (v = q / n)
    qx = -k * dh_dx
    qy = -k * dh_dy
    vx = qx / porosidad
    vy = qy / porosidad

    nrow, ncol = layer.shape
    x = np.arange(ncol)
    y = np.arange(nrow)
    xx, yy = np.meshgrid(x, y)

    pd.DataFrame(
        {
            "row": yy.ravel(),
            "col": xx.ravel(),
            "head_m": layer.ravel(),
            "flujo_darcy_qx_m_d": qx.ravel(),
            "flujo_darcy_qy_m_d": qy.ravel(),
            "velocidad_poro_vx_m_d": vx.ravel(),
            "velocidad_poro_vy_m_d": vy.ravel(),
            "velocidad_poro_m_d": np.sqrt(vx**2 + vy**2).ravel(),
        }
    ).to_csv(output_dir / "campo_velocidad_aproximado.csv", index=False)

    fig, axis = plt.subplots(figsize=(9, 7))
    image = axis.imshow(layer, origin="lower", cmap="viridis")
    axis.streamplot(x, y, vx, vy, color="white", density=1.2, linewidth=0.8, arrowsize=1.0)
    axis.set_title(f"Trayectorias aproximadas (velocidad de poro, n={porosidad:.2f})")
    axis.set_xlabel("col")
    axis.set_ylabel("row")
    fig.colorbar(image, ax=axis, label="carga hidraulica (m)")
    fig.tight_layout()
    output = output_dir / "trayectorias_aproximadas.png"
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return output
