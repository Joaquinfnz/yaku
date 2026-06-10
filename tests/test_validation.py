"""Tests de validacion de datos (estructura + geometria/unidades)."""

import pandas as pd

from yaku.builder import ModflowModelBuilder, validate_geometry_and_units


def test_demo_data_valida(demo_data_dir, tmp_path):
    builder = ModflowModelBuilder(demo_data_dir, tmp_path, model_name="t")
    assert builder.validate_input_data() == []
    geo = validate_geometry_and_units(demo_data_dir)
    assert geo.ok, geo.errors


def test_botm_no_decreciente_es_error(demo_data_dir, tmp_path):
    # Copia los datos y rompe la coherencia geometrica de capas
    data = tmp_path / "datos"
    data.mkdir()
    for csv in demo_data_dir.glob("*.csv"):
        (data / csv.name).write_text(csv.read_text(encoding="utf-8"), encoding="utf-8")
    capas = pd.read_csv(data / "capas_modelo.csv")
    # invierte botm para que NO decrezca
    capas.loc[1, "botm_m"] = capas.loc[0, "botm_m"] + 10
    capas.to_csv(data / "capas_modelo.csv", index=False)

    geo = validate_geometry_and_units(data)
    assert not geo.ok
    assert any("decrecer" in e for e in geo.errors)


def test_k_implausible_es_advertencia(demo_data_dir, tmp_path):
    data = tmp_path / "datos"
    data.mkdir()
    for csv in demo_data_dir.glob("*.csv"):
        (data / csv.name).write_text(csv.read_text(encoding="utf-8"), encoding="utf-8")
    params = pd.read_csv(data / "parametros_modelo.csv")
    params.loc[params["clave"] == "k", "valor"] = 1e8  # absurdo
    params.to_csv(data / "parametros_modelo.csv", index=False)

    geo = validate_geometry_and_units(data)
    assert any("plausible" in w for w in geo.warnings)
