#!/usr/bin/env python3
"""Evaluacion de ajuste entre cargas observadas y simuladas (Etapa 4 ASTM, D5981).

Primer escalon de la calibracion: no modifica parametros, pero cuantifica el error
(RMSE, MAE, sesgo, RMSE ponderado) que la calibracion formal debera minimizar.

Migrado desde 08_calibracion/evaluar_ajuste.py, desacoplado de rutas fijas.
"""

from __future__ import annotations

import logging
from pathlib import Path

import flopy
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

logger = logging.getLogger("yaku")


def load_simulated_heads(hds_path: Path, observations: pd.DataFrame) -> pd.DataFrame:
    """Extrae cargas simuladas para cada observacion, matching por stress_period si existe.

    Si la columna 'stress_period' esta presente y tiene valores >= 0, extrae la carga
    al tiempo correspondiente. Si no, usa el ultimo tiempo (comportamiento anterior).
    """
    hds = flopy.utils.HeadFile(str(hds_path), precision="double")
    times = hds.get_times()
    if not times:
        raise ValueError("El archivo HDS no contiene tiempos simulados.")

    has_sp = "stress_period" in observations.columns
    use_final = not has_sp

    if has_sp:
        sp_time_map = {i: t for i, t in enumerate(hds.get_times())}

    rows = []
    omitidas = 0
    for _, obs in observations.iterrows():
        layer = int(obs["layer"]) - 1
        row = int(obs["row"]) - 1
        col = int(obs["col"]) - 1

        if use_final:
            head_arr = hds.get_data(totim=times[-1])
            simulated = float(head_arr[layer, row, col])
        else:
            sp = int(obs.get("stress_period", -1))
            if sp < 0 or sp >= len(sp_time_map):
                head_arr = hds.get_data(totim=times[-1])
            else:
                head_arr = hds.get_data(totim=sp_time_map[sp])
            simulated = float(head_arr[layer, row, col])

        if not np.isfinite(simulated) or abs(simulated) >= 1e29:
            omitidas += 1
            continue
        observed = float(obs["head_observado_m"])
        weight = float(obs.get("peso", 1.0))
        residual = observed - simulated
        rows.append(
            {
                "nombre": obs["nombre"],
                "layer": int(obs["layer"]),
                "row": row,
                "col": col,
                "stress_period": int(obs.get("stress_period", -1)),
                "observado_m": observed,
                "simulado_m": simulated,
                "residual_m": residual,
                "peso": weight,
                "residual_ponderado_m": residual * weight,
                "grupo": obs.get("grupo", "niveles"),
            }
        )
    if omitidas:
        logger.warning("%d observacion(es) en celdas secas/inactivas omitidas del ajuste.", omitidas)
    return pd.DataFrame(rows)


def calculate_metrics(residuals: pd.DataFrame) -> pd.DataFrame:
    """Calcula metricas de ajuste (RMSE, MAE, sesgo, RMSE ponderado, NSE, R2, PBIAS)."""
    residual = residuals["residual_m"].to_numpy(dtype=float)
    weighted = residuals["residual_ponderado_m"].to_numpy(dtype=float)
    obs = residuals["observado_m"].to_numpy(dtype=float)
    sim = residuals["simulado_m"].to_numpy(dtype=float)
    obs_mean = float(np.mean(obs))
    ss_tot = float(np.sum((obs - obs_mean) ** 2))
    nse = float(1.0 - np.sum(residual**2) / ss_tot) if ss_tot > 0 else float("nan")
    r2 = float(np.corrcoef(obs, sim)[0, 1] ** 2) if len(obs) > 1 else float("nan")
    pbias = float(100.0 * np.sum(residual) / np.sum(obs)) if np.sum(obs) != 0 else float("nan")
    return pd.DataFrame(
        [
            {"metrica": "n_observaciones", "valor": float(len(residuals))},
            {"metrica": "rmse_m", "valor": float(np.sqrt(np.mean(residual**2)))},
            {"metrica": "mae_m", "valor": float(np.mean(np.abs(residual)))},
            {"metrica": "sesgo_m", "valor": float(np.mean(residual))},
            {"metrica": "rmse_ponderado_m", "valor": float(np.sqrt(np.mean(weighted**2)))},
            {"metrica": "nse", "valor": nse, "interpretacion": ">0.5 bueno, >0.7 muy bueno (SEIA)"},
            {"metrica": "r2", "valor": r2, "interpretacion": "correlacion al cuadrado"},
            {"metrica": "pbias_pct", "valor": pbias, "interpretacion": "sesgo porcentual, ideal < |10|%"},
        ]
    )


def plot_observed_vs_simulated(residuals: pd.DataFrame, output_path: Path) -> None:
    fig, axis = plt.subplots(figsize=(6, 6))
    axis.scatter(residuals["observado_m"], residuals["simulado_m"], s=70)
    min_value = min(residuals["observado_m"].min(), residuals["simulado_m"].min())
    max_value = max(residuals["observado_m"].max(), residuals["simulado_m"].max())
    axis.plot([min_value, max_value], [min_value, max_value], "k--", label="1:1")
    axis.set_xlabel("Carga observada (m)")
    axis.set_ylabel("Carga simulada (m)")
    axis.set_title("Observado vs simulado")
    axis.grid(alpha=0.3)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def evaluate_fit(hds_path: Path, observations_path: Path, output_dir: Path) -> pd.DataFrame:
    """Evalua el ajuste y escribe residuales, metricas y grafico. Devuelve las metricas."""
    hds_path = Path(hds_path)
    observations_path = Path(observations_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not hds_path.exists():
        raise FileNotFoundError(f"No existe HDS: {hds_path}. Corre 'yaku run' primero.")
    if not observations_path.exists():
        raise FileNotFoundError(f"Falta archivo de observaciones: {observations_path}")

    observations = pd.read_csv(observations_path)
    residuals = load_simulated_heads(hds_path, observations)
    metrics = calculate_metrics(residuals)

    residuals.to_csv(output_dir / "residuales_observaciones.csv", index=False)
    metrics.to_csv(output_dir / "metricas_ajuste.csv", index=False)
    plot_observed_vs_simulated(residuals, output_dir / "grafico_observado_vs_simulado.png")
    return metrics
