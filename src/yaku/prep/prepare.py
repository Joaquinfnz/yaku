#!/usr/bin/env python3
"""Preparacion de informacion: de datos crudos a tablas del modelo.

Ingresa los archivos que tipicamente tiene un consultor y los convierte en las
tablas que consume el motor:

  datos/fuente/                       (insumos crudos que tu entregas)
    dem.tif            DEM del lugar (raster)            -> top del modelo
    dominio.shp        borde del modelo (poligono)       -> grilla + dominio
    pozos.shp          pozos (puntos, attr: nombre)      -> ubicacion de pozos
    caudales.csv       bombeos (nombre, stress_period, rate_m3_dia) -> pozos.csv
    rio.shp            rio (linea, opcional)             -> rio.csv (esqueleto)
    observaciones.shp  niveles (puntos, opcional)        -> observaciones (esqueleto)

Produce datos/tablas/*.csv (parametros, pozos, ...) y copia las capas a datos/gis/.
Es un primer borrador editable: el consultor ajusta capas, K y bordes despues.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

logger = logging.getLogger("yaku")


def _cell_centers(minx, miny, nrow, ncol, cellsize):
    xs = minx + (np.arange(ncol) + 0.5) * cellsize
    ys = miny + (np.arange(nrow) + 0.5) * cellsize
    return xs, ys


def _sample_dem(dem_path: Path, xs, ys):
    """Devuelve una matriz nrow x ncol con la elevacion del DEM en cada centro."""
    import rasterio

    with rasterio.open(dem_path) as src:
        nodata = src.nodata
        grid = np.full((len(ys), len(xs)), np.nan)
        for j, y in enumerate(ys):
            coords = [(float(x), float(y)) for x in xs]
            vals = [v[0] for v in src.sample(coords)]
            row = np.array(vals, dtype=float)
            if nodata is not None:
                row[row == nodata] = np.nan
            grid[j, :] = row
    return grid


def _sample_coef_inf(geologia_path: Path, xs, ys) -> "np.ndarray | None":
    """Matriz nrow x ncol con el coef. de infiltracion de la unidad geologica en cada centro.

    Rasteriza geologia.shp (campo coef_inf) a la grilla para distribuir la recarga por zona.
    Devuelve None si no hay un campo de coeficiente de infiltracion.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    g = gpd.read_file(geologia_path)
    campo = next((c for c in g.columns if c.lower().replace(" ", "_") in
                  ("coef_inf", "coef_infiltracion", "coeficiente_infiltracion", "coefinf")), None)
    if campo is None:
        return None
    puntos = [{"row": j, "col": i, "geometry": Point(float(x), float(y))}
              for j, y in enumerate(ys) for i, x in enumerate(xs)]
    gp = gpd.GeoDataFrame(puntos, crs=g.crs)
    unido = gpd.sjoin(gp, g[[campo, "geometry"]], how="left", predicate="within")
    unido = unido.drop_duplicates(subset=["row", "col"], keep="first")
    grid = np.full((len(ys), len(xs)), np.nan)
    for _, r in unido.iterrows():
        if pd.notna(r[campo]):
            grid[int(r["row"]), int(r["col"])] = float(r[campo])
    return grid if np.isfinite(grid).any() else None


