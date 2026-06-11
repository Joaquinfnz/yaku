"""Tests de la calibracion multi-objetivo (niveles + caudal base SFR/RIV)."""

import shutil

import pandas as pd
import pytest

from yaku.calibration.caudales import caudal_base_simulado, peso_aforo


def test_peso_aforo_explicito_y_por_defecto():
    assert peso_aforo(pd.Series({"caudal_m3_d": 500.0, "peso": 0.02})) == 0.02
    # default: 10 % del caudal observado -> 1 / 50
    assert abs(peso_aforo(pd.Series({"caudal_m3_d": 500.0})) - 1.0 / 50.0) < 1e-12


def test_setup_pest_con_aforos_agrega_grupo_caudales(demo_data_dir, tmp_path):
    pytest.importorskip("pyemu")
    import pyemu

    from yaku.calibration import setup_pest

    datos = tmp_path / "datos"
    shutil.copytree(demo_data_dir, datos)
    pd.DataFrame([{"nombre": "aforo_salida", "caudal_m3_d": 800.0}]).to_csv(
        datos / "aforos.csv", index=False)

    pst_path = setup_pest(
        tmp_path / "pest", datos,
        datos / "observaciones_nivel.csv",
        datos / "parametros_calibracion.csv",
        max_params=2, noptmax=1,
    )
    assert (tmp_path / "pest" / "simulados_caudal.ins").exists()

    pst = pyemu.Pst(str(pst_path))
    obs = pst.observation_data
    caudales = obs[obs["obgnme"] == "caudales"]
    assert len(caudales) == 1
    assert float(caudales["obsval"].iloc[0]) == 800.0
    assert float(caudales["weight"].iloc[0]) == pytest.approx(1.0 / 80.0)
    # El forward generado contiene la extraccion del caudal base
    fwd = (tmp_path / "pest" / "forward_run.py").read_text(encoding="utf-8")
    assert "escribir_simulados_caudal" in fwd


def test_setup_pest_pilot_points_con_aforos(demo_data_dir, tmp_path):
    pytest.importorskip("pyemu")
    import pyemu

    from yaku.calibration import setup_pest_pilot_points

    datos = tmp_path / "datos"
    shutil.copytree(demo_data_dir, datos)
    pd.DataFrame([{"nombre": "aforo_salida", "caudal_m3_d": 600.0, "peso": 0.01}]).to_csv(
        datos / "aforos.csv", index=False)

    pst_path = setup_pest_pilot_points(tmp_path / "pest_pp", datos,
                                       datos / "observaciones_nivel.csv", cada=8, noptmax=1)
    pst = pyemu.Pst(str(pst_path))
    caudales = pst.observation_data[pst.observation_data["obgnme"] == "caudales"]
    assert len(caudales) == 1 and float(caudales["weight"].iloc[0]) == 0.01


@pytest.mark.slow
def test_caudal_base_simulado_desde_demo(demo_data_dir, tmp_path):
    from yaku.builder import ModflowModelBuilder

    datos = tmp_path / "datos"
    shutil.copytree(demo_data_dir, datos)
    ws = tmp_path / "modelo"
    ModflowModelBuilder(data_dir=datos, workspace=ws, model_name="qb_test").build_and_run(postprocess=False)

    sim = caudal_base_simulado(ws / "qb_test.cbc")
    assert sim is not None
    assert sim["componente"] in ("SFR", "RIV")
    assert sim["rio_a_acuifero_m3d"] >= 0.0
    assert sim["acuifero_a_rio_m3d"] >= 0.0
