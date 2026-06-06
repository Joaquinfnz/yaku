"""Test del calculo de recarga desde clima (balance de suelo, dentro del workflow)."""

import pandas as pd

from mfworkflow.prep.recarga import balance_suelo, calcular_recarga


def test_balance_suelo_humedo_vs_seco():
    # P >> ET -> recarga; P < ET -> sin recarga
    assert balance_suelo([200], [40], cc_mm=50)[0] > 0
    assert balance_suelo([10], [40], cc_mm=50)[0] == 0


def test_calcular_recarga_escribe_tabla(tmp_path):
    clima = tmp_path / "clima.csv"
    pd.DataFrame({
        "fecha": ["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01"],
        "precip_mm": [200, 150, 50, 10],
        "temp_c": [8, 7, 5, 3],
        "et0_mm": [40, 35, 30, 20],
    }).to_csv(clima, index=False)

    res = calcular_recarga(clima, tmp_path / "tablas", metodo="balance")
    assert res["archivo"].exists()
    df = pd.read_csv(res["archivo"])
    assert list(df.columns) == ["stress_period", "recharge_m_d"]
    assert (df["recharge_m_d"] >= 0).all() and len(df) == 4
    # el mes humedo recarga mas que el seco
    assert df["recharge_m_d"].iloc[0] > df["recharge_m_d"].iloc[3]


def test_metodo_coeficiente(tmp_path):
    clima = tmp_path / "clima.csv"
    pd.DataFrame({"precip_mm": [100, 50]}).to_csv(clima, index=False)
    res = calcular_recarga(clima, tmp_path / "t", metodo="coeficiente", coef_infiltracion=0.2)
    assert res["metodo"] == "coeficiente"
    df = pd.read_csv(res["archivo"])
    assert (df["recharge_m_d"] > 0).all()
