#!/usr/bin/env python3
"""Balance por ZONAS (estilo ZoneBudget) desde el .cbc, sin binarios extra.

El SEA pide el balance por sectores del acuifero (unidades, subcuencas, areas de
interes). Aqui cada zona es un entero >= 1 en una grilla nrow x ncol:

    datos/tablas/zonas_balance.csv   (sin encabezado; 0 = fuera de toda zona)

Si no existe, se derivan zonas desde recarga_zonas.csv (cada coeficiente de
infiltracion distinto = una unidad geologica = una zona).

Se suman, por zona, los terminos de celda del .cbc (recarga, pozos, rio, dren,
GHB, ET, almacenamiento, CHD...). No incluye el intercambio lateral ENTRE zonas
(FLOW-JA-FACE); para eso esta ZoneBudget 6 (zbud6). Para el balance de fuentes y
sumideros por sector —lo que pide el informe— esto es suficiente y trazable.
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

_SKIP_RECORDS = {"FLOW-JA-FACE", "FLOW JA FACE", "DATA-SPDIS", "DATA-SAT"}


def cargar_zonas(datos_dir: Path, nrow: int, ncol: int) -> "np.ndarray | None":
    """Matriz de zonas (enteros) desde zonas_balance.csv o derivada de recarga_zonas.csv."""
    datos_dir = Path(datos_dir)
    explicito = datos_dir / "zonas_balance.csv"
    if explicito.exists():
        try:
            z = pd.read_csv(explicito, header=None).to_numpy(dtype=float)
        except Exception as exc:  # noqa: BLE001
            logger.warning("zonas_balance.csv ilegible: %s", exc)
            return None
        if z.shape != (nrow, ncol):
            logger.warning("zonas_balance.csv tiene forma %s y la grilla es (%d, %d); ignorado.",
                           z.shape, nrow, ncol)
            return None
        return np.nan_to_num(z, nan=0.0).astype(int)

    # Derivar desde recarga_zonas.csv: cada coef. de infiltracion = una unidad/zona
    recarga = datos_dir / "recarga_zonas.csv"
    if recarga.exists():
        try:
            coef = pd.read_csv(recarga, header=None).to_numpy(dtype=float)
        except Exception:  # noqa: BLE001
            return None
        if coef.shape != (nrow, ncol):
            return None
        zonas = np.zeros((nrow, ncol), dtype=int)
        valores = sorted({float(v) for v in coef[np.isfinite(coef)]})
        for i, v in enumerate(valores, start=1):
            zonas[np.isclose(coef, v)] = i
        if len(valores) > 1:
            logger.info("Zonas de balance derivadas de recarga_zonas.csv: %d unidades.", len(valores))
            return zonas
    return None


def balance_por_zonas(cbc_path: Path, zonas: np.ndarray) -> "pd.DataFrame | None":
    """Entradas/salidas (m3/d) por zona y componente, ultimo paso de tiempo del .cbc."""
    cbc_path = Path(cbc_path)
    if not cbc_path.exists():
        return None
    try:
        cbc = flopy.utils.CellBudgetFile(str(cbc_path))
        kstpkper = cbc.get_kstpkper()[-1]
        nombres = cbc.get_unique_record_names(decode=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo leer el .cbc para el balance por zonas: %s", exc)
        return None

    zonas = np.asarray(zonas, dtype=int)
    ids = sorted(int(z) for z in np.unique(zonas) if z > 0)
    if not ids:
        return None

    filas: list[dict] = []
    for nombre in nombres:
        texto = str(nombre).strip()
        if texto.upper() in _SKIP_RECORDS:
            continue
        try:
            datos = cbc.get_data(text=texto, kstpkper=kstpkper, full3D=True)
        except Exception:  # noqa: BLE001
            continue
        if not datos:
            continue
        arr = np.ma.filled(np.ma.masked_invalid(np.ma.asarray(datos[-1], dtype=float)), 0.0)
        if arr.ndim == 2:
            arr = arr[np.newaxis, :, :]
        if arr.ndim != 3 or arr.shape[1:] != zonas.shape:
            continue
        for zid in ids:
            mask = np.broadcast_to(zonas == zid, arr.shape)
            vals = arr[mask]
            ent = float(vals[vals > 0].sum())
            sal = float(-vals[vals < 0].sum())
            if ent == 0.0 and sal == 0.0:
                continue
            filas.append({"zona": zid, "componente": texto,
                          "entrada_m3d": ent, "salida_m3d": sal, "neto_m3d": ent - sal})

    if not filas:
        return None
    df = pd.DataFrame(filas)
    totales = df.groupby("zona", as_index=False)[["entrada_m3d", "salida_m3d", "neto_m3d"]].sum()
    totales["componente"] = "TOTAL"
    df = pd.concat([df, totales], ignore_index=True).sort_values(
        ["zona", "componente"], key=lambda s: s.map(lambda v: "zzz" if v == "TOTAL" else str(v))
    ).reset_index(drop=True)
    return df


def figura_balance_zonas(df: pd.DataFrame, out_dir: Path, model_name: str) -> "Path | None":
    """Barras de entradas/salidas por zona (componentes apilados)."""
    datos = df[df["componente"] != "TOTAL"]
    if datos.empty:
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    zonas = sorted(datos["zona"].unique())
    componentes = sorted(datos["componente"].unique())
    cmap = plt.get_cmap("tab10")

    fig, ax = plt.subplots(figsize=(7.5, 4))
    x = np.arange(len(zonas), dtype=float)
    base_in = np.zeros(len(zonas))
    base_out = np.zeros(len(zonas))
    for i, comp in enumerate(componentes):
        sub = datos[datos["componente"] == comp].set_index("zona")
        ent = np.array([float(sub["entrada_m3d"].get(z, 0.0)) for z in zonas])
        sal = np.array([float(sub["salida_m3d"].get(z, 0.0)) for z in zonas])
        ax.bar(x - 0.18, ent, width=0.32, bottom=base_in, color=cmap(i % 10), label=comp)
        ax.bar(x + 0.18, -sal, width=0.32, bottom=-base_out, color=cmap(i % 10), alpha=0.75)
        base_in += ent
        base_out += sal
    ax.axhline(0, color="0.3", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"Zona {z}" for z in zonas])
    ax.set_ylabel("entradas (+) / salidas (−)  m³/d")
    ax.set_title("Balance por zonas (último periodo)")
    ax.legend(fontsize=7, ncols=2)
    fig.tight_layout()
    png = out_dir / f"{model_name}_balance_zonas.png"
    fig.savefig(png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return png


def balance_zonas_proyecto(cfg, figuras_dir: Path) -> "dict | None":
    """Pipeline completo para un proyecto: zonas -> balance -> csv + figura."""
    pm = cfg.datos_dir / "parametros_modelo.csv"
    if not pm.exists():
        return None
    params = {str(r.clave): r.valor for r in pd.read_csv(pm).itertuples(index=False)}
    if "nrow" not in params or "ncol" not in params:
        return None
    zonas = cargar_zonas(cfg.datos_dir, int(float(params["nrow"])), int(float(params["ncol"])))
    if zonas is None:
        return None
    df = balance_por_zonas(cfg.resultados_dir / f"{cfg.model_name}.cbc", zonas)
    if df is None:
        return None
    figuras_dir = Path(figuras_dir)
    csv = figuras_dir / "balance_por_zonas.csv"
    df.to_csv(csv, index=False)
    png = figura_balance_zonas(df, figuras_dir, cfg.model_name)
    n_zonas = df["zona"].nunique()
    logger.info("Balance por zonas: %d zonas, %d componentes (balance_por_zonas.csv).",
                n_zonas, df[df["componente"] != "TOTAL"]["componente"].nunique())
    return {"df": df, "csv": csv, "figura": png, "n_zonas": n_zonas}
