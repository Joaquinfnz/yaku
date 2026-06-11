"""Tests de los lectores de clima CR2 / CAMELS-CL -> clima.csv."""

import pandas as pd
import pytest

from yaku.prep import clima_fuentes as cf


def test_leer_cr2_mensual_con_metadatos(tmp_path):
    # Exporte tipico del Explorador Climatico: metadatos + agno/mes/valor
    p = tmp_path / "pr_cr2.csv"
    p.write_text(
        "Estacion: Quinta Normal\n"
        "Variable: Precipitacion mensual (mm)\n"
        "agno,mes,valor\n"
        "2020,1,0.5\n"
        "2020,2,-9999\n"
        "2020,3,45.2\n",
        encoding="utf-8",
    )
    df = cf.leer_cr2(p)
    assert list(df.columns) == ["fecha", "valor"]
    assert len(df) == 3
    assert df["fecha"].iloc[0] == pd.Timestamp("2020-01-01")
    assert pd.isna(df["valor"].iloc[1])  # -9999 -> nodata
    assert df["valor"].iloc[2] == 45.2


def test_leer_cr2_diario_con_fecha(tmp_path):
    p = tmp_path / "pr_diario.csv"
    p.write_text("fecha,pr\n2021-06-01,12.0\n2021-06-02,0.0\n", encoding="utf-8")
    df = cf.leer_cr2(p)
    assert len(df) == 2 and df["valor"].iloc[0] == 12.0


def test_leer_camels_por_gauge_id(tmp_path):
    p = tmp_path / "precip_cr2met_day.txt"
    p.write_text(
        "date\t1001\t2002\n"
        "1990-04-01\t5.0\t1.0\n"
        "1990-04-02\t0.0\t2.5\n",
        encoding="utf-8",
    )
    df = cf.leer_camels(p, "2002")
    assert df["valor"].tolist() == [1.0, 2.5]
    with pytest.raises(ValueError, match="gauge_id"):
        cf.leer_camels(p, "9999")


def test_construir_clima_combina_series(tmp_path):
    precip = pd.DataFrame({"fecha": pd.to_datetime(["2020-01-01", "2020-02-01"]), "valor": [10.0, 20.0]})
    temp = pd.DataFrame({"fecha": pd.to_datetime(["2020-01-01", "2020-02-01"]), "valor": [15.0, 16.0]})
    out = cf.construir_clima(precip, temp=temp, out_path=tmp_path / "clima.csv")
    clima = pd.read_csv(out)
    assert list(clima.columns) == ["fecha", "precip_mm", "temp_c"]
    assert clima["precip_mm"].tolist() == [10.0, 20.0]
    assert clima["temp_c"].tolist() == [15.0, 16.0]


def test_clima_desde_fuente_cr2_end_to_end(tmp_path):
    p = tmp_path / "pr.csv"
    p.write_text("agno,mes,valor\n2020,1,30\n2020,2,40\n", encoding="utf-8")
    out = cf.clima_desde_fuente(tmp_path / "clima.csv", fuente="cr2", precip=p)
    clima = pd.read_csv(out)
    assert clima["precip_mm"].sum() == 70


def test_clima_desde_fuente_camels_requiere_estacion(tmp_path):
    p = tmp_path / "pr.txt"
    p.write_text("date\t1001\n1990-04-01\t5.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="estacion"):
        cf.clima_desde_fuente(tmp_path / "clima.csv", fuente="camels", precip=p)
