"""Tests del contrato de insumos (obligatorios / importantes / opcionales)."""

import shutil

from mfworkflow.config import resolve_project_config
from mfworkflow.insumos import MINIMOS_PARA_CORRER, formatear, revisar_insumos


def test_caso_demo_tiene_minimos():
    cfg = resolve_project_config("examples/caso_demo")
    rep = revisar_insumos(cfg)
    assert rep.ok_minimos is True
    assert rep.faltan_para_correr == []
    # caso_demo no trae datos/fuente -> dem.tif/caudales faltan (importantes), no bloquean
    assert "dem.tif" in rep.faltan("importante")


def test_formatear_agrupa_por_nivel():
    cfg = resolve_project_config("examples/caso_demo")
    texto = "\n".join(formatear(revisar_insumos(cfg), raiz=cfg.project_dir))
    assert "OBLIGATORIOS" in texto and "IMPORTANTES" in texto and "OPCIONALES" in texto


def test_crear_plantilla(tmp_path):
    import pandas as pd

    from mfworkflow.prep.skeletons import crear_plantilla

    p = crear_plantilla(tmp_path, "capas_modelo.csv")
    assert p is not None and p.exists()
    df = pd.read_csv(p)
    assert {"layer", "top_m", "botm_m", "kx_m_d"} <= set(df.columns) and len(df) >= 2
    # no sobrescribe si ya existe
    assert crear_plantilla(tmp_path, "capas_modelo.csv") is None
    # nombre desconocido -> None
    assert crear_plantilla(tmp_path, "noexiste.csv") is None


def test_bloquea_si_faltan_minimos(tmp_path):
    # Copia caso_demo y borra una tabla minima -> ok_minimos False y la detecta.
    dest = tmp_path / "proj"
    shutil.copytree("examples/caso_demo", dest)
    (dest / "datos" / "tablas" / "stress_periods.csv").unlink()
    rep = revisar_insumos(resolve_project_config(dest))
    assert rep.ok_minimos is False
    assert "stress_periods.csv" in rep.faltan_para_correr
    assert "stress_periods.csv" in MINIMOS_PARA_CORRER
