"""Tests de calibracion: evaluacion de ajuste y setup PEST++."""

import pytest

from mfworkflow.builder import ModflowModelBuilder
from mfworkflow.calibration import evaluate_fit, setup_pest


@pytest.mark.slow
def test_evaluate_fit_metricas(demo_data_dir, tmp_path):
    ws = tmp_path / "model"
    builder = ModflowModelBuilder(demo_data_dir, ws, model_name="m")
    builder.build_and_run(postprocess=False)
    metrics = evaluate_fit(ws / "m.hds", demo_data_dir / "observaciones_nivel.csv", tmp_path / "cal")
    valores = dict(zip(metrics["metrica"], metrics["valor"]))
    assert valores["n_observaciones"] == 4
    assert valores["rmse_m"] >= 0
    assert (tmp_path / "cal" / "metricas_ajuste.csv").exists()


@pytest.mark.slow
def test_sensibilidad_oat(demo_data_dir, tmp_path):
    from mfworkflow.calibration.sensibilidad import sensibilidad_oat

    df = sensibilidad_oat(
        demo_data_dir, demo_data_dir / "parametros_calibracion.csv",
        demo_data_dir / "observaciones_nivel.csv", tmp_path / "sens",
        model_name="m", delta=0.1,
    )
    assert "sensibilidad" in df.columns and "parametro" in df.columns
    assert len(df) >= 1


def test_obs_names_unicos():
    """Nombres de observacion truncados a 20 chars no deben colisionar."""
    from mfworkflow.calibration.pest_setup import _safe_obs_names

    nombres = ["Pozo_de_monitoreo_norte_01", "Pozo_de_monitoreo_norte_02", "P1"]
    out = _safe_obs_names(nombres)
    assert len(set(out)) == len(out)         # todos unicos
    assert all(len(n) <= 20 for n in out)    # respetan el limite de PEST


def test_setup_pest_genera_pst(demo_data_dir, tmp_path):
    pytest.importorskip("pyemu")
    pst = setup_pest(
        tmp_path / "pest",
        demo_data_dir,
        demo_data_dir / "observaciones_nivel.csv",
        demo_data_dir / "parametros_calibracion.csv",
        max_params=2,
        noptmax=1,
    )
    assert pst.exists()
    assert (tmp_path / "pest" / "forward_run.py").exists()
    assert (tmp_path / "pest" / "parametros_pest.tpl").exists()
