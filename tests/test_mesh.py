"""Test de malla Voronoi/DISV (requiere binario triangle)."""

import pytest

from mfworkflow.binaries import resolve_exe


@pytest.mark.slow
def test_voronoi_y_disv(tmp_path):
    if resolve_exe("triangle") is None:
        pytest.skip("triangle no instalado (get-modflow :flopy)")
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Point, Polygon

    from mfworkflow.mesh.voronoi import build_voronoi, run_disv_flow

    gis = tmp_path / "gis"
    gis.mkdir()
    poly = Polygon([(0, 0), (2000, 0), (2000, 2000), (0, 2000)])
    gpd.GeoDataFrame({"id": [1]}, geometry=[poly], crs=None).to_file(gis / "dominio.shp")
    gpd.GeoDataFrame({"nombre": ["P1"]}, geometry=[Point(1000, 1000)], crs=None).to_file(gis / "pozos.shp")

    out = build_voronoi(gis / "dominio.shp", gis, tmp_path / "malla", cell_size=200.0, refine_factor=5.0)
    assert out["ncpl"] > 50
    assert out["figura"].exists()

    png = run_disv_flow(out["gridprops"], tmp_path / "malla")
    assert png.exists()


@pytest.mark.slow
def test_disv_multicapa(tmp_path):
    """build_disv_model arma un DISV de varias capas drapeadas y corre."""
    if resolve_exe("triangle") is None or resolve_exe("mf6") is None:
        pytest.skip("triangle/mf6 no instalados")
    gpd = pytest.importorskip("geopandas")
    import flopy
    from shapely.geometry import Polygon

    from mfworkflow.mesh.voronoi import build_disv_model, build_voronoi

    gis = tmp_path / "gis"
    gis.mkdir()
    poly = Polygon([(0, 0), (2000, 0), (2000, 2000), (0, 2000)])
    gpd.GeoDataFrame({"id": [1]}, geometry=[poly], crs=None).to_file(gis / "dominio.shp")

    out = build_voronoi(gis / "dominio.shp", gis, tmp_path / "malla", cell_size=300.0, refine_factor=3.0)
    capas = [{"espesor": 25.0, "k": 8.0}, {"espesor": 25.0, "k": 2.0}, {"espesor": 30.0, "k": 0.5}]
    res = build_disv_model(out["gridprops"], tmp_path / "malla", capas=capas, recharge=5e-4)

    assert res["nlay"] == 3
    head = flopy.utils.HeadFile(str(res["hds"])).get_data()
    assert head.shape[0] == 3            # carga por capa
    assert res["png"].exists()
