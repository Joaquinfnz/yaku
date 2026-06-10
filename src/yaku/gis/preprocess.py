#!/usr/bin/env python3
"""Preproceso GIS: GeoJSON/shapefile -> tablas row/col para el motor simple.

Migrado desde 12_gis_preproceso/gis_a_grilla.py. Mapea dominio, pozos y rio a una
grilla regular definida en parametros_modelo.csv y exporta CSV compatibles con el
builder. Rutas parametrizables por proyecto.
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import matplotlib
import pandas as pd
from shapely.geometry import box

matplotlib.use("Agg")
import matplotlib.pyplot as plt

logger = logging.getLogger("yaku")


def avisar_crs(capas: dict) -> None:
    """Avisa si las capas GIS no comparten un CRS proyectado en metros."""
    presentes = {n: c.crs for n, c in capas.items() if getattr(c, "crs", None) is not None}
    distintos = {str(v) for v in presentes.values()}
    if len(distintos) > 1:
        logger.warning("Capas GIS con CRS distintos %s; reproyecta todas al mismo CRS proyectado (m).",
                       {n: str(v) for n, v in presentes.items()})
    for n, crs in presentes.items():
        if getattr(crs, "is_geographic", False):
            logger.warning("La capa '%s' esta en CRS geografico (lat/lon); usa un CRS proyectado en metros.", n)


# Formatos vectoriales aceptados, en orden de preferencia (shapefile primero).
VECTOR_EXTS = (".shp", ".gpkg", ".geojson", ".json")


def find_vector(gis_dir: Path, name: str) -> Path | None:
    """Busca una capa vectorial por nombre base, probando shp/gpkg/geojson."""
    gis_dir = Path(gis_dir)
    for ext in VECTOR_EXTS:
        candidate = gis_dir / f"{name}{ext}"
        if candidate.exists():
            return candidate
    return None


def read_vector(gis_dir: Path, name: str) -> gpd.GeoDataFrame:
    path = find_vector(gis_dir, name)
    if path is None:
        raise FileNotFoundError(
            f"No se encontro la capa '{name}' en {gis_dir} "
            f"(formatos: {', '.join(VECTOR_EXTS)})"
        )
    return gpd.read_file(path)


def build_grid(domain, nrow: int, ncol: int, delr: float, delc: float) -> gpd.GeoDataFrame:
    minx, miny, _, _ = domain.total_bounds
    records = []
    for row in range(nrow):
        for col in range(ncol):
            x0 = minx + col * delr
            y0 = miny + row * delc
            records.append({"row": row, "col": col, "geometry": box(x0, y0, x0 + delr, y0 + delc)})
    grid = gpd.GeoDataFrame(records, geometry="geometry", crs=domain.crs)
    union = domain.geometry.union_all()
    grid["activo"] = grid.geometry.centroid.within(union)
    return grid


def _point_to_cell(point, grid: gpd.GeoDataFrame) -> tuple[int, int]:
    # `intersects` (no `contains`) para que un punto sobre el borde compartido de dos
    # celdas no quede "fuera"; si cae en un borde, varias celdas coinciden y se toma la
    # primera en orden de grilla (desempate determinista).
    matches = grid[grid.geometry.intersects(point)]
    if matches.empty:
        raise ValueError(f"Punto fuera de la grilla: {point}")
    first = matches.iloc[0]
    return int(first["row"]), int(first["col"])


def wells_to_csv(wells: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> pd.DataFrame:
    rows = []
    for _, well in wells.iterrows():
        row, col = _point_to_cell(well.geometry, grid)
        rows.append(
            {
                "nombre": well.get("nombre", "pozo"),
                "layer": int(well.get("layer", 1)) if "layer" in wells.columns else 1,
                "row": row,
                "col": col,
                "stress_period": well.get("stress_period", "all") if "stress_period" in wells.columns else "all",
                "rate_m3_dia": float(well.get("rate_m3_dia", -100.0)),
            }
        )
    return pd.DataFrame(rows)


def river_to_csv(river: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> pd.DataFrame:
    river_union = river.geometry.union_all()
    cells = grid[grid.geometry.intersects(river_union)].copy().sort_values(["col", "row"])
    cols = ["layer", "row", "col", "stage_m", "cond_m2_d", "river_bottom_m", "stress_period"]
    if cells.empty:
        return pd.DataFrame(columns=cols)
    rows = []
    max_col = max(1, int(cells["col"].max()))
    for _, cell in cells.iterrows():
        col = int(cell["col"])
        stage = 56.0 - 1.5 * (col / max_col)
        rows.append(
            {
                "layer": 1,
                "row": int(cell["row"]),
                "col": col,
                "stage_m": round(stage, 3),
                "cond_m2_d": 120.0,
                "river_bottom_m": round(stage - 2.0, 3),
                "stress_period": "all",
            }
        )
    return pd.DataFrame(rows).drop_duplicates(subset=["layer", "row", "col"])


def _plot_grid(domain, wells, river, grid, output: Path) -> Path:
    fig, axis = plt.subplots(figsize=(7, 7))
    grid.boundary.plot(ax=axis, linewidth=0.25, color="lightgray")
    grid[grid["activo"]].boundary.plot(ax=axis, linewidth=0.45, color="gray")
    domain.boundary.plot(ax=axis, color="black", linewidth=1.5)
    river.plot(ax=axis, color="royalblue", linewidth=2.0)
    wells.plot(ax=axis, color="red", markersize=50)
    axis.set_title("Preproceso GIS a grilla MODFLOW")
    axis.set_xlabel("x")
    axis.set_ylabel("y")
    axis.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return output


def run(gis_dir: Path, data_dir: Path, output_dir: Path) -> dict[str, Path]:
    """Convierte GeoJSON a tablas row/col. Devuelve las rutas generadas."""
    gis_dir = Path(gis_dir)
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    params_frame = pd.read_csv(data_dir / "parametros_modelo.csv")
    params = {str(r["clave"]): float(r["valor"]) for _, r in params_frame.iterrows()}
    nrow, ncol = int(params["nrow"]), int(params["ncol"])
    delr, delc = float(params["delr"]), float(params["delc"])

    domain = read_vector(gis_dir, "dominio")
    wells = read_vector(gis_dir, "pozos")
    river = read_vector(gis_dir, "rio")
    # Avisa si los CRS no son coherentes antes de mapear (errores silenciosos de ubicacion).
    avisar_crs({"dominio": domain, "pozos": wells, "rio": river})
    # Los datos de ejemplo usan coordenadas locales en metros, no lat/lon.
    domain.crs = None
    wells.crs = None
    river.crs = None

    grid = build_grid(domain, nrow, ncol, delr, delc)
    out = {
        "grilla": output_dir / "grilla_activa.csv",
        "pozos": output_dir / "pozos_desde_gis.csv",
        "rio": output_dir / "rio_desde_gis.csv",
        "figura": output_dir / "grilla_gis.png",
    }
    grid[["row", "col", "activo"]].to_csv(out["grilla"], index=False)
    wells_to_csv(wells, grid).to_csv(out["pozos"], index=False)
    river_to_csv(river, grid).to_csv(out["rio"], index=False)
    _plot_grid(domain, wells, river, grid, out["figura"])
    return out
