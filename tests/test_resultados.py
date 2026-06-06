"""Tests del recolector de resultados (informe data-driven)."""

from mfworkflow.config import resolve_project_config
from mfworkflow.report.resultados import leer_balance, recolectar_resultados


def test_recolecta_caso_demo(tmp_path):
    cfg = resolve_project_config("examples/caso_demo")
    res = recolectar_resultados(cfg, figuras_dir=tmp_path)
    # cargas + estadisticos por capa
    assert res.head is not None
    assert len(res.stats_por_capa) == res.head.shape[0]
    # un mapa de carga por capa (grilla estructurada)
    assert len(res.mapas_carga) == res.head.shape[0]
    # parametros y balance reales
    assert res.parametros is not None and res.parametros["globales"] is not None
    assert res.balance is not None
    # caso_demo trae calibracion
    assert res.calibracion is not None and not res.calibracion["metricas"].empty


def test_napa_y_caudal_base(tmp_path):
    cfg = resolve_project_config("examples/caso_demo")
    res = recolectar_resultados(cfg, figuras_dir=tmp_path)
    # profundidad de napa (estructurado) con su umbral GDE
    assert res.napa is not None and res.napa["png"].exists()
    assert "celdas_someras" in res.napa["stats"]
    # caso_demo tiene rio.csv -> intercambio rio-acuifero (caudal base)
    assert res.caudal_base is not None and "acuifero_a_rio_m3d" in res.caudal_base


def test_seccion_vertical(tmp_path):
    cfg = resolve_project_config("examples/caso_demo")
    res = recolectar_resultados(cfg, figuras_dir=tmp_path)
    assert res.seccion_vertical is not None and res.seccion_vertical.exists()


def test_balance_por_capa(tmp_path):
    cfg = resolve_project_config("examples/caso_demo")
    res = recolectar_resultados(cfg, figuras_dir=tmp_path)
    assert res.balance_por_capa is not None
    df = res.balance_por_capa
    assert {"componente", "capa", "entrada_m3d", "salida_m3d"} <= set(df.columns)
    assert int(df["capa"].max()) <= res.head.shape[0]


def test_criterio_calibracion_y_residuos(tmp_path):
    cfg = resolve_project_config("examples/caso_demo")
    res = recolectar_resultados(cfg, figuras_dir=tmp_path)
    # criterio SEA (MAE vs 5% de la dif. maxima observada)
    assert res.criterio_calibracion is not None
    crit = res.criterio_calibracion
    assert {"mae_m", "rmse_m", "umbral_aceptable_m", "cumple"} <= set(crit)
    assert crit["umbral_aceptable_m"] >= 0
    # histograma de residuos generado
    assert res.residuos_figs is not None and res.residuos_figs["histograma"].exists()


def test_balance_barras(tmp_path):
    cfg = resolve_project_config("examples/caso_demo")
    res = recolectar_resultados(cfg, figuras_dir=tmp_path)
    assert res.balance_barras is not None and res.balance_barras.exists()


def test_balance_tiene_total(tmp_path):
    cfg = resolve_project_config("examples/caso_demo")
    bal = leer_balance(cfg.resultados_dir / f"{cfg.model_name}.lst", tmp_path / "balance.csv")
    assert bal is not None
    df = bal["df"]
    assert "componente" in df.columns
    assert "TOTAL" in set(df["componente"])
    assert (tmp_path / "balance.csv").exists()
