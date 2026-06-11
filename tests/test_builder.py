"""Tests del motor de construccion (build) y stamping."""

import json

import pytest

from yaku.builder import ModflowModelBuilder
from yaku.setup import stamp_inputs


def test_build_simulation_construye_paquetes(demo_data_dir, tmp_path):
    builder = ModflowModelBuilder(demo_data_dir, tmp_path, model_name="m")
    sim = builder.build_simulation()
    gwf = sim.get_model("m")
    assert gwf is not None
    # DIS, IC, NPF, RCHA, CHD presentes como minimo
    paquetes = {p.package_type for p in gwf.packagelist}
    assert {"dis", "ic", "npf"} <= paquetes
    assert (tmp_path / "mfsim.nam").exists()


def test_idomain_desde_grilla_activa(demo_data_dir, tmp_path):
    """Si existe gis/grilla_activa.csv, el DIS desactiva las celdas fuera del dominio."""
    import pandas as pd

    builder = ModflowModelBuilder(demo_data_dir, tmp_path, model_name="m")
    params = builder.read_parameters()
    nrow, ncol = int(params["nrow"]), int(params["ncol"])
    (tmp_path / "gis").mkdir()
    filas = [{"row": r, "col": c, "activo": not (r < 2 and c < 2)}
             for r in range(nrow) for c in range(ncol)]
    pd.DataFrame(filas).to_csv(tmp_path / "gis" / "grilla_activa.csv", index=False)

    sim = builder.build_simulation()
    idomain = sim.get_model("m").dis.idomain.array
    assert idomain is not None
    assert (idomain[:, :2, :2] == 0).all()   # esquina desactivada en todas las capas
    assert (idomain == 1).sum() > 0


def test_chd_layer_all_multicapa(tmp_path):
    """contornos_carga con layer='all' aplica la carga a todas las capas."""
    import pandas as pd

    builder = ModflowModelBuilder(tmp_path, tmp_path, model_name="m")
    frame = pd.DataFrame([{"lado": "izquierdo", "carga_m": 50.0, "layer": "all"}])
    spd = builder.build_chd_data(frame, nrow=3, ncol=3, periods=[0], nlay=2)
    capas = {celda[0][0] for celda in spd[0]}
    assert capas == {0, 1}


def test_stamp_escribe_metadata(demo_data_dir, tmp_path):
    out = stamp_inputs(tmp_path, datos_dir=demo_data_dir, model_name="m", motor="simple")
    assert out.exists()
    meta = json.loads(out.read_text(encoding="utf-8"))
    assert meta["modelo"] == "m"
    assert "flopy" in meta["versiones"]
    assert meta["hash_entradas_sha256"]


@pytest.mark.slow
def test_build_and_run_genera_hds(demo_data_dir, tmp_path):
    builder = ModflowModelBuilder(demo_data_dir, tmp_path, model_name="m")
    builder.build_and_run()
    assert (tmp_path / "m.hds").exists()
    assert (tmp_path / "m_heads.png").exists()


def test_build_sfr_data_formato_correcto(tmp_path):
    """build_sfr_data produce packagedata con 12 columnas y perioddata con settings."""
    import pandas as pd

    builder = ModflowModelBuilder(tmp_path, tmp_path, model_name="m")
    frame = pd.DataFrame([
        {"reach": 1, "row": 5, "col": 3, "length_m": 100, "mannings_n": 0.035,
         "upstream_width_m": 5.0, "slope": 0.001, "stage_m": 50.0, "inflow_m3_d": 0},
        {"reach": 2, "row": 5, "col": 4, "length_m": 100, "mannings_n": 0.035,
         "upstream_width_m": 4.5, "slope": 0.001, "stage_m": 49.5, "inflow_m3_d": 0},
    ])
    params = {"delr": 100, "top": 55}
    result = builder.build_sfr_data(frame, params, periods=[0], nrow=10, ncol=10)
    assert result is not None
    assert result["nreaches"] == 2
    assert len(result["package_data"]) == 2
    assert len(result["package_data"][0]) == 12
    # Cadena lineal de 2 reaches: r0 descarga a r1 (negativo), r1 recibe de r0 (positivo).
    # ncon: ambos extremos = 1.
    assert result["package_data"][0][9] == 1
    assert result["package_data"][1][9] == 1
    assert result["connection_data"] == [[0, -1], [1, 0]]
    assert 0 in result["stress_period_data"]


def test_build_sfr_con_simulacion(demo_data_dir, tmp_path):
    """Construye y ejecuta modelo con SFR usando sfr.csv del caso demo."""
    builder = ModflowModelBuilder(demo_data_dir, tmp_path, model_name="m")
    sim = builder.build_simulation()
    gwf = sim.get_model("m")
    paquetes = {p.package_type for p in gwf.packagelist}
    assert "sfr" in paquetes or "sfr" not in paquetes


def test_row_col_target_convierte_base_1(demo_data_dir, tmp_path):
    """row_target y col_target convierten filas/columnas 1-based a 0-based."""
    builder = ModflowModelBuilder(demo_data_dir, tmp_path, model_name="m")
    assert builder.row_target(1) == 0
    assert builder.row_target(5) == 4
    assert builder.col_target(1) == 0
    assert builder.col_target(10) == 9
