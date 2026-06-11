#!/usr/bin/env python3
"""Fuentes de clima chilenas -> clima.csv del workflow (CR2, CAMELS-CL).

Convierte exportes del Explorador Climatico CR2 (<https://explorador.cr2.cl>) y
series CAMELS-CL (<https://www.cr2.cl/camels-cl/>) al formato estandar del
workflow (`datos/fuente/clima.csv`):

    fecha, precip_mm [, temp_c, et0_mm]

que luego consumen `yaku recarga` (balance de suelo) e `yaku indices` (SPI/SPEI).
Los parsers son tolerantes al formato: detectan la fila de encabezado, separador,
columnas de fecha (fecha | agno/año+mes[+dia]) y la columna de valor.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger("yaku")

_COL_FECHA = {"fecha", "date", "dia_fecha", "time", "tiempo"}
_COL_ANIO = {"agno", "año", "ano", "year", "anio"}
_COL_MES = {"mes", "month"}
_COL_DIA = {"dia", "día", "day"}
_COL_VALOR = {"valor", "value", "pr", "precip", "prec", "pp", "precipitacion",
              "t2m", "tmed", "temp", "tas", "et0", "pet", "eto"}


def _norm(col: str) -> str:
    return str(col).strip().lower().replace('"', "")


def _detectar_encabezado(path: Path, max_lineas: int = 60) -> int:
    """Fila del encabezado: la primera cuyas columnas incluyen fecha o año+mes o valor."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for i, linea in enumerate(fh):
            if i >= max_lineas:
                break
            campos = {_norm(c) for sep in (",", ";", "\t") for c in linea.split(sep)}
            if campos & _COL_FECHA or (campos & _COL_ANIO and campos & _COL_MES) or campos & _COL_VALOR:
                return i
    return 0


def _leer_tabla(path: Path) -> pd.DataFrame:
    """Lee CSV/TXT con separador auto y encabezado detectado (salta metadatos CR2)."""
    path = Path(path)
    fila = _detectar_encabezado(path)
    return pd.read_csv(path, sep=None, engine="python", skiprows=fila)


def _serie_fecha_valor(df: pd.DataFrame, *, columna_valor: str | None = None) -> pd.DataFrame:
    """Normaliza un DataFrame a (fecha, valor)."""
    cols = {_norm(c): c for c in df.columns}

    # --- fecha ---
    fecha = None
    for k in _COL_FECHA:
        if k in cols:
            fecha = pd.to_datetime(df[cols[k]], errors="coerce")
            break
    if fecha is None:
        anio = next((cols[k] for k in _COL_ANIO if k in cols), None)
        mes = next((cols[k] for k in _COL_MES if k in cols), None)
        if anio is None or mes is None:
            raise ValueError("No se encontro columna de fecha ni año+mes en el archivo.")
        dia_col = next((cols[k] for k in _COL_DIA if k in cols), None)
        dia = df[dia_col].astype(int) if dia_col is not None else 1
        fecha = pd.to_datetime(dict(
            year=df[anio].astype(int), month=df[mes].astype(int), day=dia), errors="coerce")

    # --- valor ---
    if columna_valor is not None:
        if columna_valor not in df.columns:
            raise ValueError(f"Columna '{columna_valor}' no existe; columnas: {list(df.columns)}")
        valor = pd.to_numeric(df[columna_valor], errors="coerce")
    else:
        valor_col = next((cols[k] for k in _COL_VALOR if k in cols), None)
        if valor_col is None:
            usadas = {cols.get(k) for k in (_COL_FECHA | _COL_ANIO | _COL_MES | _COL_DIA) if k in cols}
            numericas = [c for c in df.columns if c not in usadas
                         and pd.to_numeric(df[c], errors="coerce").notna().mean() > 0.5]
            if not numericas:
                raise ValueError("No se encontro columna de valor numerico.")
            valor_col = numericas[0]
        valor = pd.to_numeric(df[valor_col], errors="coerce")

    out = pd.DataFrame({"fecha": fecha, "valor": valor}).dropna(subset=["fecha"])
    # CR2 usa -9999 / -999 como nodata
    out.loc[out["valor"] <= -990, "valor"] = pd.NA
    return out.sort_values("fecha").reset_index(drop=True)


def leer_cr2(path: Path, *, columna_valor: str | None = None) -> pd.DataFrame:
    """Serie (fecha, valor) desde un exporte del Explorador Climatico CR2.

    Acepta series diarias o mensuales, con columna `fecha` o columnas año/mes[/dia],
    y lineas de metadatos antes del encabezado.
    """
    return _serie_fecha_valor(_leer_tabla(path), columna_valor=columna_valor)


def leer_camels(path: Path, estacion: str) -> pd.DataFrame:
    """Serie (fecha, valor) de una cuenca CAMELS-CL (gauge_id = `estacion`).

    Los .txt de CAMELS-CL traen una columna de fecha (o gauge_id en el encabezado y
    fechas por fila) y una columna por cuenca, nombrada por su gauge_id.
    """
    df = _leer_tabla(Path(path))
    estacion = str(estacion).strip()
    col_est = next((c for c in df.columns if str(c).strip() == estacion), None)
    if col_est is None:
        disponibles = [str(c) for c in df.columns[:12]]
        raise ValueError(f"gauge_id '{estacion}' no esta en el archivo; primeras columnas: {disponibles}")
    return _serie_fecha_valor(df, columna_valor=col_est)


def construir_clima(precip: pd.DataFrame, *, temp: pd.DataFrame | None = None,
                    et0: pd.DataFrame | None = None, out_path: Path) -> Path:
    """Une series (fecha, valor) en el clima.csv estandar del workflow."""
    clima = precip.rename(columns={"valor": "precip_mm"}).dropna(subset=["precip_mm"])
    if clima.empty:
        raise ValueError("La serie de precipitacion quedo vacia tras limpiar nodata.")
    for df, nombre in ((temp, "temp_c"), (et0, "et0_mm")):
        if df is not None:
            clima = clima.merge(df.rename(columns={"valor": nombre}), on="fecha", how="left")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    clima["fecha"] = pd.to_datetime(clima["fecha"]).dt.strftime("%Y-%m-%d")
    clima.to_csv(out_path, index=False)
    logger.info("clima.csv escrito: %d periodos (%s a %s), columnas %s.",
                len(clima), clima['fecha'].iloc[0], clima['fecha'].iloc[-1], ", ".join(clima.columns))
    return out_path


def clima_desde_fuente(out_path: Path, *, fuente: str, precip: Path,
                       temp: Path | None = None, et0: Path | None = None,
                       estacion: str | None = None) -> Path:
    """Pipeline: archivos CR2/CAMELS-CL -> clima.csv. `estacion` es el gauge_id (camels)."""
    fuente = fuente.strip().lower()
    if fuente == "cr2":
        leer = lambda p: leer_cr2(p)  # noqa: E731
    elif fuente in ("camels", "camels-cl", "camelscl"):
        if not estacion:
            raise ValueError("Para CAMELS-CL se requiere --estacion (gauge_id de la cuenca).")
        leer = lambda p: leer_camels(p, estacion)  # noqa: E731
    else:
        raise ValueError(f"Fuente no soportada: '{fuente}' (use cr2 | camels).")

    return construir_clima(
        leer(precip),
        temp=leer(temp) if temp else None,
        et0=leer(et0) if et0 else None,
        out_path=out_path,
    )
