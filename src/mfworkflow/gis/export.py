#!/usr/bin/env python3
"""Exporta resultados del modelo a raster GeoTIFF, para abrir en QGIS/ArcGIS.

Convierte las cargas y la profundidad de napa de la capa superior en rasters
georreferenciados (origen y CRS tomados del dominio del proyecto). Útil como
entregable GIS además del informe.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger("mfworkflow")

_INACTIVO = 1e29


def exportar_rasters(cfg, out_dir: Path | None = None) -> dict:
    """Escribe GeoTIFFs (carga capa 1 y profundidad de napa). Devuelve {nombre: ruta}."""
    import flopy
    import geopandas as gpd
    import rasterio
    from rasterio.transform import from_origin

    from mfworkflow.gis.preprocess import find_vector

    res_dir = cfg.resultados_dir
    model = cfg.model_name
    hds = res_dir / f"{model}.hds"
    if not hds.exists():
        logger.error("export-gis: no existe %s (corre 'mfw run' primero).", hds.name)
        return {}

    pm = cfg.datos_dir / "parametros_modelo.csv"
    if not pm.exists():
        logger.error("export-gis: falta parametros_modelo.csv.")
        return {}
    params = {str(r.clave): r.valor for r in pd.read_csv(pm).itertuples(index=False)}
    nrow, ncol = int(params["nrow"]), int(params["ncol"])
    delr, delc = float(params["delr"]), float(params["delc"])

    dom = find_vector(cfg.gis_dir, "dominio") or find_vector(cfg.project_dir / "datos" / "fuente", "dominio")
    if dom is None:
        logger.error("export-gis: falta dominio.shp para georreferenciar el raster.")
        return {}
    gdf = gpd.read_file(dom)
    minx, _miny, _maxx, maxy = gdf.total_bounds
    crs = gdf.crs
    transform = from_origin(minx, maxy, delr, delc)  # raster: fila 0 = norte (maxy)

    head = flopy.utils.HeadFile(str(hds), precision="double")
    h = head.get_data(totim=head.get_times()[-1]) if head.get_times() else head.get_data()
    capa0 = np.asarray(h[0], dtype="float32")
    capa0 = np.where(np.abs(capa0) >= _INACTIVO, np.nan, capa0)

    # top (para profundidad de napa): top_dem_grid.csv o el escalar de parametros
    top_grid = cfg.datos_dir / "top_dem_grid.csv"
    if top_grid.exists():
        top = pd.read_csv(top_grid, header=None).to_numpy(dtype="float32")
    else:
        top = np.full(capa0.shape, float(params.get("top", np.nanmax(capa0))), dtype="float32")
    napa = top - capa0

    out_dir = Path(out_dir) if out_dir else (res_dir / "gis_export")
    out_dir.mkdir(parents=True, exist_ok=True)

    def _write(nombre: str, arr2d) -> Path:
        # la grilla del modelo tiene fila 0 = sur; el raster espera fila 0 = norte.
        arr = np.flipud(np.asarray(arr2d, dtype="float32"))
        p = out_dir / nombre
        with rasterio.open(p, "w", driver="GTiff", height=nrow, width=ncol, count=1,
                           dtype="float32", crs=crs, transform=transform, nodata=float("nan")) as dst:
            dst.write(arr, 1)
        return p

    out = {
        "carga": _write(f"{model}_carga.tif", capa0),
        "profundidad_napa": _write(f"{model}_profundidad_napa.tif", napa),
    }
    logger.info("Rasters GIS escritos en %s: %s", out_dir, ", ".join(p.name for p in out.values()))
    return out