def _point_cell(x, y, minx, miny, cellsize, nrow, ncol):
    col = int((x - minx) // cellsize)
    row = int((y - miny) // cellsize)
    return min(max(row, 0), nrow - 1), min(max(col, 0), ncol - 1)


def _leer_perfil_litologico(source_dir: Path, nlay: int) -> list[dict] | None:
    """Lee datos/fuente/perfil_litologico.csv (propiedades hidrogeologicas por capa).

    Columnas esperadas: layer, kx_m_d, kz_m_d, sy, ss, iconvert y, opcional, unidad.
    Permite definir un contraste acuifero/acuitardo (Guia SEA 2012, 3.3.3 y Tabla 11:
    "demostrar la equivalencia de las capas con las unidades hidrogeologicas"). Devuelve
    una lista de nlay dicts ordenada por capa, o None si no hay archivo o no calza con nlay.
    """
    p = source_dir / "perfil_litologico.csv"
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo leer perfil_litologico.csv (%s); uso K uniforme.", exc)
        return None
    faltan = {"layer", "kx_m_d", "kz_m_d", "sy", "ss", "iconvert"} - set(df.columns)
    if faltan:
        logger.warning("perfil_litologico.csv: faltan columnas %s; uso K uniforme.",
                       ", ".join(sorted(faltan)))
        return None
    df = df.sort_values("layer").reset_index(drop=True)
    if len(df) != nlay:
        logger.warning("perfil_litologico.csv tiene %d capas pero nlay=%d; uso K uniforme.",
                       len(df), nlay)
        return None
    return df.to_dict("records")


def prepare_from_sources(
    source_dir: Path,
    tablas_dir: Path,
    gis_dir: Path,
    *,
    cellsize: float = 100.0,
    nlay: int = 1,
    espesor: float = 50.0,
    k: float = 5.0,
    recharge: float = 0.0005,
) -> dict[str, object]:
    """Construye un borrador de tablas del modelo desde datos/fuente/."""
    source_dir = Path(source_dir)
    tablas_dir = Path(tablas_dir)
    gis_dir = Path(gis_dir)
    tablas_dir.mkdir(parents=True, exist_ok=True)
    gis_dir.mkdir(parents=True, exist_ok=True)

    def _find(name: str) -> Path | None:
        for ext in (".shp", ".gpkg", ".geojson"):
            p = source_dir / f"{name}{ext}"
            if p.exists():
                return p
        return None

    resumen: dict[str, object] = {}

    # --- 1. Dominio -> grilla ---
    dom_path = _find("dominio")
    if dom_path is None:
        raise FileNotFoundError(f"Falta el borde del modelo (dominio.shp) en {source_dir}")
    domain = gpd.read_file(dom_path)
    minx, miny, maxx, maxy = domain.total_bounds
    ncol = max(1, int(np.ceil((maxx - minx) / cellsize)))
    nrow = max(1, int(np.ceil((maxy - miny) / cellsize)))
    resumen["grilla"] = {"nrow": nrow, "ncol": ncol, "cellsize": cellsize}
    logger.info("Grilla derivada del dominio: %d filas x %d columnas (celda %.1f)", nrow, ncol, cellsize)

    xs, ys = _cell_centers(minx, miny, nrow, ncol, cellsize)

    # --- 2. DEM -> top ---
    dem_path = source_dir / "dem.tif"
    if dem_path.exists():
        dem_grid = _sample_dem(dem_path, xs, ys)
        top_val = float(np.nanmean(dem_grid))
        pd.DataFrame(dem_grid).to_csv(tablas_dir / "top_dem_grid.csv", index=False, header=False)
        logger.info("DEM muestreado a la grilla; top medio = %.1f m (top_dem_grid.csv para top variable)", top_val)
    else:
        top_val = float(espesor)
        logger.warning("No hay dem.tif; uso top=%.1f. Entrega un DEM para mejor geometria.", top_val)
    botm_val = top_val - espesor

    # --- 2b. Recarga zonal: coef. de infiltracion de geologia.shp -> grilla ---
    geologia_path = source_dir / "geologia.shp"
    if geologia_path.exists():
        try:
            coef_grid = _sample_coef_inf(geologia_path, xs, ys)
            if coef_grid is not None:
                pd.DataFrame(coef_grid).to_csv(tablas_dir / "recarga_zonas.csv", index=False, header=False)
                logger.info("Recarga zonal: coef. de infiltracion rasterizado a la grilla "
                            "(recarga_zonas.csv); el modelo reparte la recarga por unidad geologica.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo generar recarga_zonas.csv desde geologia.shp: %s", exc)

    # --- 3. parametros_modelo.csv ---
    params = {
        "nlay": nlay, "nrow": nrow, "ncol": ncol,
        "delr": cellsize, "delc": cellsize,
        "top": round(top_val, 2), "botm": round(botm_val, 2),
        "starting_head": round(top_val - 1.0, 2),
        "k": k, "recharge": recharge,
    }
    pd.DataFrame({"clave": list(params), "valor": list(params.values())}).to_csv(
        tablas_dir / "parametros_modelo.csv", index=False)
    resumen["parametros"] = params

    # capas_modelo.csv coherente con nlay (reemplaza el de ejemplo de la plantilla).
    # Si el usuario entrega datos/fuente/perfil_litologico.csv, se usan sus K/Sy/Ss/iconvert
    # por capa (contraste acuifero/acuitardo, como exige la Guia SEA 2012); si no, K uniforme.
    perfil = _leer_perfil_litologico(source_dir, nlay)
    bordes = np.linspace(top_val, botm_val, nlay + 1)
    capas = []
    for i in range(nlay):
        prop = perfil[i] if perfil is not None else None
        capas.append({
            "layer": i + 1,
            "top_m": round(float(bordes[i]), 2),
            "botm_m": round(float(bordes[i + 1]), 2),
            "kx_m_d": float(prop["kx_m_d"]) if prop else k,
            "kz_m_d": float(prop["kz_m_d"]) if prop else round(k / 10.0, 4),
            "sy": float(prop["sy"]) if prop else 0.1,
            "ss": float(prop["ss"]) if prop else 1e-5,
            "iconvert": int(prop["iconvert"]) if prop else (1 if i == 0 else 0),
            **({"unidad": prop["unidad"]} if prop and prop.get("unidad") else {}),
        })
    pd.DataFrame(capas).to_csv(tablas_dir / "capas_modelo.csv", index=False)
    if perfil is not None:
        resumen["perfil_litologico"] = [c.get("unidad", f"capa {c['layer']}") for c in capas]
        logger.info("Perfil litologico aplicado: %d unidades con contraste de K/Sy/Ss.", nlay)

    # --- 3b. Geometria no plana: base_capa{N}.tif -> botm_grid_capa{N}.csv ---
    # Rasters con la cota de BASE de cada unidad hidrogeologica (mismo CRS del DEM).
    # El motor los usa como superficie de base de la capa (en vez de una cota plana).
    superficies: list[int] = []
    for i in range(1, nlay + 1):
        raster = source_dir / f"base_capa{i}.tif"
        if not raster.exists():
            continue
        try:
            grid_base = _sample_dem(raster, xs, ys)
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo remuestrear base_capa%d.tif: %s", i, exc)
            continue
        pd.DataFrame(grid_base).to_csv(tablas_dir / f"botm_grid_capa{i}.csv", index=False, header=False)
        superficies.append(i)
    if superficies:
        resumen["superficies_capas"] = superficies
        logger.info("Geometria no plana: superficie de base remuestreada para capa(s) %s "
                    "(botm_grid_capa{N}.csv).", ", ".join(map(str, superficies)))

    # --- 4. Pozos: shp + caudales.csv -> pozos.csv ---
    pozos_path = _find("pozos")
    if pozos_path is not None:
        pozos = gpd.read_file(pozos_path)
        filas = []
        for _, w in pozos.iterrows():
            geom = w.geometry
            row, col = _point_cell(geom.x, geom.y, minx, miny, cellsize, nrow, ncol)
            filas.append({"nombre": w.get("nombre", w.get("name", f"Pozo_{len(filas)+1}")),
                          "layer": int(w.get("layer", 1)), "row": row, "col": col})
        pozos_grid = pd.DataFrame(filas)
        caudales = source_dir / "caudales.csv"
        if caudales.exists():
            cau = pd.read_csv(caudales)
            pozos_out = pozos_grid.merge(cau, on="nombre", how="left")
            if "stress_period" not in pozos_out:
                pozos_out["stress_period"] = "all"
            if "rate_m3_dia" not in pozos_out:
                pozos_out["rate_m3_dia"] = -100.0
        else:
            pozos_out = pozos_grid.assign(stress_period="all", rate_m3_dia=-100.0)
            logger.warning("No hay caudales.csv; rate por defecto -100. Edita pozos.csv.")
        pozos_out.to_csv(tablas_dir / "pozos.csv", index=False)
        resumen["n_pozos"] = len(pozos_out)

    # --- 5. Esqueletos de bordes y stress periods (el consultor completa) ---
    if not (tablas_dir / "contornos_carga.csv").exists():
        pd.DataFrame([
            {"lado": "izquierdo", "carga_m": round(top_val - 1, 2), "layer": 1, "stress_period": "all"},
            {"lado": "derecho", "carga_m": round(botm_val + 5, 2), "layer": 1, "stress_period": "all"},
        ]).to_csv(tablas_dir / "contornos_carga.csv", index=False)
    if not (tablas_dir / "stress_periods.csv").exists():
        pd.DataFrame([{"stress_period": 0, "perlen_d": 1.0, "nstp": 1, "tsmult": 1.0, "steady_state": 1}]
                     ).to_csv(tablas_dir / "stress_periods.csv", index=False)
    # recarga por periodo (vehiculo para calibrar/variar la recarga; arranca con la base)
    if not (tablas_dir / "recarga_periodos.csv").exists():
        pd.DataFrame([{"stress_period": 0, "recharge_m_d": recharge}]
                     ).to_csv(tablas_dir / "recarga_periodos.csv", index=False)

    # --- 6. Copiar capas a datos/gis/ (para yaku gis / motor mfsetup) ---
    for name in ("dominio", "pozos", "rio"):
        p = _find(name)
        if p is not None and p.suffix == ".shp":
            for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
                f = p.with_suffix(ext)
                if f.exists():
                    shutil.copy(f, gis_dir / f.name)
        elif p is not None:
            shutil.copy(p, gis_dir / p.name)

    return resumen
