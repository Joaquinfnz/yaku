#!/usr/bin/env python3
"""Paquete de entregables para el SEIA: arma una carpeta lista para presentar.

Toma un proyecto ya corrido y construye `informe/entregables_seia/` con el informe
data-driven, las figuras, las tablas de resultados, los archivos de entrada del modelo
(anexo digital de trazabilidad), una plantilla de plan de seguimiento y un MANIFIESTO
que indexa todo con versiones y hash de las entradas.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from yaku.report.pdf import leer_secciones_md, write_pdf
from yaku.report.resultados import recolectar_resultados

logger = logging.getLogger("yaku")

# Archivos de entrada de MODFLOW 6 en texto (no binarios) que se copian como anexo.
_MODELO_EXTS = (
    ".nam", ".dis", ".disv", ".tdis", ".ims", ".npf", ".ic", ".oc",
    ".sto", ".chd", ".wel", ".riv", ".rcha", ".rch", ".evt", ".ghb", ".drn",
)


def _copiar(src: Path | None, dest_dir: Path) -> str | None:
    if src is None or not Path(src).exists():
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    destino = dest_dir / Path(src).name
    shutil.copy(src, destino)
    return destino.name


def _escribir_plan_seguimiento(destino: Path, cfg, res) -> None:
    """Plan de seguimiento con una fila por punto de observacion y umbrales reales.

    El umbral del nivel = descenso maximo predicho (de 'mfw predict'); el del caudal base =
    intercambio rio-acuifero simulado. Si no hay datos, deja una plantilla editable.
    """
    import pandas as pd

    umbral_descenso = ""
    if res.prediccion and res.prediccion.get("descenso") is not None:
        d = res.prediccion["descenso"]
        if "descenso_max_m" in d.columns and len(d):
            umbral_descenso = round(float(d["descenso_max_m"].iloc[0]), 3)

    filas = []
    obs_path = cfg.datos_dir / "observaciones_nivel.csv"
    if obs_path.exists():
        for _, o in pd.read_csv(obs_path).iterrows():
            filas.append({
                "variable": "nivel_freatico_m", "punto": str(o.get("nombre", "pozo")),
                "frecuencia": "mensual", "umbral_alerta": umbral_descenso,
                "observacion": "descenso maximo predicho (nivel de alerta)",
            })
    if res.caudal_base:
        filas.append({
            "variable": "caudal_base_m3d", "punto": "rio (tramo modelado)",
            "frecuencia": "mensual", "umbral_alerta": round(res.caudal_base["acuifero_a_rio_m3d"], 1),
            "observacion": "caudal base simulado de referencia",
        })
    if not filas:
        filas = [{"variable": "nivel_freatico_m", "punto": "pozo_monitoreo_1", "frecuencia": "mensual",
                  "umbral_alerta": "", "observacion": "definir nivel de alerta"}]
    pd.DataFrame(filas).to_csv(destino, index=False)


def armar_entregables(cfg, perfil: str = "sea") -> Path:
    """Construye informe/entregables_seia/ y devuelve su ruta."""
    res = recolectar_resultados(cfg)
    if res.head is None:
        raise FileNotFoundError(
            f"No hay resultados en {cfg.resultados_dir} (corre 'mfw run' antes de entregables)."
        )

    dest = cfg.informe_dir / "entregables_seia"
    figuras = dest / "figuras"
    tablas = dest / "tablas"
    modelo = dest / "modelo"
    for d in (dest, figuras, tablas, modelo):
        d.mkdir(parents=True, exist_ok=True)

    # 1) Informe data-driven
    pdf = dest / f"informe_{cfg.model_name}_{perfil}.pdf"
    textos = leer_secciones_md(cfg.informe_dir / "secciones.md")
    write_pdf(pdf, res.head, res.times,
              titulo=cfg.informe.get("titulo", f"Informe - {cfg.model_name}"),
              autor=cfg.proyecto.get("autor", "yaku"),
              perfil=perfil, resultados=res, textos_secciones=textos)

    # 2) Figuras
    figs: list[str] = []
    for png in res.mapas_carga:
        figs.append(_copiar(png, figuras))
    if res.napa:
        figs.append(_copiar(res.napa.get("png"), figuras))
    if res.seccion_vertical:
        figs.append(_copiar(res.seccion_vertical, figuras))
    if res.calibracion:
        figs.append(_copiar(res.calibracion.get("scatter"), figuras))
    if res.prediccion:
        figs.append(_copiar(res.prediccion.get("descenso_png"), figuras))
        figs.append(_copiar(res.prediccion.get("incert_png"), figuras))
    for extra in (res.mapa_conceptual, res.recarga_mapa, res.napa_animacion):
        figs.append(_copiar(extra, figuras))
    if res.indices_clima:                              # figuras de indices clima-hidrogeologia
        for f in (res.indices_clima.get("figuras") or {}).values():
            figs.append(_copiar(f, figuras))
    figs = [f for f in figs if f]

    # 3) Tablas
    tbs: list[str] = []
    if res.calibracion:
        cal = cfg.resultados_dir / "calibracion"
        for nombre in ("metricas_ajuste.csv", "residuales_observaciones.csv"):
            tbs.append(_copiar(cal / nombre, tablas))
    if res.balance and res.balance.get("csv"):
        tbs.append(_copiar(res.balance["csv"], tablas))
    for nombre in ("parametros_modelo.csv", "capas_modelo.csv"):
        tbs.append(_copiar(cfg.datos_dir / nombre, tablas))
    if res.qa is not None and not res.qa.empty:        # verificacion de calidad (QA)
        qa_csv = tablas / "verificacion_qa.csv"
        res.qa.to_csv(qa_csv, index=False)
        tbs.append(qa_csv)
    if res.indices_clima and res.indices_clima.get("csv"):   # indices clima-hidrogeologia
        tbs.append(_copiar(res.indices_clima["csv"], tablas))
    tbs = [t for t in tbs if t]

    # 4) Modelo (inputs de texto + trazabilidad)
    mods: list[str] = []
    if cfg.resultados_dir.is_dir():
        for f in sorted(cfg.resultados_dir.iterdir()):
            if f.is_file() and (f.suffix.lower() in _MODELO_EXTS or f.name in ("mfsim.nam", "inputs_metadata.json")):
                mods.append(_copiar(f, modelo))
    mods = [m for m in mods if m]

    # 5) Plan de seguimiento (derivado de las observaciones y los descensos predichos)
    plan = dest / "plan_seguimiento.csv"
    _escribir_plan_seguimiento(plan, cfg, res)

    # 6) MANIFIESTO
    tz = res.trazabilidad or {}
    lineas = [
        f"# Entregables SEIA - {cfg.model_name}",
        "",
        f"- Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Perfil de informe: {perfil}",
        f"- Autor: {cfg.proyecto.get('autor', 'yaku')}",
        f"- Hash de entradas (SHA256): {tz.get('hash_entradas_sha256', 's/d')}",
        "",
        "## Contenido",
        f"- `{pdf.name}` - informe tecnico con resultados reales.",
        f"- `figuras/` - {len(figs)} figura(s) de resultados.",
        f"- `tablas/` - {len(tbs)} tabla(s) (calibracion, balance, parametros).",
        f"- `modelo/` - {len(mods)} archivo(s) de entrada MODFLOW 6 + metadatos (anexo de trazabilidad).",
        "- `plan_seguimiento.csv` - plantilla de seguimiento de variables ambientales.",
        "",
        "## Versiones",
    ]
    for lib, ver in (tz.get("versiones") or {}).items():
        lineas.append(f"- {lib}: {ver}")
    (dest / "MANIFIESTO.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")

    logger.info("Entregables SEIA en %s (%d figuras, %d tablas, %d inputs)",
                dest, len(figs), len(tbs), len(mods))
    return dest
