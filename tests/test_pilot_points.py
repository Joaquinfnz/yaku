"""Tests de calibracion por pilot points (generacion, interpolacion, setup PEST, builder)."""

import shutil

import numpy as np
import pandas as pd
import pytest

from yaku.calibration import pilot_points as pp_mod


def _params(data_dir) -> dict[str, float]:
    frame = pd.read_csv(data_dir / "parametros_modelo.csv")
    return {str(r["clave"]): float(r["valor"]) for _, r in frame.iterrows()}


def test_generar_pilot_points_cubre_la_grilla(demo_data_dir):
    params = _params(demo_data_dir)
    pp = pp_mod.generar_pilot_points(demo_data_dir, cada=5)
    assert len(pp) >= 4
    assert pp["row"].between(0, int(params["nrow"]) - 1).all()
    assert pp["col"].between(0, int(params["ncol"]) - 1).all()
    # Valor inicial = K del modelo, para que la corrida base sea el modelo sin calibrar
    assert np.allclose(pp["valor"], params["k"])
    assert pp["nombre"].is_unique


def test_interpolar_campo_constante_da_constante():
    pp = pd.DataFrame({
        "nombre": ["a", "b", "c", "d"],
        "row": [1, 1, 8, 8], "col": [1, 8, 1, 8],
        "x": [15.0, 85.0, 15.0, 85.0], "y": [85.0, 85.0, 15.0, 15.0],
        "valor": [12.5] * 4,
    })
    campo = pp_mod.interpolar_a_grilla(pp, nrow=10, ncol=10, delr=10.0, delc=10.0, metodo="lineal")
    assert campo.shape == (10, 10)
    assert np.allclose(campo, 12.5)


def test_interpolar_gradiente_es_monotono():
    pp = pd.DataFrame({
        "nombre": ["a", "b"],
        "row": [5, 5], "col": [0, 9],
        "x": [5.0, 95.0], "y": [50.0, 50.0],
        "valor": [1.0, 100.0],
    })
    campo = pp_mod.interpolar_a_grilla(pp, nrow=10, ncol=10, delr=10.0, delc=10.0, metodo="lineal")
    fila = campo[5, :]
    assert fila[0] < fila[-1]
    assert np.all(np.diff(fila) >= -1e-9)  # crece (log-lineal) hacia el punto de K alta


def test_aplicar_pilot_points_escribe_k_field(demo_data_dir, tmp_path):
    datos = tmp_path / "datos"
    shutil.copytree(demo_data_dir, datos)
    pp = pp_mod.generar_pilot_points(datos, cada=5, valor_inicial=7.7)
    pp_path = tmp_path / "pilot_points.csv"
    pp.to_csv(pp_path, index=False)

    out = pp_mod.aplicar_pilot_points(datos, pp_path, capa=1, metodo="lineal")
    params = _params(datos)
    campo = pd.read_csv(out, header=None).to_numpy(dtype=float)
    assert campo.shape == (int(params["nrow"]), int(params["ncol"]))
    assert np.allclose(campo, 7.7)


def test_builder_usa_k_field(demo_data_dir, tmp_path):
    from yaku.builder import ModflowModelBuilder

    datos = tmp_path / "datos"
    shutil.copytree(demo_data_dir, datos)
    params = _params(datos)
    nrow, ncol = int(params["nrow"]), int(params["ncol"])
    campo = np.full((nrow, ncol), 3.21)
    pd.DataFrame(campo).to_csv(datos / "k_field_capa1.csv", index=False, header=False)

    builder = ModflowModelBuilder(data_dir=datos, workspace=tmp_path / "modelo", model_name="pp_test")
    sim = builder.build_simulation()
    gwf = sim.get_model("pp_test")
    k = np.asarray(gwf.npf.k.get_data())
    assert np.allclose(k[0], 3.21)


def test_setup_pest_pilot_points_genera_caso(demo_data_dir, tmp_path):
    pytest.importorskip("pyemu")
    datos = tmp_path / "datos"
    shutil.copytree(demo_data_dir, datos)
    obs = datos / "observaciones_nivel.csv"
    assert obs.exists()

    pst_path = pp_mod.setup_pest_pilot_points(tmp_path / "pest", datos, obs, cada=5, capa=1, noptmax=1)
    assert pst_path.exists()
    assert (tmp_path / "pest" / "pilot_points.tpl").exists()
    assert (tmp_path / "pest" / "forward_run.py").exists()

    import pyemu

    pst = pyemu.Pst(str(pst_path))
    n_pp = len(pp_mod.generar_pilot_points(datos, cada=5))
    assert pst.npar == n_pp
    par = pst.parameter_data
    assert (par["partrans"] == "log").all()
    assert (par["pargp"] == "k_pp_capa1").all()
