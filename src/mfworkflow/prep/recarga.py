#!/usr/bin/env python3
"""Recarga desde clima, DENTRO del workflow (sin modelos hidrologicos externos).

Convierte una serie climatica (precipitacion y, si esta, evapotranspiracion) en
recarga por periodo, con un balance de suelo simple tipo Thornthwaite-Mather. Escribe
`recarga_periodos.csv`, que el motor ya usa como recarga (transiente) del modelo.

Formato de `datos/fuente/clima.csv` (una fila por periodo, p.ej. mensual):
    fecha, precip_mm, temp_c, et0_mm
`precip_mm` es obligatoria; `et0_mm` es lo ideal (si no esta, se estima con `temp_c`).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger("mfworkflow")


def balance_suelo(precip_mm, pet_mm, *, cc_mm: float = 100.0,
                  coef_escorrentia: float = 0.0, soil_inicial: float | None = None) -> list[float]:
    """Recarga (mm) por periodo con un balance de suelo (Thornthwaite-Mather simplificado).

    Para cada periodo: la lluvia que no escurre (P*(1-esc)) menos la ET potencial llena
    primero el almacenamiento del suelo (hasta `cc_mm`); el excedente es recarga. Si el
    balance es negativo, el suelo se seca y no hay recarga.
    """
    soil = float(cc_mm if soil_inicial is None else soil_inicial)
    recargas: list[float] = []
    for P, PET in zip(precip_mm, pet_mm):
        balance = float(P) * (1.0 - coef_escorrentia) - float(PET)
        if balance >= 0:
            espacio = cc_mm - soil
            if balance <= espacio:
                soil += balance
                rec = 0.0
            else:
                soil = cc_mm
                rec = balance - espacio
        else:
            soil = max(0.0, soil + balance)
            rec = 0.0
        recargas.append(max(0.0, rec))
    return recargas


def _pet_desde_temp(temp_c: np.ndarray) -> np.ndarray:
    """ET potencial aproximada cuando no hay et0 (estimacion gruesa por temperatura)."""
    # Aproximacion simple y conservadora: ~5 mm por grado positivo y periodo.
    return np.clip(temp_c, 0, None) * 5.0


def _dias_por_periodo(df: pd.DataFrame, n: int) -> np.ndarray:
    """Dias de cada periodo: desde la columna 'fecha' si se puede, si no ~30.44."""
    if "fecha" in df.columns:
        try:
            fechas = pd.to_datetime(df["fecha"])
            dias = fechas.diff().dt.days.bfill()
            dias = dias.fillna(30.44).to_numpy(dtype=float)
            dias[dias <= 0] = 30.44
            return dias
        except Exception:  # noqa: BLE001
            pass
    return np.full(n, 30.44)


def _es_diario(df: pd.DataFrame) -> bool:
    """True si clima.csv tiene paso ~diario (mediana de dias entre filas <= 20)."""
    if "fecha" not in df.columns:
        return False
    try:
        d = pd.to_datetime(df["fecha"]).diff().dt.days.dropna()
        return bool(d.median() <= 20)
    except Exception:  # noqa: BLE001
        return False


def calcular_recarga(clima_path: Path, tablas_dir: Path, *, metodo: str = "balance",
                     cc_mm: float = 100.0, coef_infiltracion: float = 0.15,
                     coef_escorrentia: float = 0.1, k_percolacion: float = 1.0,
                     transiente: bool = False, freq: str = "MS") -> dict:
    """Lee clima.csv y escribe recarga_periodos.csv (recarga por periodo de stress).

    metodo: 'balance' (suelo, usa precip+ET) o 'coeficiente' (recarga = coef*precip).
    Si clima.csv es DIARIO usa el balance de suelo diario (con percolacion) y agrega a periodos
    `freq` (mensual por defecto). Con `transiente=True` ademas escribe stress_periods.csv alineado
    (1.er periodo permanente + resto transiente), para correr la serie multianual como transiente.
    """
    from mfworkflow.hidrologia import agregar_a_periodos, balance_suelo_diario

    clima_path = Path(clima_path)
    tablas_dir = Path(tablas_dir)
    df = pd.read_csv(clima_path)
    if "precip_mm" not in df.columns:
        raise ValueError("clima.csv debe tener al menos la columna 'precip_mm'.")

    precip = df["precip_mm"].astype(float).to_numpy()
    if "et0_mm" in df.columns:
        pet = df["et0_mm"].astype(float).to_numpy()
    elif "temp_c" in df.columns:
        pet = _pet_desde_temp(df["temp_c"].astype(float).to_numpy())
        logger.warning("clima.csv sin 'et0_mm'; ET estimada desde 'temp_c' (aproximada).")
    else:
        pet = np.zeros(len(precip))

    tablas_dir.mkdir(parents=True, exist_ok=True)
    diario = _es_diario(df)

    if diario and metodo == "balance":
        # Balance de suelo DIARIO -> serie diaria -> agregada a periodos (mensual)
        rec_diaria = balance_suelo_diario(precip, pet, cc_mm=cc_mm,
                                          coef_escorrentia=coef_escorrentia, k_percolacion=k_percolacion)
        agg = agregar_a_periodos(df["fecha"], rec_diaria, freq=freq)
        n = len(agg)
        rec_m_d = (agg["media_mm_d"] / 1000.0).to_numpy()
        dias = agg["dias"].to_numpy()
        rec_mm_total = float(agg["suma_mm"].sum())
        metodo_usado = "balance_diario"
    else:
        dias = _dias_por_periodo(df, len(precip))
        if metodo == "balance" and float(np.sum(pet)) > 0:
            rec_mm = balance_suelo(precip, pet, cc_mm=cc_mm, coef_escorrentia=coef_escorrentia)
            metodo_usado = "balance"
        else:
            rec_mm = [coef_infiltracion * float(p) for p in precip]
            metodo_usado = "coeficiente"
        n = len(precip)
        rec_m_d = np.array([r / 1000.0 / d for r, d in zip(rec_mm, dias)])
        rec_mm_total = float(np.sum(rec_mm))

    tabla = pd.DataFrame({
        "stress_period": list(range(n)),
        "recharge_m_d": [round(float(x), 8) for x in rec_m_d],
    })
    out = tablas_dir / "recarga_periodos.csv"
    tabla.to_csv(out, index=False)

    sp_out = None
    if transiente and n > 1:
        # 1.er periodo permanente (condicion inicial) + resto transiente
        sp = pd.DataFrame({
            "stress_period": list(range(n)),
            "perlen_d": [round(float(d), 2) for d in dias],
            "nstp": [1] * n,
            "tsmult": [1.0] * n,
            "steady_state": [1] + [0] * (n - 1),
        })
        sp_out = tablas_dir / "stress_periods.csv"
        sp.to_csv(sp_out, index=False)
        logger.info("Régimen transiente: %d periodos en stress_periods.csv (1 permanente + %d transientes).",
                    n, n - 1)

    logger.info("Recarga (%s): %d periodos, recarga total ~%.0f mm; recarga_periodos.csv escrito.",
                metodo_usado, n, rec_mm_total)
    return {"archivo": out, "metodo": metodo_usado, "recarga_total_mm": rec_mm_total,
            "tabla": tabla, "stress_periods": sp_out, "n_periodos": n}
