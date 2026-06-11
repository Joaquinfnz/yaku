#!/usr/bin/env python3
"""Caudal base simulado (intercambio rio-acuifero) como objetivo de calibracion.

Permite calibrar contra AFOROS ademas de niveles (multi-objetivo, GMDSI):
`datos/tablas/aforos.csv` define el caudal base observado y el forward model de
PEST escribe el simulado leyendo el budget (SFR si existe; si no, RIV):

    aforos.csv:  nombre, caudal_m3_d [, peso] [, grupo]

`caudal_m3_d` es el flujo acuifero->rio (caudal base, positivo). Si no se entrega
`peso`, se asume un error del 10 % del valor observado (peso = 1 / (0.1*|q|)),
para que niveles (m) y caudales (m3/d) pesen de forma comparable en la funcion
objetivo.
"""

from __future__ import annotations

import logging
from pathlib import Path

import flopy
import numpy as np
import pandas as pd

logger = logging.getLogger("yaku")


def caudal_base_simulado(cbc_path: Path) -> dict | None:
    """Intercambio rio-acuifero (m3/d) del ultimo paso de tiempo, desde el .cbc.

    Devuelve {componente, rio_a_acuifero_m3d, acuifero_a_rio_m3d, neto_m3d} o None
    si el modelo no tiene SFR ni RIV.
    """
    cbc_path = Path(cbc_path)
    if not cbc_path.exists():
        return None
    try:
        cbc = flopy.utils.CellBudgetFile(str(cbc_path))
        nombres = [str(n).strip().upper() for n in cbc.get_unique_record_names(decode=True)]
        texto = next((t for t in ("SFR", "RIV") if t in nombres), None)
        if texto is None:
            return None
        datos = cbc.get_data(text=texto, kstpkper=cbc.get_kstpkper()[-1])
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo leer el caudal base del .cbc: %s", exc)
        return None
    if not datos:
        return None
    rec = datos[-1]
    q = np.asarray(rec["q"], dtype=float)  # q > 0: el rio recarga al acuifero
    return {
        "componente": texto,
        "rio_a_acuifero_m3d": float(q[q > 0].sum()),
        "acuifero_a_rio_m3d": float(-q[q < 0].sum()),
        "neto_m3d": float(q.sum()),
    }


def escribir_simulados_caudal(cbc_path: Path, aforos: pd.DataFrame, out_path: Path) -> Path:
    """Escribe el caudal base simulado para cada aforo (formato leido por el .ins)."""
    sim = caudal_base_simulado(cbc_path)
    caudal = float(sim["acuifero_a_rio_m3d"]) if sim else 0.0
    filas = [{"nombre": str(r["nombre"]).lower(), "simulado_m3d": caudal}
             for _, r in aforos.iterrows()]
    out_path = Path(out_path)
    pd.DataFrame(filas).to_csv(out_path, index=False, sep=" ")
    return out_path


def peso_aforo(row: pd.Series) -> float:
    """Peso PEST del aforo: el entregado, o 1/(10 % del caudal observado)."""
    if "peso" in row and pd.notna(row.get("peso")):
        return float(row["peso"])
    q = abs(float(row["caudal_m3_d"]))
    return 1.0 / max(0.1 * q, 1e-6)
