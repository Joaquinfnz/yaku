"""Tests de prediccion (escenario + incertidumbre)."""

import pytest

from mfworkflow.calibration import monte_carlo, scenario_drawdown


@pytest.mark.slow
def test_scenario_drawdown(demo_data_dir, tmp_path):
    out = scenario_drawdown(demo_data_dir, tmp_path / "pred", factor=1.5, model_name="m")
    assert out["mapa"].exists()
    assert out["resumen"].exists()


@pytest.mark.slow
def test_monte_carlo(demo_data_dir, tmp_path):
    out = monte_carlo(demo_data_dir, demo_data_dir / "parametros_calibracion.csv",
                      tmp_path / "mc", n=4, model_name="m")
    assert out["mapa"].exists()
