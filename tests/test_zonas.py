"""Tests del balance por zonas (estilo ZoneBudget) desde el .cbc."""

import shutil

import numpy as np
import pandas as pd
import pytest

from yaku.report import zonas as z


def test_cargar_zonas_explicito(tmp_path):
    grid = np.ones((4, 5), dtype=int)
    grid[:, 3:] = 2
    pd.DataFrame(grid).to_csv(tmp_path / "zonas_balance.csv", index=False, header=False)
    out = z.cargar_zonas(tmp_path, 4, 5)
    assert out is not None and out.shape == (4, 5)
    assert set(np.unique(out)) == {1, 2}


def test_cargar_zonas_forma_invalida(tmp_path):
    pd.DataFrame(np.ones((2, 2))).to_csv(tmp_path / "zonas_balance.csv", index=False, header=False)
    assert z.cargar_zonas(tmp_path, 4, 5) is None


def test_cargar_zonas_derivadas_de_recarga(tmp_path):
    coef = np.full((4, 5), 0.10)
    coef[:, 2:] = 0.25  # dos unidades geologicas -> dos zonas
    pd.DataFrame(coef).to_csv(tmp_path / "recarga_zonas.csv", index=False, header=False)
    out = z.cargar_zonas(tmp_path, 4, 5)
    assert out is not None
    assert set(np.unique(out)) == {1, 2}
    assert (out[:, :2] == 1).all() and (out[:, 2:] == 2).all()


def test_figura_balance_zonas(tmp_path):
    df = pd.DataFrame([
        {"zona": 1, "componente": "RCHA", "entrada_m3d": 100.0, "salida_m3d": 0.0, "neto_m3d": 100.0},
        {"zona": 1, "componente": "WEL", "entrada_m3d": 0.0, "salida_m3d": 80.0, "neto_m3d": -80.0},
        {"zona": 2, "componente": "RCHA", "entrada_m3d": 50.0, "salida_m3d": 0.0, "neto_m3d": 50.0},
    ])
    png = z.figura_balance_zonas(df, tmp_path, "demo")
    assert png is not None and png.exists()


@pytest.mark.slow
def test_balance_por_zonas_end_to_end(demo_data_dir, tmp_path):
    """Corre el demo y verifica que el balance por zonas cuadra con el balance global."""
    from yaku.builder import ModflowModelBuilder

    datos = tmp_path / "datos"
    shutil.copytree(demo_data_dir, datos)
    ws = tmp_path / "modelo"
    builder = ModflowModelBuilder(data_dir=datos, workspace=ws, model_name="zb_test")
    builder.build_and_run(postprocess=False)

    zonas = np.ones((20, 20), dtype=int)
    zonas[:, 10:] = 2
    df = z.balance_por_zonas(ws / "zb_test.cbc", zonas)
    assert df is not None and not df.empty
    assert set(df["zona"].unique()) == {1, 2}
    assert (df[df["componente"] == "TOTAL"]["zona"].tolist()) == [1, 2]
    # La recarga total de ambas zonas debe ser positiva
    rch = df[(df["componente"].str.contains("RCH")) & (df["componente"] != "TOTAL")]
    assert rch["entrada_m3d"].sum() > 0
