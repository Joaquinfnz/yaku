#!/usr/bin/env python3
"""Análisis de sensibilidad one-at-a-time (OAT) de los parámetros de calibración.

Para cada parámetro de `parametros_calibracion.csv`, lo perturba +/- un delta, reconstruye
y corre el modelo, y mide el cambio en el RMSE de las observaciones. Es el análisis que la
Guía SEA pide para identificar los parámetros más influyentes. Más barato que PEST++; para
sensibilidad formal usar pestpp-glm.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from yaku.builder import ModflowModelBuilder
from yaku.calibration.evaluate import calculate_metrics, load_simulated_heads

logger = logging.getLogger("yaku")


def _copiar(data_dir: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for csv in Path(data_dir).glob("*.csv"):
        shutil.copy(csv, dest / csv.name)
    return dest


def _aplicar(definicion: pd.Series, data_dir: Path, factor: float) -> None:
    """Aplica el parámetro perturbado (multiplicador o valor) a su CSV."""
    path = data_dir / str(definicion["archivo"])
    if not path.exists():
        return
    frame = pd.read_csv(path)
    campo, selector, tipo = str(definicion["campo"]), str(definicion["selector"]), str(definicion["tipo"])
    mask = pd.Series(True, index=frame.index)
    if "=" in selector:
        clave, valor = selector.split("=", 1)
        mask = frame[clave.strip()].astype(str) == valor.strip()
    base = float(definicion["valor_inicial"])
    if tipo == "multiplicador":
        frame.loc[mask, campo] = frame.loc[mask, campo].astype(float) * factor
    else:  # valor_capa
        frame.loc[mask, campo] = base * factor
    frame.to_csv(path, index=False)


def _rmse(data_dir: Path, ws: Path, obs: pd.DataFrame, model_name: str,
          drapear_dem: bool = False) -> float | None:
    try:
        ModflowModelBuilder(data_dir, ws, model_name=model_name,
                            drapear_dem=drapear_dem).build_and_run(postprocess=False)
        residuals = load_simulated_heads(ws / f"{model_name}.hds", obs)
        metrics = dict(zip(calculate_metrics(residuals)["metrica"], calculate_metrics(residuals)["valor"]))
        return float(metrics["rmse_m"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("sensibilidad: una corrida falló (%s).", exc)
        return None


def sensibilidad_oat(data_dir: Path, calib_params: Path, obs_path: Path, output_dir: Path,
                     *, model_name: str = "modelo", delta: float = 0.1,
                     drapear_dem: bool = False) -> pd.DataFrame:
    """Corre OAT y escribe sensibilidad.csv. Devuelve el DataFrame de sensibilidad."""
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    defs = pd.read_csv(calib_params)
    obs = pd.read_csv(obs_path)

    filas = []
    with tempfile.TemporaryDirectory(prefix="mfw_sens_") as tmp:
        tmp = Path(tmp)
        rmse_base = _rmse(_copiar(data_dir, tmp / "base"), tmp / "wbase", obs, model_name, drapear_dem)
        for i, d in defs.iterrows():
            nombre = str(d["nombre"])
            rmses = {}
            for etiqueta, factor in (("mas", 1.0 + delta), ("menos", 1.0 - delta)):
                di = _copiar(data_dir, tmp / f"d{i}_{etiqueta}")
                _aplicar(d, di, factor)
                rmses[etiqueta] = _rmse(di, tmp / f"w{i}_{etiqueta}", obs, model_name, drapear_dem)
            if rmses["mas"] is None or rmses["menos"] is None:
                continue
            sens = abs(rmses["mas"] - rmses["menos"]) / (2.0 * delta)
            filas.append({
                "parametro": nombre,
                "rmse_base_m": round(rmse_base, 4) if rmse_base else None,
                "rmse_+10%_m": round(rmses["mas"], 4),
                "rmse_-10%_m": round(rmses["menos"], 4),
                "sensibilidad": round(sens, 4),
            })

    df = pd.DataFrame(filas).sort_values("sensibilidad", ascending=False).reset_index(drop=True)
    out = output_dir / "sensibilidad.csv"
    df.to_csv(out, index=False)
    logger.info("Sensibilidad (OAT, ±%.0f%%): %d parámetros -> %s", delta * 100, len(df), out.name)
    return df
