"""Tests del motor de construccion (build) y stamping."""

import json

import pytest

from mfworkflow.builder import ModflowModelBuilder
from mfworkflow.setup import stamp_inputs


def test_build_simulation_construye_paquetes(demo_data_dir, tmp_path):
    builder = ModflowModelBuilder(demo_data_dir, tmp_path, model_name="m")
    sim = builder.build_simulation()
    gwf = sim.get_model("m")
    assert gwf is not None
    # DIS, IC, NPF, RCHA, CHD presentes como minimo
    paquetes = set(gwf.package_type_dict.keys())
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
