"""Test de preparacion de datos (DEM + shapefile + csv -> tablas)."""

import numpy as np
import pandas as pd
import pytest


@pytest.mark.slow
def test_prep_desde_fuentes(tmp_path):
    gpd = pytest.importorskip("geopandas")
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    from shapely.geometry import Point, Polygon

    from mfworkflow.prep import prepare_from_sources

    src = tmp_path / "fuente"
    src.mkdir()
    # dominio 0..1000 x 0..1000
    poly = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    gpd.GeoDataFrame({"id": [1]}, geometry=[poly], crs=None).to_file(src / "dominio.shp")
    # un pozo
    gpd.GeoDataFrame({"nombre": ["P1"]}, geometry=[Point(500, 500)], crs=None).to_file(src / "pozos.shp")
    pd.DataFrame([{"nombre": "P1", "stress_period": "all", "rate_m3_dia": -300.0}]).to_csv(src / "caudales.csv", index=False)
    # DEM plano = 100 m
    res = 50.0
    n = int(1000 / res)
    dem = np.full((n, n), 100.0, dtype="float32")
    with rasterio.open(src / "dem.tif", "w", driver="GTiff", height=n, width=n, count=1,
                       dtype="float32", transform=from_origin(0, 1000, res, res), crs=None) as dst:
        dst.write(dem, 1)

    tablas = tmp_path / "tablas"
    gis = tmp_path / "gis"
    resumen = prepare_from_sources(src, tablas, gis, cellsize=100.0, nlay=1, espesor=40.0)

    assert resumen["grilla"]["nrow"] == 10 and resumen["grilla"]["ncol"] == 10
    params = pd.read_csv(tablas / "parametros_modelo.csv").set_index("clave")["valor"]
    assert abs(params["top"] - 100.0) < 1.0          # top desde DEM
    assert (tablas / "capas_modelo.csv").exists()
    assert (tablas / "pozos.csv").exists()
    assert (gis / "dominio.shp").exists()             # capa copiada a gis/


@pytest.mark.slow
def test_prep_con_perfil_litologico(tmp_path):
    """Si hay perfil_litologico.csv, capas_modelo.csv hereda K/Sy/Ss por capa (contraste)."""
    gpd = pytest.importorskip("geopandas")
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    from shapely.geometry import Polygon

    from mfworkflow.prep import prepare_from_sources

    src = tmp_path / "fuente"
    src.mkdir()
    poly = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    gpd.GeoDataFrame({"id": [1]}, geometry=[poly], crs=None).to_file(src / "dominio.shp")
    res = 50.0
    n = int(1000 / res)
    dem = np.full((n, n), 100.0, dtype="float32")
    with rasterio.open(src / "dem.tif", "w", driver="GTiff", height=n, width=n, count=1,
                       dtype="float32", transform=from_origin(0, 1000, res, res), crs=None) as dst:
        dst.write(dem, 1)
    # perfil con contraste acuifero/acuitardo
    pd.DataFrame([
        {"layer": 1, "unidad": "acuifero", "kx_m_d": 9.0, "kz_m_d": 0.9, "sy": 0.15, "ss": 1e-5, "iconvert": 1},
        {"layer": 2, "unidad": "acuitardo", "kx_m_d": 0.1, "kz_m_d": 0.005, "sy": 0.02, "ss": 5e-4, "iconvert": 0},
    ]).to_csv(src / "perfil_litologico.csv", index=False)

    tablas = tmp_path / "tablas"
    resumen = prepare_from_sources(src, tablas, tmp_path / "gis", cellsize=100.0, nlay=2, espesor=40.0)

    capas = pd.read_csv(tablas / "capas_modelo.csv").sort_values("layer")
    assert list(capas["kx_m_d"]) == [9.0, 0.1]        # contraste aplicado
    assert capas.loc[capas["layer"] == 2, "ss"].iloc[0] == pytest.approx(5e-4)
    assert "perfil_litologico" in resumen             # se reporta el perfil
