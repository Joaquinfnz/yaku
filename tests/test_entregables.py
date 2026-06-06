"""Test del paquete de entregables SEIA."""

import shutil

from mfworkflow.config import resolve_project_config
from mfworkflow.report.entregables import armar_entregables


def test_arma_paquete_seia(tmp_path):
    # Copia caso_demo (con sus resultados) a un tmp y arma el paquete ahí.
    dest_proj = tmp_path / "caso_demo"
    shutil.copytree("examples/caso_demo", dest_proj)
    cfg = resolve_project_config(dest_proj)

    paquete = armar_entregables(cfg, perfil="sea")

    assert paquete.is_dir()
    pdfs = list(paquete.glob("informe_*_sea.pdf"))
    assert pdfs and pdfs[0].stat().st_size > 0
    assert (paquete / "MANIFIESTO.md").exists()
    assert (paquete / "plan_seguimiento.csv").exists()
    # subcarpetas con contenido
    assert any((paquete / "figuras").glob("*.png"))
    assert any((paquete / "tablas").glob("*.csv"))
    assert any((paquete / "modelo").iterdir())
    # el manifiesto menciona el hash de entradas
    assert "Hash de entradas" in (paquete / "MANIFIESTO.md").read_text(encoding="utf-8")
