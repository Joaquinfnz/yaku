"""Tests de geometria no plana: superficies de base por capa (botm_grid_capa{N}.csv)."""

import shutil

import numpy as np
import pandas as pd
import pytest

from yaku.builder import ModflowModelBuilder


def _builder_con_superficie(demo_data_dir, tmp_path, superficie: np.ndarray, capa: int = 1):
    datos = tmp_path / "datos"
    shutil.copytree(demo_data_dir, datos)
    pd.DataFrame(superficie).to_csv(datos / f"botm_grid_capa{capa}.csv", index=False, header=False)
    return ModflowModelBuilder(data_dir=datos, workspace=tmp_path / "modelo", model_name="geom_test")


def test_superficie_de_base_reemplaza_cota_plana(demo_data_dir, tmp_path):
    # caso_demo: 2 capas, top=60, bases planas 35 y 0; grilla 20x20
    superficie = np.full((20, 20), 30.0)
    superficie[:, 10:] = 40.0  # escalon: la unidad se acuna hacia el este
    builder = _builder_con_superficie(demo_data_dir, tmp_path, superficie, capa=1)
    sim = builder.build_simulation()
    botm = np.asarray(sim.get_model("geom_test").dis.botm.get_data())

    assert np.allclose(botm[0][:, :10], 30.0)
    assert np.allclose(botm[0][:, 10:], 40.0)
    assert np.allclose(botm[1], 0.0)  # la capa 2 conserva su base plana


def test_superficie_se_recorta_para_garantizar_espesor(demo_data_dir, tmp_path):
    # Base por sobre el top (60): debe recortarse a top - espesor_min, no invertir la capa
    superficie = np.full((20, 20), 80.0)
    builder = _builder_con_superficie(demo_data_dir, tmp_path, superficie, capa=1)
    sim = builder.build_simulation()
    dis = sim.get_model("geom_test").dis
    top = np.asarray(dis.top.get_data(), dtype=float)
    botm = np.asarray(dis.botm.get_data())

    assert np.all(botm[0] < top)            # geometria valida
    assert np.all(botm[1] < botm[0])        # capas decrecientes
    assert np.allclose(botm[0], 60.0 - 0.5)  # recortada al espesor minimo


def test_forma_invalida_se_ignora(demo_data_dir, tmp_path):
    superficie = np.full((5, 5), 30.0)  # no calza con la grilla 20x20
    builder = _builder_con_superficie(demo_data_dir, tmp_path, superficie, capa=1)
    sim = builder.build_simulation()
    botm = np.asarray(sim.get_model("geom_test").dis.botm.get_data())
    assert np.allclose(botm[0], 35.0)  # se mantiene la base plana de capas_modelo.csv


@pytest.mark.slow
def test_prep_remuestrea_base_capa(tmp_path):
    gpd = pytest.importorskip("geopandas")
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    from shapely.geometry import Polygon

    from yaku.prep import prepare_from_sources

    src = tmp_path / "fuente"
    src.mkdir()
    poly = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    gpd.GeoDataFrame({"id": [1]}, geometry=[poly], crs=None).to_file(src / "dominio.shp")
    res = 50.0
    n = int(1000 / res)
    transform = from_origin(0, 1000, res, res)
    dem = np.full((n, n), 100.0, dtype="float32")
    with rasterio.open(src / "dem.tif", "w", driver="GTiff", height=n, width=n, count=1,
                       dtype="float32", transform=transform, crs=None) as dst:
        dst.write(dem, 1)
    # base de la capa 1: plano inclinado 40 -> 60 m (oeste a este)
    base = np.tile(np.linspace(40.0, 60.0, n, dtype="float32"), (n, 1))
    with rasterio.open(src / "base_capa1.tif", "w", driver="GTiff", height=n, width=n, count=1,
                       dtype="float32", transform=transform, crs=None) as dst:
        dst.write(base, 1)

    tablas = tmp_path / "tablas"
    resumen = prepare_from_sources(src, tablas, tmp_path / "gis", cellsize=100.0, nlay=2, espesor=40.0)

    assert resumen.get("superficies_capas") == [1]
    grid = pd.read_csv(tablas / "botm_grid_capa1.csv", header=None).to_numpy(dtype=float)
    assert grid.shape == (10, 10)
    assert grid[0, 0] < grid[0, -1]  # conserva la pendiente oeste-este
