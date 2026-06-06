"""Tests de trayectorias (MODPATH 7 real, si esta disponible)."""

import pytest

from mfworkflow.binaries import resolve_exe
from mfworkflow.builder import ModflowModelBuilder


@pytest.mark.slow
def test_modpath7_zonas_captura(demo_data_dir, tmp_path):
    if resolve_exe("mp7") is None:
        pytest.skip("mp7 no instalado (get-modflow :flopy)")
    from mfworkflow.pathlines import modpath7

    ws = tmp_path / "model"
    builder = ModflowModelBuilder(demo_data_dir, ws, model_name="m")
    builder.build_and_run(postprocess=False)

    out = modpath7.run(ws, demo_data_dir, tmp_path / "tray", model_name="m", direction="backward")
    assert out["figura"].exists()
    # con pozos en el demo hay endpoints con tiempos de viaje
    assert "endpoints" in out and out["endpoints"].exists()
