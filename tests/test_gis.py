"""Tests de GIS: aviso de CRS inconsistente."""

import logging

import pytest


def test_avisar_crs_distintos(caplog):
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Point

    from mfworkflow.gis.preprocess import avisar_crs

    a = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs="EPSG:32719")   # UTM 19S (m)
    b = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs="EPSG:4326")    # lat/lon
    with caplog.at_level(logging.WARNING, logger="mfworkflow"):
        avisar_crs({"dominio": a, "pozos": b})
    msgs = " ".join(r.message for r in caplog.records)
    assert "CRS" in msgs           # avisa que difieren
    assert "geografico" in msgs    # avisa que una es lat/lon


def test_export_rasters(tmp_path):
    import shutil

    pytest.importorskip("rasterio")
    from mfworkflow.config import resolve_project_config
    from mfworkflow.gis.export import exportar_rasters

    dest = tmp_path / "caso_demo"
    shutil.copytree("examples/caso_demo", dest)
    out = exportar_rasters(resolve_project_config(dest))
    assert "carga" in out and out["carga"].exists()
    assert "profundidad_napa" in out and out["profundidad_napa"].exists()
    import rasterio
    with rasterio.open(out["carga"]) as r:
        assert r.width > 0 and r.height > 0 and r.count == 1


def test_avisar_crs_coherente_no_avisa(caplog):
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Point

    from mfworkflow.gis.preprocess import avisar_crs

    a = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs="EPSG:32719")
    b = gpd.GeoDataFrame(geometry=[Point(1, 1)], crs="EPSG:32719")
    with caplog.at_level(logging.WARNING, logger="mfworkflow"):
        avisar_crs({"dominio": a, "pozos": b})
    assert not [r for r in caplog.records if "CRS" in r.message]
