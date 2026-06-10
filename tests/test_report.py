"""Tests del informe doble perfil (astm | sea)."""

import numpy as np

from yaku.report.pdf import PERFILES, write_pdf


def test_perfiles_definidos():
    assert "astm" in PERFILES and "sea" in PERFILES
    # el perfil sea incluye plan de seguimiento
    titulos_sea = [t for t, _ in PERFILES["sea"]["secciones"]]
    assert any("seguimiento" in t.lower() for t in titulos_sea)


def test_secciones_md_editable(tmp_path):
    from yaku.report.pdf import _norm, _texto_usuario, leer_secciones_md

    md = tmp_path / "secciones.md"
    md.write_text("## Modelo conceptual\nAcuifero libre en gravas.\n\n## Conclusiones\nModelo valido.\n",
                  encoding="utf-8")
    textos = leer_secciones_md(md)
    assert "modelo conceptual" in textos
    assert _texto_usuario(textos, _norm("3. Modelo conceptual")) == "Acuifero libre en gravas."
    assert _texto_usuario(textos, _norm("12. Conclusiones")).startswith("Modelo valido")
    # seccion sin texto del usuario -> None (cae a la guia)
    assert _texto_usuario(textos, _norm("7. Balance hidrico")) is None


def test_secciones_md_ignora_comentarios(tmp_path):
    from yaku.report.pdf import _norm, _texto_usuario, leer_secciones_md

    md = tmp_path / "secciones.md"
    md.write_text(
        "## Modelo conceptual\n<!-- ejemplo: describe las unidades -->\n\n"
        "## Conclusiones\nModelo representativo del acuifero.\n",
        encoding="utf-8")
    textos = leer_secciones_md(md)
    # la seccion con solo un comentario-guia no aporta texto (cae a la guia por defecto)
    assert _texto_usuario(textos, _norm("4. Modelo conceptual")) is None
    # la seccion con redaccion real si se inyecta
    assert _texto_usuario(textos, _norm("13. Conclusiones")).startswith("Modelo representativo")


def test_perfil_sea_tiene_marco_y_glosario():
    titulos = [_t.lower() for _t, _ in PERFILES["sea"]["secciones"]]
    assert any("marco normativo" in t for t in titulos)
    assert any("glosario" in t for t in titulos)


def test_write_pdf_ambos_perfiles(tmp_path):
    head = np.linspace(40, 60, 2 * 5 * 5).reshape(2, 5, 5)
    for perfil in ("astm", "sea"):
        out = write_pdf(tmp_path / f"informe_{perfil}.pdf", head, [1.0], perfil=perfil)
        assert out.exists()
        assert out.stat().st_size > 0


def test_write_docx_perfil_sea(tmp_path):
    import pytest

    pytest.importorskip("docx")
    from yaku.config import resolve_project_config
    from yaku.report.docx_report import write_docx
    from yaku.report.resultados import recolectar_resultados

    cfg = resolve_project_config("examples/caso_demo")
    res = recolectar_resultados(cfg, figuras_dir=tmp_path)
    # a_pdf=False: no depende de LibreOffice (soffice) en el entorno de test
    out = write_docx(tmp_path / "informe.docx", cfg, perfil="sea", resultados=res, a_pdf=False)
    assert out.exists() and out.suffix == ".docx" and out.stat().st_size > 0
