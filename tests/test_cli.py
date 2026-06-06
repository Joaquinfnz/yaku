"""Tests de la CLI mfw (new + pipeline)."""

import pytest

from mfworkflow.cli import main


def test_new_crea_proyecto_autocontenido(tmp_path):
    rc = main(["new", "proj_test", "--dest", str(tmp_path), "--autor", "Joaquin Fernandez"])
    assert rc == 0
    proj = tmp_path / "proj_test"
    assert (proj / "config.yaml").exists()
    assert (proj / "datos" / "tablas" / "parametros_modelo.csv").exists()
    # placeholders sustituidos
    cfg_text = (proj / "config.yaml").read_text(encoding="utf-8")
    assert "{{nombre}}" not in cfg_text
    assert "{{empresa}}" not in cfg_text
    assert "proj_test" in cfg_text
    assert "Joaquin Fernandez" in cfg_text


def test_new_con_tipo_dewatering(tmp_path):
    rc = main(["new", "p", "--dest", str(tmp_path), "--tipo", "dewatering"])
    assert rc == 0
    cfg = (tmp_path / "p" / "config.yaml").read_text(encoding="utf-8")
    assert "dewatering" in cfg.lower()       # proposito orientado al tipo
    assert 'perfil: "sea"' in cfg            # perfil SEIA por defecto en estudios SEA


@pytest.mark.slow
def test_pipeline_demo_genera_informe(tmp_path):
    # Instancia un proyecto nuevo y corre el pipeline completo
    assert main(["new", "p", "--dest", str(tmp_path)]) == 0
    proj = tmp_path / "p"
    assert main(["pipeline", "--project", str(proj)]) == 0
    pdfs = list((proj / "informe").glob("*.pdf")) + list((proj / "informe").glob("*.md"))
    assert pdfs, "no se genero informe"
    assert (proj / "resultados" / "inputs_metadata.json").exists()
