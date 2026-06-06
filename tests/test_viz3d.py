"""Test de visualizacion 3D (exportacion VTK; el PNG depende de OpenGL)."""

import pytest

from mfworkflow.builder import ModflowModelBuilder


@pytest.mark.slow
def test_view3d_exporta_vtk(demo_data_dir, tmp_path):
    from mfworkflow.viz import plots_3d

    ws = tmp_path / "model"
    ModflowModelBuilder(demo_data_dir, ws, model_name="m").build_and_run(postprocess=False)
    out = plots_3d.run(ws, "m", tmp_path / "v3d")
    assert "vtk" in out and out["vtk"].exists()
    # El VTK lleva litologia (K), recarga y marcadores de rio/pozos, no solo la carga.
    pv = pytest.importorskip("pyvista")
    arrays = set(pv.read(str(out["vtk"])).array_names)
    assert "K_m_d" in arrays
    assert {"rio", "pozos"} <= arrays
