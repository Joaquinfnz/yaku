#!/usr/bin/env python3
"""Backend Word (.docx) del informe, con el mismo tema azul que el tutorial.

Reusa el DocBuilder vendorizado (`_docx_tema.py`) para escribir el informe de modelación
con la estructura de perfiles de `pdf.py` (astm | sea) y el contenido data-driven de
`resultados`. Tras escribir el .docx lo convierte a PDF con LibreOffice (soffice).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from yaku.report._docx_tema import DocBuilder, docx_to_pdf
from yaku.report.pdf import (
    GLOSARIO,
    MARCO_NORMATIVO,
    PERFILES,
    _norm,
    _texto_usuario,
)

logger = logging.getLogger("yaku")


def _filas(df: "pd.DataFrame", max_rows: int = 14) -> list[list[str]]:
    def fmt(v):
        return f"{v:.4g}" if isinstance(v, float) else str(v)
    return [[fmt(v) for v in fila] for fila in df.head(max_rows).itertuples(index=False)]


def _tabla(d: DocBuilder, df: "pd.DataFrame", max_rows: int = 14) -> None:
    d.table([str(c) for c in df.columns], _filas(df, max_rows))


def _seccion_datos(d: DocBuilder, n: str, res) -> bool:
    """Escribe el contenido data-driven de una seccion. Devuelve True si escribio algo."""
    if "calibrac" in n or "validacion" in n:
        cal = getattr(res, "calibracion", None)
        if not cal:
            return False
        d.h2("Estadísticos de ajuste")
        _tabla(d, cal["metricas"])
        crit = res.criterio_calibracion
        if crit and crit.get("cumple") is not None:
            estado = "CUMPLE" if crit["cumple"] else "NO cumple"
            d.p(f"Criterio SEA: MAE = {crit['mae_m']:.2f} m frente al umbral de "
                f"{crit['umbral_aceptable_m']:.2f} m (5 % de la diferencia máxima observada) — {estado}. "
                f"RMSE = {crit['rmse_m']:.2f} m, sesgo = {crit['sesgo_m']:.2f} m.")
        for clave, cap in (("scatter", "Observado vs simulado"),):
            if cal.get(clave):
                d.image(cal[clave], caption=cap)
        if res.residuos_figs:
            if res.residuos_figs.get("histograma"):
                d.image(res.residuos_figs["histograma"], caption="Histograma de residuos")
            if res.residuos_figs.get("mapa"):
                d.image(res.residuos_figs["mapa"], caption="Distribución espacial de residuos")
        if res.series_tiempo:
            d.image(res.series_tiempo, caption="Series de tiempo por pozo")
        return True

    if "balance" in n:
        bal = getattr(res, "balance", None)
        if not bal:
            return False
        d.h2("Balance hídrico simulado (m³/día)")
        _tabla(d, bal["df"])
        if res.balance_barras:
            d.image(res.balance_barras, caption="Entradas y salidas por componente")
        disc = bal.get("discrepancia_pct")
        if disc is not None:
            ok = abs(disc) <= 1.0
            d.p(f"Discrepancia del balance: {disc:.3g} % — "
                f"{'dentro del criterio (≤ 1 %)' if ok else 'fuera del criterio (> 1 %)'}.")
        if res.balance_por_capa is not None:
            d.h2("Balance por capa / sector (m³/día)")
            _tabla(d, res.balance_por_capa, max_rows=30)
        bz = getattr(res, "balance_por_zonas", None)
        if bz and bz.get("df") is not None:
            d.h2("Balance por zonas (m³/día)")
            d.p("Fuentes y sumideros por zona del acuífero (estilo ZoneBudget); "
                "no incluye intercambio lateral entre zonas.")
            _tabla(d, bz["df"], max_rows=40)
            if bz.get("figura"):
                d.image(bz["figura"], caption="Entradas y salidas por zona y componente")
        return True

    if "construc" in n or "diseno" in n or "numerico" in n:
        par = getattr(res, "parametros", None)
        algo = False
        if par and par.get("globales") is not None:
            d.h2("Parámetros del modelo"); _tabla(d, par["globales"]); algo = True
        if par and par.get("capas") is not None:
            d.h2("Capas hidrogeológicas"); _tabla(d, par["capas"]); algo = True
        for png in getattr(res, "mapas_carga", []) or []:
            d.image(png, caption=""); algo = True
        if res.napa:
            s = res.napa["stats"]
            d.p(f"Napa entre {s['min_m']:.1f} y {s['max_m']:.1f} m; {s['celdas_someras']} celdas "
                f"({100 * s['frac_someras']:.0f} %) con napa somera (≤ {s['umbral_m']:.1f} m, GDE).")
            d.image(res.napa["png"], caption="Profundidad del nivel freático"); algo = True
        if getattr(res, "seccion_vertical", None):
            d.image(res.seccion_vertical, caption="Sección vertical (estratos y carga)"); algo = True
        return algo

    if "sensibilidad" in n:
        if getattr(res, "sensibilidad", None) is not None and not res.sensibilidad.empty:
            d.h2("Sensibilidad de los parámetros (OAT, ±10%)"); _tabla(d, res.sensibilidad)
            return True
        return False

    if "predict" in n or "escenario" in n or "simulaciones" in n:
        pred = getattr(res, "prediccion", None)
        algo = False
        if pred and pred.get("descenso") is not None:
            d.h2("Resumen del escenario (descenso)"); _tabla(d, pred["descenso"]); algo = True
        if pred and pred.get("descenso_png"):
            d.image(pred["descenso_png"], caption="Mapa de descenso"); algo = True
        if res.napa:
            s = res.napa["stats"]
            d.p(f"{s['celdas_someras']} celdas con napa somera (≤ {s['umbral_m']:.1f} m): "
                f"verificar afección a ecosistemas dependientes (GDE).")
            algo = True
        return algo

    if "incertidumbre" in n:
        pred = getattr(res, "prediccion", None)
        if pred and pred.get("incertidumbre") is not None:
            d.h2("Incertidumbre (Monte Carlo)"); _tabla(d, pred["incertidumbre"])
            if pred.get("incert_png"):
                d.image(pred["incert_png"], caption="Bandas de incertidumbre")
            return True
        return False

    if "marco normativo" in n:
        d.table(["Instrumento", "Alcance"], [[k, v] for k, v in MARCO_NORMATIVO])
        return True

    if "glosario" in n:
        d.table(["Término", "Definición"], [[k, v] for k, v in GLOSARIO])
        return True

    if "conclusion" in n:
        crit = getattr(res, "criterio_calibracion", None)
        algo = False
        if crit:
            estado = ("cumple el criterio SEA" if crit.get("cumple")
                      else "no cumple el criterio SEA" if crit.get("cumple") is not None else "evaluado")
            d.bullet(f"Calibración: RMSE {crit['rmse_m']:.2f} m, MAE {crit['mae_m']:.2f} m ({estado}).")
            algo = True
        if res.balance and res.balance.get("discrepancia_pct") is not None:
            d.bullet(f"Balance hídrico con discrepancia {res.balance['discrepancia_pct']:.3g} % "
                     f"(criterio < 1 %)."); algo = True
        if res.prediccion and res.prediccion.get("descenso") is not None:
            df = res.prediccion["descenso"]
            col = next((c for c in df.columns if "descenso" in c.lower()), None)
            if col is not None and len(df):
                d.bullet(f"Descenso máximo predicho: {float(df[col].abs().max()):.2f} m."); algo = True
        return algo

    if "anexo" in n:
        tz = getattr(res, "trazabilidad", None)
        if tz:
            filas = [[k, str(tz[k])[:60]] for k in ("generado", "modelo", "motor", "hash_entradas_sha256")
                     if tz.get(k)]
            if filas:
                d.table(["Campo", "Valor"], filas)
                return True
        return False
    return False


def write_docx(output_path: Path, cfg, *, perfil: str = "sea", resultados=None,
               textos_secciones: dict | None = None, a_pdf: bool = True) -> Path:
    """Escribe el informe en .docx (tema azul) y, si a_pdf, lo convierte a PDF con LibreOffice."""
    spec = PERFILES.get(perfil, PERFILES["astm"])
    titulo = cfg.informe.get("titulo", f"Informe - {cfg.model_name}")
    autor = cfg.proyecto.get("autor", "yaku")

    d = DocBuilder()
    d.cover(titulo, spec["subtitulo"], f"{autor} — {datetime.now().strftime('%Y-%m-%d')}")
    for titulo_sec, guia in spec["secciones"]:
        d.h1(titulo_sec, numbered=False)
        n = _norm(titulo_sec)
        user = _texto_usuario(textos_secciones, n)
        if user:
            for parrafo in [p.strip() for p in user.split("\n\n") if p.strip()]:
                d.p(parrafo.replace("\n", " "))
        escribio = _seccion_datos(d, n, resultados) if resultados is not None else False
        if not user and not escribio:
            d.p(guia)

    output_path = Path(output_path).with_suffix(".docx")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    d.save(output_path)
    logger.info("Informe Word generado: %s", output_path.name)
    if a_pdf:
        try:
            pdf = docx_to_pdf(output_path)
            logger.info("Informe Word convertido a PDF: %s", Path(pdf).name)
            return Path(pdf)
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo convertir el .docx a PDF (%s). Queda el .docx.", exc)
    return output_path
